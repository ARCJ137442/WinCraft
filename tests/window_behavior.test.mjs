import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeNativeContentHeight,normalizeNativeContentWidth,shouldShowConnectionStatus,titlebarMovementExceedsDragThreshold} from '../apps/desktop/dist/window_behavior.js';

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

test('native content fit clamps a compact shell to the titlebar minimum',()=>{
  assert.equal(normalizeNativeContentHeight(46),50);
  assert.equal(normalizeNativeContentHeight(50),50);
  assert.equal(normalizeNativeContentHeight(10_000),10_000);
  assert.equal(normalizeNativeContentHeight(10_001),null);
  assert.equal(normalizeNativeContentHeight(-1),null);
  assert.equal(normalizeNativeContentHeight(Number.NaN),null);
});

test('collapsed titlebar width respects native minimum and maximum bounds',()=>{
  assert.equal(normalizeNativeContentWidth(120),160);
  assert.equal(normalizeNativeContentWidth(240),240);
  assert.equal(normalizeNativeContentWidth(2_400),2_400);
  assert.equal(normalizeNativeContentWidth(2_401),null);
  assert.equal(normalizeNativeContentWidth(Number.NaN),null);
});
