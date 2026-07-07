/** Client-side Trakt status cache shared across request pages. */

const CACHE_TTL_MS = 2 * 60 * 60 * 1000;
const cache = new Map();

/**
 * Build a stable cache key for a Trakt status lookup.
 *
 * @param {string} userId
 * @param {string} tmdbId
 * @param {string} mediaType
 * @returns {string}
 */
export function traktStatusCacheKey(userId, tmdbId, mediaType) {
  return `${userId}:${mediaType}:${tmdbId}`;
}

/**
 * @param {string} key
 * @returns {boolean}
 */
export function isTraktStatusCacheFresh(key) {
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
export function getCachedTraktStatus(key) {
  if (!isTraktStatusCacheFresh(key)) {
    cache.delete(key);
    return null;
  }
  return cache.get(key).status;
}

/**
 * @param {string} key
 * @param {object|null} status
 */
export function setCachedTraktStatus(key, status) {
  cache.set(key, {
    status,
    fetchedAt: Date.now(),
  });
}

/**
 * @param {string} userId
 * @param {string} tmdbId
 * @param {string} mediaType
 */
export function invalidateTraktStatusCacheForItem(userId, tmdbId, mediaType) {
  cache.delete(traktStatusCacheKey(userId, tmdbId, mediaType));
}

/**
 * @param {string} userId
 */
export function invalidateTraktStatusCacheForUser(userId) {
  const prefix = `${userId}:`;
  for (const key of cache.keys()) {
    if (key.startsWith(prefix)) {
      cache.delete(key);
    }
  }
}

/**
 * Clear all cached Trakt statuses (tests).
 */
export function clearTraktStatusCache() {
  cache.clear();
}
