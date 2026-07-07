import { ref } from 'vue';
import {
  getRequestTraktStatus,
  getRequestTraktStatusesBatch,
  listTraktMediaUsers,
  markRequestWatched,
  rateRequestOnTrakt,
  unmarkRequestWatched,
} from '@/api/api.js';
import { formatTraktStars, starsFromTraktStatus } from '@/utils/traktRating.js';
import {
  getCachedTraktStatus,
  invalidateTraktStatusCacheForItem,
  isTraktStatusCacheFresh,
  setCachedTraktStatus,
  traktStatusCacheKey,
} from '@/utils/traktStatusCache.js';

/**
 * Shared Trakt watched/rating state and actions for request poster cards and modals.
 *
 * @returns {object} Trakt state refs and action helpers for Vue components.
 */
export function useRequestTraktActions() {
  const defaultTraktUserId = ref('');
  const connectedTraktUserIds = ref(new Set());
  const traktStatus = ref(null);
  const traktStatusLoading = ref(false);
  const traktActionLoading = ref(false);
  const traktStatusError = ref('');
  const traktRatingStars = ref('');
  const traktStatusByRequest = ref({});
  const traktRatingStarsByRequest = ref({});
  const traktStatusLoadingByRequest = ref({});
  const traktActionLoadingByRequest = ref({});
  const traktStatusErrorByRequest = ref({});

  const batchPrefetchByUser = new Map();
  let batchPrefetchPromise = null;
  const queuedPosterItems = new Map();
  let posterFlushTimer = null;
  let posterPrefetchSilent = false;
  const POSTER_BATCH_SIZE = 16;
  const POSTER_FLUSH_MS = 120;
  const SILENT_STATUS_FLUSH_MS = 120;
  let silentStatusFlushTimer = null;
  let pendingSilentStatuses = {};
  let pendingSilentStars = {};
  let posterSilentPrefetchDepth = 0;

  let modalTargetResolver = () => null;

  /**
   * Register a callback that returns the request item bound to the open modal strip.
   *
   * @param {Function} resolver
   */
  function setModalTargetResolver(resolver) {
    modalTargetResolver = typeof resolver === 'function' ? resolver : () => null;
  }

  function getModalTarget() {
    return modalTargetResolver() || null;
  }

  function statusCacheKeyFor(item) {
    return traktStatusCacheKey(
      resolveTraktUserId(item),
      traktRequestKey(item),
      item.media_type,
    );
  }

  function invalidateTraktStatusForItem(item) {
    if (!item?.request_id || !item?.media_type) {
      return;
    }
    const userId = resolveTraktUserId(item);
    if (!userId) {
      return;
    }
    invalidateTraktStatusCacheForItem(userId, item.request_id, item.media_type);
  }

  function hasFreshTraktStatus(item) {
    const key = traktRequestKey(item);
    if (!key) {
      return false;
    }
    return Boolean(traktStatusByRequest.value[key]) || isTraktStatusCacheFresh(statusCacheKeyFor(item));
  }

  function rememberTraktStatus(item, status) {
    if (!item?.request_id) {
      return;
    }
    setCachedTraktStatus(statusCacheKeyFor(item), status);
  }

  function itemFromStatus(status) {
    return {
      request_id: status.tmdb_id,
      media_type: status.media_type,
      user_id: status.user_id,
    };
  }

  function traktRequestKey(item) {
    return item?.request_id ? String(item.request_id) : '';
  }

  function resolveTraktUserId(item) {
    const externalUserId = item?.external_user_id;
    if (externalUserId) {
      return String(externalUserId);
    }

    const requestUserId = item?.user_id;
    if (requestUserId && connectedTraktUserIds.value.has(String(requestUserId))) {
      return String(requestUserId);
    }

    return defaultTraktUserId.value || '';
  }

  function canManageTrakt(item) {
    return Boolean(
      item &&
      item.request_id &&
      item.media_type &&
      !item.requests &&
      resolveTraktUserId(item),
    );
  }

  function canShowRelatedTrakt(item) {
    return Boolean(
      item?.request_id &&
      item?.media_type &&
      resolveTraktUserId(item),
    );
  }

  function getTraktModalTarget(source) {
    if (!source) {
      return null;
    }

    if (!source.requests && canManageTrakt(source)) {
      return source;
    }

    if (Array.isArray(source.requests) && source.requests.length === 1) {
      const request = source.requests[0];
      if (canShowRelatedTrakt(request)) {
        return request;
      }
    }

    return null;
  }

  async function loadTraktDefaults() {
    try {
      const response = await listTraktMediaUsers();
      const connected = (response.data?.media_users || []).filter((user) => user.trakt?.connected);
      connectedTraktUserIds.value = new Set(
        connected.map((user) => String(user.external_user_id || '')).filter(Boolean),
      );
      if (connected.length > 0) {
        defaultTraktUserId.value = String(connected[0].external_user_id || '');
      } else {
        defaultTraktUserId.value = '';
      }
    } catch (error) {
      console.warn('Could not load Trakt media users for request actions:', error);
    }
  }

  function mergeTraktStatus(previous, incoming) {
    if (!incoming) {
      return null;
    }
    const merged = { ...(previous || {}), ...incoming };
    if (previous) {
      if (!('watched' in incoming)) {
        merged.watched = previous.watched;
      }
      if (!('rating' in incoming) && previous.rating != null) {
        merged.rating = previous.rating;
        merged.rating_stars = starsFromTraktStatus(previous);
      }
    }
    if (merged.rating != null && merged.rating_stars == null) {
      merged.rating_stars = Number(merged.rating) / 2;
    }
    return merged;
  }

  function applyTraktStatus(status, { merge = true } = {}) {
    const previous = traktStatus.value;
    traktStatus.value = merge ? mergeTraktStatus(previous, status) : (status || null);
    traktRatingStars.value = starsFromTraktStatus(traktStatus.value);
  }

  function applyTraktStatusFor(item, status, { merge = true } = {}) {
    const key = traktRequestKey(item);
    if (!key) return;

    const previous = traktStatusByRequest.value[key];
    const nextStatus = merge ? mergeTraktStatus(previous, status) : (status || null);

    traktStatusByRequest.value = {
      ...traktStatusByRequest.value,
      [key]: nextStatus,
    };
    traktRatingStarsByRequest.value = {
      ...traktRatingStarsByRequest.value,
      [key]: starsFromTraktStatus(nextStatus),
    };

    if (item?.request_id) {
      rememberTraktStatus(item, nextStatus);
    }

    const modalTarget = getModalTarget();
    if (modalTarget?.request_id === item.request_id) {
      applyTraktStatus(nextStatus);
    }
  }

  function getTraktStatus(item) {
    return traktStatusByRequest.value[traktRequestKey(item)] || null;
  }

  function getTraktRatingStars(item) {
    return traktRatingStarsByRequest.value[traktRequestKey(item)] || '';
  }

  function getTraktInlineLabel(item) {
    const key = traktRequestKey(item);
    if (traktStatusLoadingByRequest.value[key]) return 'Checking';
    if (traktStatusErrorByRequest.value[key]) return traktStatusErrorByRequest.value[key];

    const status = getTraktStatus(item);
    if (!status) return 'Trakt';
    const stars = formatTraktStars(starsFromTraktStatus(status));
    if (stars) {
      return `${status.watched ? 'Watched' : 'Unwatched'} · ${stars}★`;
    }
    return status.watched ? 'Watched' : 'Unwatched';
  }

  function isTraktBusy(item) {
    const key = traktRequestKey(item);
    return Boolean(
      traktStatusLoadingByRequest.value[key] ||
      traktActionLoadingByRequest.value[key],
    );
  }

  async function loadTraktStatusFor(item, { force = false } = {}) {
    if (!canShowRelatedTrakt(item)) return;

    const key = traktRequestKey(item);
    if (force) {
      invalidateTraktStatusForItem(item);
    }
    if (!force && hasFreshTraktStatus(item)) {
      const cached = getCachedTraktStatus(statusCacheKeyFor(item));
      if (cached) {
        applyTraktStatusFor(item, cached, { merge: false });
      }
      return;
    }

    const userId = resolveTraktUserId(item);
    traktStatusLoadingByRequest.value = { ...traktStatusLoadingByRequest.value, [key]: true };
    traktStatusErrorByRequest.value = { ...traktStatusErrorByRequest.value, [key]: '' };
    try {
      const response = await getRequestTraktStatus(item.request_id, item.media_type, userId);
      applyTraktStatusFor(item, response.data, { merge: false });
    } catch (error) {
      applyTraktStatusFor(item, null, { merge: false });
      traktStatusErrorByRequest.value = {
        ...traktStatusErrorByRequest.value,
        [key]: error.response?.data?.message || 'Unavailable',
      };
    } finally {
      traktStatusLoadingByRequest.value = { ...traktStatusLoadingByRequest.value, [key]: false };
    }
  }

  async function loadTraktStatusForSource(source, { force = false } = {}) {
    const target = getTraktModalTarget(source);
    if (!target) {
      applyTraktStatus(null, { merge: false });
      return;
    }

    if (force) {
      invalidateTraktStatusForItem(target);
    }
    if (!force && hasFreshTraktStatus(target)) {
      applyTraktStatus(getTraktStatus(target), { merge: false });
      return;
    }

    traktStatusLoading.value = true;
    traktStatusError.value = '';
    try {
      const response = await getRequestTraktStatus(
        target.request_id,
        target.media_type,
        resolveTraktUserId(target),
      );
      applyTraktStatus(response.data, { merge: false });
      applyTraktStatusFor(target, response.data, { merge: false });
    } catch (error) {
      applyTraktStatus(null, { merge: false });
      traktStatusError.value = error.response?.data?.message || 'Trakt unavailable';
    } finally {
      traktStatusLoading.value = false;
    }
  }

  async function setTraktWatchedForSource(source, watched) {
    const target = getTraktModalTarget(source);
    if (!target || traktActionLoading.value || typeof watched !== 'boolean') return;

    const userId = resolveTraktUserId(target);
    const previousStatus = traktStatus.value ? { ...traktStatus.value } : null;

    applyTraktStatus({ watched });
    applyTraktStatusFor(target, { watched });

    traktActionLoading.value = true;
    traktStatusError.value = '';
    try {
      const response = watched
        ? await markRequestWatched(
          target.request_id,
          target.media_type,
          userId,
          traktRatingStars.value || null,
        )
        : await unmarkRequestWatched(target.request_id, target.media_type, userId);
      applyTraktStatus(response.data, { merge: false });
      applyTraktStatusFor(target, response.data, { merge: false });
    } catch (error) {
      applyTraktStatus(previousStatus, { merge: false });
      applyTraktStatusFor(target, previousStatus, { merge: false });
      traktStatusError.value = error.response?.data?.message || 'Could not update Trakt';
    } finally {
      traktActionLoading.value = false;
    }
  }

  function queueSilentTraktStatusUpdates(statuses, stars) {
    pendingSilentStatuses = { ...pendingSilentStatuses, ...statuses };
    pendingSilentStars = { ...pendingSilentStars, ...stars };
    if (!silentStatusFlushTimer) {
      silentStatusFlushTimer = setTimeout(flushSilentTraktStatusUpdates, SILENT_STATUS_FLUSH_MS);
    }
  }

  function flushSilentTraktStatusUpdates() {
    silentStatusFlushTimer = null;
    if (!Object.keys(pendingSilentStatuses).length) {
      return;
    }

    traktStatusByRequest.value = {
      ...traktStatusByRequest.value,
      ...pendingSilentStatuses,
    };
    traktRatingStarsByRequest.value = {
      ...traktRatingStarsByRequest.value,
      ...pendingSilentStars,
    };
    pendingSilentStatuses = {};
    pendingSilentStars = {};
  }

  function flushSilentTraktStatusUpdatesNow() {
    if (silentStatusFlushTimer) {
      clearTimeout(silentStatusFlushTimer);
      silentStatusFlushTimer = null;
    }
    flushSilentTraktStatusUpdates();
  }

  function isPosterSilentPrefetchActive() {
    return posterSilentPrefetchDepth > 0;
  }

  async function fetchBatchStatuses(userId, items, { silent = false } = {}) {
    const keys = items.map((item) => traktRequestKey(item));
    if (!silent) {
      const loadingState = { ...traktStatusLoadingByRequest.value };
      const errorState = { ...traktStatusErrorByRequest.value };
      keys.forEach((key) => {
        loadingState[key] = true;
        errorState[key] = '';
      });
      traktStatusLoadingByRequest.value = loadingState;
      traktStatusErrorByRequest.value = errorState;
    }

    try {
      const response = await getRequestTraktStatusesBatch(userId, items.map((item) => ({
        tmdb_id: item.request_id,
        media_type: item.media_type,
      })));
      const batchStatuses = {};
      const batchStars = {};
      const modalTarget = getModalTarget();

      for (const status of response.data?.statuses || []) {
        const item = itemFromStatus(status);
        const key = traktRequestKey(item);
        if (!key) {
          continue;
        }
        batchStatuses[key] = status || null;
        batchStars[key] = starsFromTraktStatus(status);
        if (item?.request_id) {
          rememberTraktStatus(item, status);
        }
        if (modalTarget?.request_id === item.request_id) {
          applyTraktStatus(status, { merge: false });
        }
      }

      if (silent) {
        queueSilentTraktStatusUpdates(batchStatuses, batchStars);
      } else {
        traktStatusByRequest.value = {
          ...traktStatusByRequest.value,
          ...batchStatuses,
        };
        traktRatingStarsByRequest.value = {
          ...traktRatingStarsByRequest.value,
          ...batchStars,
        };
      }
    } catch (error) {
      if (silent) {
        return;
      }
      const message = error.response?.data?.message || 'Unavailable';
      const nextErrors = { ...traktStatusErrorByRequest.value };
      keys.forEach((key) => {
        nextErrors[key] = message;
      });
      traktStatusErrorByRequest.value = nextErrors;
    } finally {
      if (!silent) {
        const nextLoading = { ...traktStatusLoadingByRequest.value };
        keys.forEach((key) => {
          nextLoading[key] = false;
        });
        traktStatusLoadingByRequest.value = nextLoading;
      }
    }
  }

  function prefetchPosterTraktStatuses(requests, { force = false } = {}) {
    for (const item of (requests || [])) {
      queuePosterTraktStatus(item, { force });
    }
  }

  function schedulePosterTraktFlush() {
    if (posterFlushTimer) {
      return;
    }
    posterFlushTimer = setTimeout(() => {
      posterFlushTimer = null;
      void flushPosterTraktQueue({ silent: posterPrefetchSilent });
    }, POSTER_FLUSH_MS);
  }

  async function flushPosterTraktQueue({ silent = false } = {}) {
    const pending = [...queuedPosterItems.values()];
    queuedPosterItems.clear();
    if (!pending.length) {
      return;
    }

    const pendingByUser = new Map();
    const overflow = [];

    for (const item of pending) {
      const userId = resolveTraktUserId(item);
      if (!userId) {
        continue;
      }
      if (!pendingByUser.has(userId)) {
        pendingByUser.set(userId, []);
      }
      const bucket = pendingByUser.get(userId);
      const alreadyQueued = bucket.some((entry) => String(entry.request_id) === String(item.request_id));
      if (alreadyQueued) {
        continue;
      }
      if (bucket.length < POSTER_BATCH_SIZE) {
        bucket.push(item);
      } else {
        overflow.push(item);
      }
    }

    for (const item of overflow) {
      queuedPosterItems.set(traktRequestKey(item), item);
    }

    if (batchPrefetchPromise) {
      await batchPrefetchPromise;
    }

    batchPrefetchPromise = Promise.all([...pendingByUser.entries()].map(async ([userId, items]) => {
      if (!items.length) {
        return;
      }
      await fetchBatchStatuses(userId, items, { silent });
    }));
    try {
      await batchPrefetchPromise;
    } finally {
      batchPrefetchPromise = null;
    }

    if (queuedPosterItems.size > 0) {
      schedulePosterTraktFlush();
    }
  }

  function queuePosterTraktStatus(item, { force = false } = {}) {
    if (force) {
      invalidateTraktStatusForItem(item);
    }
    if (!force && (!canShowRelatedTrakt(item) || hasFreshTraktStatus(item))) {
      const cached = getCachedTraktStatus(statusCacheKeyFor(item));
      if (cached) {
        applyTraktStatusFor(item, cached, { merge: false });
      }
      return;
    }
    if (!canShowRelatedTrakt(item)) {
      return;
    }
    queuedPosterItems.set(traktRequestKey(item), item);
    schedulePosterTraktFlush();
  }

  async function drainPosterTraktQueue({ silent = false } = {}) {
    await flushPosterTraktQueue({ silent });
    if (posterFlushTimer) {
      await new Promise((resolve) => setTimeout(resolve, POSTER_FLUSH_MS + 20));
    }
    if (batchPrefetchPromise) {
      await batchPrefetchPromise;
    }
    if (queuedPosterItems.size > 0 || posterFlushTimer) {
      await drainPosterTraktQueue({ silent });
    }
  }

  async function prefetchPosterTraktStatusesAsync(requests, { force = false, silent = false } = {}) {
    posterPrefetchSilent = silent;
    if (silent) {
      posterSilentPrefetchDepth += 1;
    }
    try {
      for (const item of (requests || [])) {
        queuePosterTraktStatus(item, { force });
      }
      await drainPosterTraktQueue({ silent });
      if (silent) {
        flushSilentTraktStatusUpdatesNow();
      }
    } finally {
      if (silent) {
        posterSilentPrefetchDepth = Math.max(0, posterSilentPrefetchDepth - 1);
      }
      posterPrefetchSilent = false;
    }
  }

  async function rateSelectedOnTraktForSource(source) {
    const target = getTraktModalTarget(source);
    if (!target || !traktRatingStars.value || traktActionLoading.value) {
      return;
    }

    const userId = resolveTraktUserId(target);
    traktActionLoading.value = true;
    traktStatusError.value = '';
    try {
      const response = await rateRequestOnTrakt(
        target.request_id,
        target.media_type,
        userId,
        traktRatingStars.value,
      );
      applyTraktStatus(response.data, { merge: false });
      applyTraktStatusFor(target, response.data, { merge: false });
    } catch (error) {
      traktStatusError.value = error.response?.data?.message || 'Could not rate on Trakt';
    } finally {
      traktActionLoading.value = false;
    }
  }

  async function setTraktWatchedFor(item, watched) {
    if (!canShowRelatedTrakt(item) || isTraktBusy(item) || typeof watched !== 'boolean') return;

    const key = traktRequestKey(item);
    const previousStatus = getTraktStatus(item) ? { ...getTraktStatus(item) } : null;
    const rating = getTraktRatingStars(item);
    const userId = resolveTraktUserId(item);

    applyTraktStatusFor(item, { watched });

    traktActionLoadingByRequest.value = { ...traktActionLoadingByRequest.value, [key]: true };
    traktStatusErrorByRequest.value = { ...traktStatusErrorByRequest.value, [key]: '' };
    try {
      const response = watched
        ? await markRequestWatched(item.request_id, item.media_type, userId, rating || null)
        : await unmarkRequestWatched(item.request_id, item.media_type, userId);
      applyTraktStatusFor(item, response.data, { merge: false });
    } catch (error) {
      applyTraktStatusFor(item, previousStatus, { merge: false });
      traktStatusErrorByRequest.value = {
        ...traktStatusErrorByRequest.value,
        [key]: error.response?.data?.message || 'Could not update',
      };
    } finally {
      traktActionLoadingByRequest.value = { ...traktActionLoadingByRequest.value, [key]: false };
    }
  }

  async function rateRequestOnTraktFor(item, stars) {
    const key = traktRequestKey(item);
    traktRatingStarsByRequest.value = { ...traktRatingStarsByRequest.value, [key]: stars };
    if (!canShowRelatedTrakt(item) || !stars || isTraktBusy(item)) return;

    const userId = resolveTraktUserId(item);
    traktActionLoadingByRequest.value = { ...traktActionLoadingByRequest.value, [key]: true };
    traktStatusErrorByRequest.value = { ...traktStatusErrorByRequest.value, [key]: '' };
    try {
      const response = await rateRequestOnTrakt(item.request_id, item.media_type, userId, stars);
      applyTraktStatusFor(item, response.data, { merge: false });
    } catch (error) {
      traktStatusErrorByRequest.value = {
        ...traktStatusErrorByRequest.value,
        [key]: error.response?.data?.message || 'Could not rate',
      };
    } finally {
      traktActionLoadingByRequest.value = { ...traktActionLoadingByRequest.value, [key]: false };
    }
  }

  function posterTraktProps(item) {
    return {
      showTraktActions: canShowRelatedTrakt(item),
      traktLabel: getTraktInlineLabel(item),
      traktWatched: Boolean(getTraktStatus(item)?.watched),
      traktBusy: !isPosterSilentPrefetchActive() && isTraktBusy(item),
      traktRatingStars: getTraktRatingStars(item),
    };
  }

  return {
    defaultTraktUserId,
    traktStatus,
    traktStatusLoading,
    traktActionLoading,
    traktStatusError,
    traktRatingStars,
    traktStatusByRequest,
    traktRatingStarsByRequest,
    traktStatusLoadingByRequest,
    traktActionLoadingByRequest,
    traktStatusErrorByRequest,
    setModalTargetResolver,
    resolveTraktUserId,
    canManageTrakt,
    canShowRelatedTrakt,
    getTraktModalTarget,
    loadTraktDefaults,
    getTraktStatus,
    getTraktRatingStars,
    getTraktInlineLabel,
    isTraktBusy,
    loadTraktStatusFor,
    loadTraktStatusForSource,
    setTraktWatchedForSource,
    rateSelectedOnTraktForSource,
    setTraktWatchedFor,
    rateRequestOnTraktFor,
    prefetchPosterTraktStatuses,
    queuePosterTraktStatus,
    posterTraktProps,
    applyTraktStatus,
  };
}
