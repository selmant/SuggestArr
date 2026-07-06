import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const requestsPageSource = readFileSync(new URL('./RequestsPage.vue', import.meta.url), 'utf8');
const detailsModalSource = readFileSync(new URL('./common/RequestDetailsModal.vue', import.meta.url), 'utf8');
const requestPosterCardSource = readFileSync(new URL('./common/RequestPosterCard.vue', import.meta.url), 'utf8');

test('request details modal renders Trakt actions for selected and related requests', () => {
  assert.match(requestsPageSource, /:trakt-modal-target="getTraktModalTarget\(selectedSource\)"/);
  assert.match(requestsPageSource, /:can-show-related-trakt="canShowRelatedTrakt"/);
  assert.match(requestsPageSource, /@toggle-related-trakt-watched="toggleTraktWatchedFor"/);
  assert.match(requestsPageSource, /@rate-related-on-trakt="rateRequestOnTraktFromModal"/);
  assert.match(requestsPageSource, /resolveTraktUserId/);
  assert.match(requestsPageSource, /listTraktMediaUsers/);

  assert.match(detailsModalSource, /v-if="traktModalTarget" class="trakt-action-strip"/);
  assert.match(detailsModalSource, /v-if="canShowRelatedTrakt\(request\)" class="trakt-inline-actions"/);
  assert.match(detailsModalSource, /data-testid="trakt-action-strip"/);
  assert.match(detailsModalSource, /data-testid="trakt-mark-watched"/);
  assert.match(detailsModalSource, /@click\.stop="\$emit\('toggle-related-trakt-watched', request\)"/);
  assert.match(detailsModalSource, /@change\.stop="\$emit\('rate-related-on-trakt', request, \$event\)"/);
  assert.match(detailsModalSource, /traktRequestActions\.css/);
  assert.match(requestPosterCardSource, /data-testid="trakt-poster-actions"/);
  assert.match(requestPosterCardSource, /data-testid="trakt-poster-mark-watched"/);
  assert.match(requestsPageSource, /prefetchPosterTraktStatuses/);
});
