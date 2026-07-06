import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const requestsPageSource = readFileSync(new URL('./RequestsPage.vue', import.meta.url), 'utf8');
const detailsModalSource = readFileSync(new URL('./common/RequestDetailsModal.vue', import.meta.url), 'utf8');
const requestPosterCardSource = readFileSync(new URL('./common/RequestPosterCard.vue', import.meta.url), 'utf8');
const traktActionsSource = readFileSync(new URL('../composables/useRequestTraktActions.js', import.meta.url), 'utf8');
const traktStarRatingSource = readFileSync(new URL('./common/TraktStarRating.vue', import.meta.url), 'utf8');
const traktRequestActionsCss = readFileSync(new URL('../assets/styles/traktRequestActions.css', import.meta.url), 'utf8');

test('request details modal renders Trakt actions for selected and related requests', () => {
  assert.match(requestsPageSource, /:trakt-modal-target="getTraktModalTarget\(selectedSource\)"/);
  assert.match(requestsPageSource, /:can-show-related-trakt="canShowRelatedTrakt"/);
  assert.match(requestsPageSource, /@set-related-trakt-watched="\(item, watched\) => setTraktWatchedFor\(item, watched\)"/);
  assert.match(requestsPageSource, /@rate-related-on-trakt="\(item, stars\) => rateRequestOnTraktFor\(item, stars\)"/);
  assert.match(traktActionsSource, /resolveTraktUserId/);
  assert.match(traktActionsSource, /listTraktMediaUsers/);
  assert.match(traktActionsSource, /starsFromTraktStatus/);

  assert.match(detailsModalSource, /v-if="traktModalTarget" class="trakt-action-strip trakt-action-strip--modal"/);
  assert.match(detailsModalSource, /v-if="canShowRelatedTrakt\(request\)" class="trakt-inline-actions"/);
  assert.match(detailsModalSource, /data-testid="trakt-action-strip"/);
  assert.match(detailsModalSource, /data-testid="trakt-mark-watched"/);
  assert.match(detailsModalSource, /@click\.stop="\$emit\('set-related-trakt-watched', request, !getTraktStatus\(request\)\?\.watched\)"/);
  assert.match(detailsModalSource, /TraktStarRating/);
  assert.match(detailsModalSource, /data-testid="trakt-star-rating-wrap"/);
  assert.match(detailsModalSource, /traktRequestActions\.css/);
  assert.match(requestPosterCardSource, /data-testid="trakt-poster-actions"/);
  assert.match(requestPosterCardSource, /data-testid="trakt-poster-rating"/);
  assert.match(requestPosterCardSource, /TraktStarRating/);
  assert.match(requestPosterCardSource, /trakt-poster-dock/);
  assert.match(requestPosterCardSource, /mediaTypeLabel/);
  assert.doesNotMatch(requestPosterCardSource, /item\.media_type\.charAt\(0\)\.toUpperCase\(\)/);
  assert.match(detailsModalSource, /request-details-modal__context-row--trakt/);
  assert.match(detailsModalSource, /Media type <strong>/);
  assert.match(detailsModalSource, /RatingBadges/);
  assert.match(detailsModalSource, /Trakt status <strong>/);
  assert.match(detailsModalSource, /traktStatusLabel/);
  assert.match(traktRequestActionsCss, /\.trakt-action-strip--modal/);
  assert.match(traktRequestActionsCss, /\.trakt-action-summary/);
  assert.match(traktStarRatingSource, /v-for="index in 5"/);
  assert.match(requestsPageSource, /useRequestTraktActions/);
  assert.match(requestsPageSource, /posterTraktProps/);
});
