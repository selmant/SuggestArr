import { ref } from 'vue';
import {
  approveSeerRequest,
  declineSeerRequest,
  getRequestSeerStatus,
  getRequestSeerStatusesBatch,
} from '@/api/api.js';
import { formatSeerStatusLabel } from '@/utils/seerStatus.js';
import {
  getCachedSeerStatus,
  invalidateSeerStatusCacheForItem,
  isSeerStatusCacheFresh,
  seerStatusCacheKey,
  setCachedSeerStatus,
} from '@/utils/seerStatusCache.js';

/**
 * Shared Seer approval state and actions for request poster cards and modals.
 *
 * @returns {object} Seer state refs and action helpers for Vue components.
 */
export function useRequestSeerActions() {
  const seerStatus = ref(null);
  const seerStatusLoading = ref(false);
  const seerActionLoading = ref(false);
  const seerStatusError = ref('');
  const seerStatusByRequest = ref({});
  const seerStatusLoadingByRequest = ref({});
  const seerActionLoadingByRequest = ref({});
  const seerStatusErrorByRequest = ref({});

  let modalTargetResolver = () => null;
  let seerStatusChangeHandler = null;
  let batchPrefetchPromise = null;
  const queuedPosterItems = new Map();
  let posterFlushTimer = null;
  let posterPrefetchSilent = false;
  const POSTER_BATCH_SIZE = 16;
  const POSTER_FLUSH_MS = 120;
  const SILENT_STATUS_FLUSH_MS = 120;
  let silentStatusFlushTimer = null;
  let pendingSilentStatuses = {};
  let posterSilentPrefetchDepth = 0;

  function setModalTargetResolver(resolver) {
    modalTargetResolver = typeof resolver === 'function' ? resolver : () => null;
  }

  function setSeerStatusChangeHandler(handler) {
    seerStatusChangeHandler = typeof handler === 'function' ? handler : null;
  }

  function getModalTarget() {
    return modalTargetResolver() || null;
  }

  function seerRequestKey(item) {
    return item?.request_id ? String(item.request_id) : '';
  }

  function statusCacheKeyFor(item) {
    return seerStatusCacheKey(seerRequestKey(item), item.media_type);
  }

  function canShowSeerActions(item) {
    return Boolean(item?.request_id && item?.media_type && !item.requests);
  }

  function canShowRelatedSeer(item) {
    return Boolean(item?.request_id && item?.media_type);
  }

  function getSeerModalTarget(source) {
    if (!source) {
      return null;
    }

    if (!source.requests && canShowSeerActions(source)) {
      return source;
    }

    if (Array.isArray(source.requests) && source.requests.length === 1) {
      const request = source.requests[0];
      if (canShowRelatedSeer(request)) {
        return request;
      }
    }

    return null;
  }

  function itemFromStatus(status) {
    return {
      request_id: status.tmdb_id,
      media_type: status.media_type,
    };
  }

  function hasFreshSeerStatus(item) {
    const key = seerRequestKey(item);
    if (!key) {
      return false;
    }

    const stored = item?.seer_status;
    const live = seerStatusByRequest.value[key];
    const cached = isSeerStatusCacheFresh(statusCacheKeyFor(item))
      ? getCachedSeerStatus(statusCacheKeyFor(item))
      : null;
    const resolved = live || cached;

    if (!resolved) {
      return false;
    }

    if (stored && resolved.seer_status && stored !== resolved.seer_status) {
      return false;
    }

    if (stored === 'pending' && resolved.seer_status === 'pending' && !resolved.can_action) {
      return false;
    }

    return true;
  }

  function rememberSeerStatus(item, status) {
    if (!item?.request_id) {
      return;
    }
    setCachedSeerStatus(statusCacheKeyFor(item), status);
  }

  function applySeerStatus(status, { merge = true } = {}) {
    seerStatus.value = merge && seerStatus.value
      ? { ...seerStatus.value, ...status }
      : (status || null);
  }

  function applySeerStatusFor(item, status, { merge = true } = {}) {
    const key = seerRequestKey(item);
    if (!key) {
      return;
    }

    const previous = seerStatusByRequest.value[key];
    const nextStatus = merge && previous
      ? { ...previous, ...status }
      : (status || null);

    seerStatusByRequest.value = {
      ...seerStatusByRequest.value,
      [key]: nextStatus,
    };

    if (item?.request_id) {
      rememberSeerStatus(item, nextStatus);
      if (nextStatus?.seer_status) {
        seerStatusChangeHandler?.(item, nextStatus);
      }
    }

    const modalTarget = getModalTarget();
    if (modalTarget?.request_id === item.request_id) {
      applySeerStatus(nextStatus, { merge: false });
    }
  }

  function getSeerStatus(item) {
    return seerStatusByRequest.value[seerRequestKey(item)] || null;
  }

  function getSeerInlineLabel(item) {
    const key = seerRequestKey(item);
    if (seerStatusLoadingByRequest.value[key]) {
      return 'Checking';
    }
    if (seerStatusErrorByRequest.value[key]) {
      return seerStatusErrorByRequest.value[key];
    }
    const status = getSeerStatus(item);
    return formatSeerStatusLabel(status?.seer_status || item?.seer_status || 'not_found');
  }

  function canActionSeer(item) {
    const status = getSeerStatus(item);
    if (status) {
      return Boolean(status.can_action);
    }

    const key = seerRequestKey(item);
    if (seerStatusLoadingByRequest.value[key] || seerStatusErrorByRequest.value[key]) {
      return false;
    }

    return item?.seer_status === 'pending';
  }

  function isSeerBusy(item) {
    const key = seerRequestKey(item);
    return Boolean(
      seerStatusLoadingByRequest.value[key] ||
      seerActionLoadingByRequest.value[key],
    );
  }

  async function loadSeerStatusFor(item, { force = false } = {}) {
    if (!canShowRelatedSeer(item)) {
      return;
    }

    const key = seerRequestKey(item);
    if (!force && hasFreshSeerStatus(item)) {
      const cached = getCachedSeerStatus(statusCacheKeyFor(item));
      if (cached) {
        applySeerStatusFor(item, cached, { merge: false });
      }
      return;
    }

    seerStatusLoadingByRequest.value = { ...seerStatusLoadingByRequest.value, [key]: true };
    seerStatusErrorByRequest.value = { ...seerStatusErrorByRequest.value, [key]: '' };
    try {
      const response = await getRequestSeerStatus(item.request_id, item.media_type);
      applySeerStatusFor(item, response.data, { merge: false });
    } catch (error) {
      applySeerStatusFor(item, null, { merge: false });
      seerStatusErrorByRequest.value = {
        ...seerStatusErrorByRequest.value,
        [key]: error.response?.data?.message || 'Unavailable',
      };
    } finally {
      seerStatusLoadingByRequest.value = { ...seerStatusLoadingByRequest.value, [key]: false };
    }
  }

  async function loadSeerStatusForSource(source, { force = false } = {}) {
    const target = getSeerModalTarget(source);
    if (!target) {
      applySeerStatus(null, { merge: false });
      return;
    }

    if (!force && hasFreshSeerStatus(target)) {
      applySeerStatus(getSeerStatus(target), { merge: false });
      return;
    }

    seerStatusLoading.value = true;
    seerStatusError.value = '';
    try {
      const response = await getRequestSeerStatus(target.request_id, target.media_type);
      applySeerStatus(response.data, { merge: false });
      applySeerStatusFor(target, response.data, { merge: false });
    } catch (error) {
      applySeerStatus(null, { merge: false });
      seerStatusError.value = error.response?.data?.message || 'Seer unavailable';
    } finally {
      seerStatusLoading.value = false;
    }
  }

  function queueSilentSeerStatusUpdates(statuses) {
    pendingSilentStatuses = { ...pendingSilentStatuses, ...statuses };
    if (!silentStatusFlushTimer) {
      silentStatusFlushTimer = setTimeout(flushSilentSeerStatusUpdates, SILENT_STATUS_FLUSH_MS);
    }
  }

  function flushSilentSeerStatusUpdates() {
    silentStatusFlushTimer = null;
    if (!Object.keys(pendingSilentStatuses).length) {
      return;
    }

    seerStatusByRequest.value = {
      ...seerStatusByRequest.value,
      ...pendingSilentStatuses,
    };
    pendingSilentStatuses = {};
  }

  function flushSilentSeerStatusUpdatesNow() {
    if (silentStatusFlushTimer) {
      clearTimeout(silentStatusFlushTimer);
      silentStatusFlushTimer = null;
    }
    flushSilentSeerStatusUpdates();
  }

  function isPosterSilentPrefetchActive() {
    return posterSilentPrefetchDepth > 0;
  }

  async function fetchBatchStatuses(items, { silent = false } = {}) {
    const keys = items.map((item) => seerRequestKey(item));
    if (!silent) {
      const loadingState = { ...seerStatusLoadingByRequest.value };
      const errorState = { ...seerStatusErrorByRequest.value };
      keys.forEach((key) => {
        loadingState[key] = true;
        errorState[key] = '';
      });
      seerStatusLoadingByRequest.value = loadingState;
      seerStatusErrorByRequest.value = errorState;
    }

    try {
      const response = await getRequestSeerStatusesBatch(items.map((item) => ({
        tmdb_id: item.request_id,
        media_type: item.media_type,
      })));
      const batchStatuses = {};
      const modalTarget = getModalTarget();

      for (const status of response.data?.statuses || []) {
        const item = itemFromStatus(status);
        const key = seerRequestKey(item);
        if (!key) {
          continue;
        }
        batchStatuses[key] = status || null;
        if (item?.request_id) {
          rememberSeerStatus(item, status);
        }
        if (seerStatusChangeHandler) {
          seerStatusChangeHandler(item, status);
        }
        if (modalTarget?.request_id === item.request_id) {
          applySeerStatus(status, { merge: false });
        }
      }

      if (silent) {
        queueSilentSeerStatusUpdates(batchStatuses);
      } else {
        seerStatusByRequest.value = {
          ...seerStatusByRequest.value,
          ...batchStatuses,
        };
      }
    } catch (error) {
      if (silent) {
        return;
      }
      const message = error.response?.data?.message || 'Unavailable';
      const nextErrors = { ...seerStatusErrorByRequest.value };
      keys.forEach((key) => {
        nextErrors[key] = message;
      });
      seerStatusErrorByRequest.value = nextErrors;
    } finally {
      if (!silent) {
        const nextLoading = { ...seerStatusLoadingByRequest.value };
        keys.forEach((key) => {
          nextLoading[key] = false;
        });
        seerStatusLoadingByRequest.value = nextLoading;
      }
    }
  }

  function prefetchPosterSeerStatuses(requests) {
    for (const item of (requests || [])) {
      queuePosterSeerStatus(item);
    }
  }

  function schedulePosterSeerFlush() {
    if (posterFlushTimer) {
      return;
    }
    posterFlushTimer = setTimeout(() => {
      posterFlushTimer = null;
      void flushPosterSeerQueue({ silent: posterPrefetchSilent });
    }, POSTER_FLUSH_MS);
  }

  async function flushPosterSeerQueue({ silent = false } = {}) {
    const allPending = [...queuedPosterItems.values()];
    const pending = allPending.slice(0, POSTER_BATCH_SIZE);
    const overflow = allPending.slice(POSTER_BATCH_SIZE);
    queuedPosterItems.clear();
    for (const item of overflow) {
      queuedPosterItems.set(seerRequestKey(item), item);
    }
    if (!pending.length) {
      if (queuedPosterItems.size > 0) {
        schedulePosterSeerFlush();
      }
      return;
    }
    if (batchPrefetchPromise) {
      await batchPrefetchPromise;
    }
    batchPrefetchPromise = fetchBatchStatuses(pending, { silent });
    try {
      await batchPrefetchPromise;
    } finally {
      batchPrefetchPromise = null;
    }
    if (queuedPosterItems.size > 0) {
      schedulePosterSeerFlush();
    }
  }

  function queuePosterSeerStatus(item) {
    if (!canShowRelatedSeer(item) || hasFreshSeerStatus(item)) {
      const cached = getCachedSeerStatus(statusCacheKeyFor(item));
      if (cached) {
        applySeerStatusFor(item, cached, { merge: false });
      }
      return;
    }
    queuedPosterItems.set(seerRequestKey(item), item);
    schedulePosterSeerFlush();
  }

  async function drainPosterSeerQueue({ silent = false } = {}) {
    await flushPosterSeerQueue({ silent });
    if (posterFlushTimer) {
      await new Promise((resolve) => setTimeout(resolve, POSTER_FLUSH_MS + 20));
    }
    if (batchPrefetchPromise) {
      await batchPrefetchPromise;
    }
    if (queuedPosterItems.size > 0 || posterFlushTimer) {
      await drainPosterSeerQueue({ silent });
    }
  }

  async function prefetchPosterSeerStatusesAsync(requests, { silent = false } = {}) {
    posterPrefetchSilent = silent;
    if (silent) {
      posterSilentPrefetchDepth += 1;
    }
    try {
      for (const item of (requests || [])) {
        queuePosterSeerStatus(item);
      }
      await drainPosterSeerQueue({ silent });
      if (silent) {
        flushSilentSeerStatusUpdatesNow();
      }
    } finally {
      if (silent) {
        posterSilentPrefetchDepth = Math.max(0, posterSilentPrefetchDepth - 1);
      }
      posterPrefetchSilent = false;
    }
  }

  async function approveFor(item) {
    if (!canShowRelatedSeer(item) || isSeerBusy(item)) {
      return;
    }

    const key = seerRequestKey(item);
    const previousStatus = getSeerStatus(item) ? { ...getSeerStatus(item) } : null;

    invalidateSeerStatusCacheForItem(item.request_id, item.media_type);
    applySeerStatusFor(item, { seer_status: 'approved', can_action: false });

    seerActionLoadingByRequest.value = { ...seerActionLoadingByRequest.value, [key]: true };
    seerStatusErrorByRequest.value = { ...seerStatusErrorByRequest.value, [key]: '' };
    try {
      const response = await approveSeerRequest(item.request_id, item.media_type);
      applySeerStatusFor(item, response.data, { merge: false });
      const modalTarget = getModalTarget();
      if (modalTarget?.request_id === item.request_id) {
        applySeerStatus(response.data, { merge: false });
      }
    } catch (error) {
      applySeerStatusFor(item, previousStatus, { merge: false });
      seerStatusErrorByRequest.value = {
        ...seerStatusErrorByRequest.value,
        [key]: error.response?.data?.message || 'Could not approve',
      };
    } finally {
      seerActionLoadingByRequest.value = { ...seerActionLoadingByRequest.value, [key]: false };
    }
  }

  async function declineFor(item) {
    if (!canShowRelatedSeer(item) || isSeerBusy(item)) {
      return;
    }

    const key = seerRequestKey(item);
    const previousStatus = getSeerStatus(item) ? { ...getSeerStatus(item) } : null;

    invalidateSeerStatusCacheForItem(item.request_id, item.media_type);
    applySeerStatusFor(item, { seer_status: 'declined', can_action: false });

    seerActionLoadingByRequest.value = { ...seerActionLoadingByRequest.value, [key]: true };
    seerStatusErrorByRequest.value = { ...seerStatusErrorByRequest.value, [key]: '' };
    try {
      const response = await declineSeerRequest(item.request_id, item.media_type);
      applySeerStatusFor(item, response.data, { merge: false });
      const modalTarget = getModalTarget();
      if (modalTarget?.request_id === item.request_id) {
        applySeerStatus(response.data, { merge: false });
      }
    } catch (error) {
      applySeerStatusFor(item, previousStatus, { merge: false });
      seerStatusErrorByRequest.value = {
        ...seerStatusErrorByRequest.value,
        [key]: error.response?.data?.message || 'Could not decline',
      };
    } finally {
      seerActionLoadingByRequest.value = { ...seerActionLoadingByRequest.value, [key]: false };
    }
  }

  async function approveForSource(source) {
    const target = getSeerModalTarget(source);
    if (!target || seerActionLoading.value) {
      return;
    }
    await approveFor(target);
  }

  async function declineForSource(source) {
    const target = getSeerModalTarget(source);
    if (!target || seerActionLoading.value) {
      return;
    }
    await declineFor(target);
  }

  function posterSeerProps(item) {
    const status = getSeerStatus(item);
    return {
      showSeerActions: canShowSeerActions(item),
      seerLabel: getSeerInlineLabel(item),
      seerStatus: status?.seer_status || item?.seer_status || '',
      seerBusy: !isPosterSilentPrefetchActive() && isSeerBusy(item),
      seerCanAction: !isPosterSilentPrefetchActive() && canActionSeer(item),
    };
  }

  return {
    seerStatus,
    seerStatusLoading,
    seerActionLoading,
    seerStatusError,
    seerStatusByRequest,
    seerStatusLoadingByRequest,
    seerActionLoadingByRequest,
    seerStatusErrorByRequest,
    setModalTargetResolver,
    setSeerStatusChangeHandler,
    canShowSeerActions,
    canShowRelatedSeer,
    getSeerModalTarget,
    getSeerStatus,
    getSeerInlineLabel,
    canActionSeer,
    isSeerBusy,
    loadSeerStatusFor,
    loadSeerStatusForSource,
    approveFor,
    declineFor,
    approveForSource,
    declineForSource,
    prefetchPosterSeerStatuses,
    prefetchPosterSeerStatusesAsync,
    queuePosterSeerStatus,
    posterSeerProps,
    applySeerStatus,
  };
}
