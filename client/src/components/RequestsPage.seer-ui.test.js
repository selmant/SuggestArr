import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const requestsPageSource = readFileSync(new URL('./RequestsPage.vue', import.meta.url), 'utf8');
const detailsModalSource = readFileSync(new URL('./common/RequestDetailsModal.vue', import.meta.url), 'utf8');
const requestPosterCardSource = readFileSync(new URL('./common/RequestPosterCard.vue', import.meta.url), 'utf8');
const seerActionsSource = readFileSync(new URL('../composables/useRequestSeerActions.js', import.meta.url), 'utf8');

test('request details modal renders Seer actions for selected and related requests', () => {
  assert.match(requestsPageSource, /:seer-modal-target="getSeerModalTarget\(selectedSource\)"/);
  assert.match(requestsPageSource, /:can-show-related-seer="canShowRelatedSeer"/);
  assert.match(requestsPageSource, /@approve-related-seer="approveFor"/);
  assert.match(requestsPageSource, /@decline-related-seer="declineFor"/);
  assert.match(seerActionsSource, /getRequestSeerStatusesBatch/);
  assert.match(seerActionsSource, /approveSeerRequest/);
  assert.match(seerActionsSource, /declineSeerRequest/);

  assert.match(detailsModalSource, /v-if="seerModalTarget" class="[^"]*seer-action-strip/);
  assert.match(detailsModalSource, /v-if="canShowRelatedSeer\(request\)" class="seer-inline-actions"/);
  assert.match(detailsModalSource, /data-testid="seer-action-strip"/);
  assert.match(detailsModalSource, /data-testid="seer-approve"/);
  assert.match(detailsModalSource, /data-testid="seer-decline"/);
  assert.match(detailsModalSource, /@click\.stop="\$emit\('approve-related-seer', request\)"/);
  assert.match(detailsModalSource, /seerRequestActions\.css/);
  assert.match(requestPosterCardSource, /data-testid="seer-poster-actions"/);
  assert.match(requestPosterCardSource, /data-testid="seer-poster-approve"/);
  assert.match(requestPosterCardSource, /seer-poster-dock/);
  assert.match(requestsPageSource, /useRequestSeerActions/);
  assert.match(requestsPageSource, /posterSeerProps/);
  assert.match(requestsPageSource, /prefetchPosterSeerStatuses\(mapped\)/);
  assert.match(requestsPageSource, /seer_status: request\.seer_status/);
  assert.doesNotMatch(requestsPageSource, /@visible="onRequestCardVisible"/);
  assert.match(requestsPageSource, /seerStatusFilter/);
  assert.match(requestsPageSource, /SEER_STATUS_FILTER_OPTIONS/);
  assert.match(requestsPageSource, /filterRequestList/);
});
