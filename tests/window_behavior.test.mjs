import test from 'node:test';
import assert from 'node:assert/strict';
import {shouldShowConnectionStatus,titlebarMovementExceedsDragThreshold} from '../apps/desktop/dist/window_behavior.js';

test('healthy connection status is omitted while recovery states remain visible',()=>{
  assert.equal(shouldShowConnectionStatus('online'),false);
  assert.equal(shouldShowConnectionStatus('stale'),true);
  assert.equal(shouldShowConnectionStatus('vacant'),true);
  assert.equal(shouldShowConnectionStatus('startup'),true);
});

test('titlebar movement distinguishes a click from a real drag threshold',()=>{
  assert.equal(titlebarMovementExceedsDragThreshold(10,10,13,12),false);
  assert.equal(titlebarMovementExceedsDragThreshold(10,10,15,10),true);
});
