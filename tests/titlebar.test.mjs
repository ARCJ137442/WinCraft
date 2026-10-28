import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const html=readFileSync(new URL('../apps/desktop/index.html',import.meta.url),'utf8');
const css=readFileSync(new URL('../apps/desktop/style.css',import.meta.url),'utf8');

test('titlebar brand and controls use centered vector icons',()=>{
  assert.match(html,/<svg class="brand-mark" viewBox="0 0 16 16"/);
  assert.match(html,/id="minimize"[\s\S]*?<svg class="titlebar-icon" viewBox="0 0 16 16"/);
  assert.match(html,/id="close"[\s\S]*?<svg class="titlebar-icon" viewBox="0 0 16 16"/);
  assert.equal(html.includes('<span class="brand-mark"'),false);
  assert.match(css,/\.chrome\{[^}]*align-items:center/);
  assert.match(css,/\.drag\{[^}]*align-items:center/);
  assert.match(css,/\.minimize,\.close\{[^}]*align-items:center;justify-content:center/);
  assert.match(css,/\.brand-mark\{[^}]*width:16px;height:16px/);
  assert.match(css,/\.titlebar-icon\{[^}]*width:14px;height:14px/);
});
