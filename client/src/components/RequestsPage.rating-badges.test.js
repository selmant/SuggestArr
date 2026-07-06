import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const requestsPageSource = readFileSync(new URL('./RequestsPage.vue', import.meta.url), 'utf8');
const requestPosterCardSource = readFileSync(new URL('./common/RequestPosterCard.vue', import.meta.url), 'utf8');
const detailsModalSource = readFileSync(new URL('./common/RequestDetailsModal.vue', import.meta.url), 'utf8');
const settingsAdvancedSource = readFileSync(new URL('./settings/SettingsAdvanced.vue', import.meta.url), 'utf8');

test('requests page wires rating badge settings into poster cards and modal', () => {
  assert.match(requestsPageSource, /getRatingBadgeSettings/);
  assert.match(requestsPageSource, /ratingBadgeSettings/);
  assert.match(requestsPageSource, /:badge-settings="ratingBadgeSettings"/);
  assert.match(requestsPageSource, /imdb_rating/);
  assert.match(requestPosterCardSource, /RatingBadges/);
  assert.match(requestPosterCardSource, /:badge-settings="badgeSettings"/);
  assert.match(detailsModalSource, /:badge-settings="badgeSettings"/);
  assert.match(settingsAdvancedSource, /SHOW_RATING_TMDB/);
  assert.match(settingsAdvancedSource, /SHOW_RATING_RT_USER/);
});
