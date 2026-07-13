import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const seerActionsSource = readFileSync(new URL('./useRequestSeerActions.js', import.meta.url), 'utf8');

test('canActionSeer falls back to stored pending before live status loads', () => {
  assert.match(seerActionsSource, /function canActionSeer\(item\)/);
  assert.match(seerActionsSource, /if \(status\) \{[\s\S]*return Boolean\(status\.can_action\)/);
  assert.match(seerActionsSource, /return item\?\.seer_status === 'pending'/);
});

test('hasFreshSeerStatus invalidates cache when stored status disagrees', () => {
  assert.match(seerActionsSource, /stored !== resolved\.seer_status/);
  assert.match(seerActionsSource, /stored === 'pending' && resolved\.seer_status === 'pending' && !resolved\.can_action/);
});

test('decline protects the optimistic declined state from stale pending refreshes', () => {
  assert.match(seerActionsSource, /const recentDeclines = new Map\(\)/);
  assert.match(seerActionsSource, /status\?\.seer_status === 'pending' && recentDeclineAt/);
  assert.match(seerActionsSource, /recentDeclines\.set\(key, Date\.now\(\)\)/);
});
