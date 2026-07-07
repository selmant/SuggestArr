import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  buildRatingBadges,
  getRatingBadgeSettings,
  getScoreQuality,
} from '../utils/ratingBadgeConfig.js';

test('getScoreQuality buckets normalized scores into good/mixed/bad', () => {
  assert.equal(getScoreQuality(85), 'good');
  assert.equal(getScoreQuality(60), 'good');
  assert.equal(getScoreQuality(59), 'mixed');
  assert.equal(getScoreQuality(40), 'mixed');
  assert.equal(getScoreQuality(39), 'bad');
  assert.equal(getScoreQuality(0), 'bad');
  assert.equal(getScoreQuality(null), null);
  assert.equal(getScoreQuality('n/a'), null);
});

test('buildRatingBadges tags each source with a normalized quality class', () => {
  const badges = buildRatingBadges(
    {
      rating: 8.2, // TMDB 0-10 -> 82 -> good
      imdb_rating: 5.5, // -> 55 -> mixed
      rt_rating: 30, // -> 30 -> bad
      metacritic_rating: 74, // -> good
    },
    {
      showTmdb: true,
      showImdb: true,
      showRt: true,
      showRtUser: false,
      showMetacritic: true,
      showTraktUser: true,
      showTraktCommunity: false,
    },
    3, // Trakt user raw 3/10 -> 30 -> bad (displayed as 1.5 stars)
  );

  const byKey = Object.fromEntries(badges.map((badge) => [badge.key, badge]));
  assert.equal(byKey.tmdb.quality, 'good');
  assert.equal(byKey.tmdb.qualityClassName, 'rating-badge--good');
  assert.equal(byKey.imdb.quality, 'mixed');
  assert.equal(byKey.rt.quality, 'bad');
  assert.equal(byKey.metacritic.quality, 'good');
  assert.equal(byKey['trakt-user'].quality, 'bad');
  assert.match(byKey.tmdb.title, /TMDB · High/);
});

test('getRatingBadgeSettings defaults all sources to enabled', () => {
  const settings = getRatingBadgeSettings({});
  assert.equal(settings.showTmdb, true);
  assert.equal(settings.showImdb, true);
  assert.equal(settings.showRt, true);
  assert.equal(settings.showRtUser, true);
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

test('buildRatingBadges includes RT audience score when enabled', () => {
  const badges = buildRatingBadges(
    { rt_rating: 87, rt_user_rating: 92 },
    {
      showTmdb: false,
      showImdb: false,
      showRt: true,
      showRtUser: true,
      showMetacritic: false,
      showTraktUser: false,
      showTraktCommunity: false,
    },
  );

  assert.deepEqual(
    badges.map((badge) => badge.key),
    ['rt', 'rt-user'],
  );
  assert.equal(badges.find((badge) => badge.key === 'rt-user').value, '92%');
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
      showRtUser: false,
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
