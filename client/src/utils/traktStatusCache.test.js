import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  clearTraktStatusCache,
  getCachedTraktStatus,
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
