import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const traktActionsSource = readFileSync(new URL('./useRequestTraktActions.js', import.meta.url), 'utf8');

test('trakt actions support forced refresh on load and modal fetch paths', () => {
  assert.match(traktActionsSource, /function prefetchPosterTraktStatuses\(requests, \{ force = false \}/);
  assert.match(traktActionsSource, /function queuePosterTraktStatus\(item, \{ force = false \}/);
  assert.match(traktActionsSource, /if \(force\) \{[\s\S]*invalidateTraktStatusForItem\(item\)/);
  assert.match(traktActionsSource, /applyTraktStatusFor\(item, response\.data, \{ merge: false \}\)/);
  assert.match(traktActionsSource, /applyTraktStatus\(response\.data, \{ merge: false \}\)/);
  assert.match(traktActionsSource, /overflow\.push\(item\)/);
  assert.match(traktActionsSource, /connected\.length > 0/);
  assert.match(traktActionsSource, /connectedTraktUserIds/);
  assert.match(traktActionsSource, /external_user_id/);
  assert.match(traktActionsSource, /\{ silent = false \}/);
  assert.match(traktActionsSource, /queueSilentTraktStatusUpdates/);
  assert.match(traktActionsSource, /isPosterSilentPrefetchActive/);
});
