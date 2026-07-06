import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const source = readFileSync(new URL('./RequestsPage.vue', import.meta.url), 'utf8');

test('grouped request modal renders Trakt actions for each request row', () => {
  assert.match(source, /v-if="canManageTrakt\(request\)" class="trakt-inline-actions"/);
  assert.match(source, /@click\.stop="toggleTraktWatchedFor\(request\)"/);
  assert.match(source, /@change\.stop="rateRequestOnTraktFromModal\(request, \$event\)"/);
});
