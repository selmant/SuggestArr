import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  clearTraktStatusCache,
  getCachedTraktStatus,
  invalidateTraktStatusCacheForItem,
  isTraktStatusCacheFresh,
  setCachedTraktStatus,
  traktStatusCacheKey,
} from './traktStatusCache.js';

test('trakt status cache stores and expires entries by key', () => {
  clearTraktStatusCache();
  const key = traktStatusCacheKey('jf-1', '550', 'movie');
  setCachedTraktStatus(key, { watched: true, rating: 8 });

  assert.equal(isTraktStatusCacheFresh(key), true);
  assert.deepEqual(getCachedTraktStatus(key), { watched: true, rating: 8 });

  clearTraktStatusCache();
  assert.equal(getCachedTraktStatus(key), null);
});

test('trakt status cache can invalidate a single item', () => {
  clearTraktStatusCache();
  const key = traktStatusCacheKey('jf-1', '550', 'movie');
  const otherKey = traktStatusCacheKey('jf-1', '551', 'movie');
  setCachedTraktStatus(key, { watched: true });
  setCachedTraktStatus(otherKey, { watched: false });

  invalidateTraktStatusCacheForItem('jf-1', '550', 'movie');

  assert.equal(getCachedTraktStatus(key), null);
  assert.deepEqual(getCachedTraktStatus(otherKey), { watched: false });
});
