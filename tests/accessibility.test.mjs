import test from 'node:test';
import assert from 'node:assert/strict';
import {nextUserFontScale,normalizeUserFontScale} from '../apps/desktop/dist/accessibility.js';

test('saved user font scale is bounded and rejects invalid values',()=>{
  assert.equal(normalizeUserFontScale('1.4'),1.4);
  assert.equal(normalizeUserFontScale('99'),2);
  assert.equal(normalizeUserFontScale('0.1'),0.8);
  assert.equal(normalizeUserFontScale('not-a-number'),null);
  assert.equal(normalizeUserFontScale(null),null);
});

test('zoom shortcuts preserve local override and reset to the provider theme',()=>{
  assert.equal(nextUserFontScale(null,'in'),1.1);
  assert.equal(nextUserFontScale(1.1,'out'),1);
  assert.equal(nextUserFontScale(2,'in'),2);
  assert.equal(nextUserFontScale(0.8,'out'),0.8);
  assert.equal(nextUserFontScale(1.6,'reset'),null);
});
