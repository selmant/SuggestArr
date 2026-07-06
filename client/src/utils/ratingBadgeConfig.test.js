import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  buildRatingBadges,
  getRatingBadgeSettings,
} from '../utils/ratingBadgeConfig.js';

test('getRatingBadgeSettings defaults all sources to enabled', () => {
  const settings = getRatingBadgeSettings({});
  assert.equal(settings.showTmdb, true);
  assert.equal(settings.showImdb, true);
  assert.equal(settings.showRt, true);
  assert.equal(settings.showMetacritic, true);
  assert.equal(settings.showTraktUser, true);
  assert.equal(settings.showTraktCommunity, true);
});

test('getRatingBadgeSettings respects disabled toggles', () => {
  const settings = getRatingBadgeSettings({
    SHOW_RATING_TMDB: false,
    SHOW_RATING_IMDB: false,
  });
  assert.equal(settings.showTmdb, false);
  assert.equal(settings.showImdb, false);
  assert.equal(settings.showRt, true);
});

test('buildRatingBadges only includes enabled sources with values', () => {
  const badges = buildRatingBadges(
    {
      rating: 7.8,
      imdb_rating: 8.1,
      rt_rating: 87,
      metacritic_rating: 74,
      trakt_rating: 8.2,
    },
    {
      showTmdb: true,
      showImdb: true,
      showRt: false,
      showMetacritic: true,
      showTraktUser: true,
      showTraktCommunity: true,
    },
    9,
  );

  assert.deepEqual(
    badges.map((badge) => badge.key),
    ['tmdb', 'imdb', 'metacritic', 'trakt-community', 'trakt-user'],
  );
  assert.equal(badges.find((badge) => badge.key === 'imdb').value, '8.1');
  assert.equal(badges.find((badge) => badge.key === 'trakt-user').value, '4.5');
});
