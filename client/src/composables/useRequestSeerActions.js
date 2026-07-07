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
  let batchPrefetchPromise = null;
  const queuedPosterItems = new Map();
  let posterFlushTimer = null;
  const POSTER_BATCH_SIZE = 16;
  const POSTER_FLUSH_MS = 120;

  function setModalTargetResolver(resolver) {
    modalTargetResolver = typeof resolver === 'function' ? resolver : () => null;
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
    return Boolean(seerStatusByRequest.value[key]) || isSeerStatusCacheFresh(statusCacheKeyFor(item));
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
    return formatSeerStatusLabel(status?.seer_status || 'not_found');
  }

  function canActionSeer(item) {
    return Boolean(getSeerStatus(item)?.can_action);
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

  async function loadSeerStatusForSource(source) {
    const target = getSeerModalTarget(source);
    if (!target) {
      applySeerStatus(null, { merge: false });
      return;
    }

    if (hasFreshSeerStatus(target)) {
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

  async function fetchBatchStatuses(items) {
    const keys = items.map((item) => seerRequestKey(item));
    const loadingState = { ...seerStatusLoadingByRequest.value };
    const errorState = { ...seerStatusErrorByRequest.value };
    keys.forEach((key) => {
      loadingState[key] = true;
      errorState[key] = '';
    });
    seerStatusLoadingByRequest.value = loadingState;
    seerStatusErrorByRequest.value = errorState;

    try {
      const response = await getRequestSeerStatusesBatch(items.map((item) => ({
        tmdb_id: item.request_id,
        media_type: item.media_type,
      })));
      for (const status of response.data?.statuses || []) {
        applySeerStatusFor(itemFromStatus(status), status, { merge: false });
      }
    } catch (error) {
      const message = error.response?.data?.message || 'Unavailable';
      const nextErrors = { ...seerStatusErrorByRequest.value };
      keys.forEach((key) => {
        nextErrors[key] = message;
      });
      seerStatusErrorByRequest.value = nextErrors;
    } finally {
      const nextLoading = { ...seerStatusLoadingByRequest.value };
      keys.forEach((key) => {
        nextLoading[key] = false;
      });
      seerStatusLoadingByRequest.value = nextLoading;
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
      void flushPosterSeerQueue();
    }, POSTER_FLUSH_MS);
  }

  async function flushPosterSeerQueue() {
    const pending = [...queuedPosterItems.values()].slice(0, POSTER_BATCH_SIZE);
    queuedPosterItems.clear();
    if (!pending.length) {
      return;
    }
    if (batchPrefetchPromise) {
      await batchPrefetchPromise;
    }
    batchPrefetchPromise = fetchBatchStatuses(pending);
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

  async function prefetchPosterSeerStatusesAsync(requests) {
    for (const item of (requests || [])) {
      queuePosterSeerStatus(item);
    }
    await flushPosterSeerQueue();
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
      await loadSeerStatusFor(item, { force: true });
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
      await loadSeerStatusFor(item, { force: true });
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
      seerStatus: status?.seer_status || '',
      seerBusy: isSeerBusy(item),
      seerCanAction: canActionSeer(item),
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
    queuePosterSeerStatus,
    posterSeerProps,
    applySeerStatus,
  };
}
