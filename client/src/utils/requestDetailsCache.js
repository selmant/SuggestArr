import { getRequestDetails } from '@/api/api.js';

const CACHE_TTL_MS = 10 * 60 * 1000;
const cache = new Map();
const inflight = new Map();

function cacheKey(tmdbId, mediaType) {
  return `${mediaType}:${String(tmdbId)}`;
}

function isFresh(entry) {
  return entry && (Date.now() - entry.fetchedAt) < CACHE_TTL_MS;
}

export function getCachedRequestDetails(tmdbId, mediaType) {
  const key = cacheKey(tmdbId, mediaType);
  const entry = cache.get(key);
  if (!isFresh(entry)) {
    if (entry) {
      cache.delete(key);
    }
    return null;
  }
  return entry.value;
}

export async function getRequestDetailsCached(tmdbId, mediaType) {
  const key = cacheKey(tmdbId, mediaType);
  const cached = getCachedRequestDetails(tmdbId, mediaType);
  if (cached) {
    return cached;
  }

  if (inflight.has(key)) {
    return inflight.get(key);
  }

  const request = getRequestDetails(tmdbId, mediaType)
    .then((response) => {
      const value = response?.data || {};
      cache.set(key, { value, fetchedAt: Date.now() });
      return value;
    })
    .finally(() => {
      inflight.delete(key);
    });

  inflight.set(key, request);
  return request;
}

export function prefetchRequestDetails(tmdbId, mediaType) {
  if (!tmdbId || !mediaType) {
    return;
  }
  if (getCachedRequestDetails(tmdbId, mediaType)) {
    return;
  }
  const key = cacheKey(tmdbId, mediaType);
  if (inflight.has(key)) {
    return;
  }
  void getRequestDetailsCached(tmdbId, mediaType);
}
