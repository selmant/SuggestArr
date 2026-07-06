/** Client-side Seer status cache shared across request pages. */

const CACHE_TTL_MS = 2 * 60 * 1000;
const cache = new Map();

/**
 * Build a stable cache key for a Seer status lookup.
 *
 * @param {string} tmdbId
 * @param {string} mediaType
 * @returns {string}
 */
export function seerStatusCacheKey(tmdbId, mediaType) {
  return `${mediaType}:${tmdbId}`;
}

/**
 * @param {string} key
 * @returns {boolean}
 */
export function isSeerStatusCacheFresh(key) {
  const entry = cache.get(key);
  if (!entry) {
    return false;
  }
  return (Date.now() - entry.fetchedAt) < CACHE_TTL_MS;
}

/**
 * @param {string} key
 * @returns {object|null}
 */
export function getCachedSeerStatus(key) {
  if (!isSeerStatusCacheFresh(key)) {
    cache.delete(key);
    return null;
  }
  return cache.get(key).status;
}

/**
 * @param {string} key
 * @param {object|null} status
 */
export function setCachedSeerStatus(key, status) {
  cache.set(key, {
    status,
    fetchedAt: Date.now(),
  });
}

/**
 * @param {string} tmdbId
 * @param {string} mediaType
 */
export function invalidateSeerStatusCacheForItem(tmdbId, mediaType) {
  cache.delete(seerStatusCacheKey(tmdbId, mediaType));
}

/**
 * Clear all cached Seer statuses (tests).
 */
export function clearSeerStatusCache() {
  cache.clear();
}
