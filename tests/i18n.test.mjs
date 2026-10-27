import test from 'node:test';
import assert from 'node:assert/strict';
import {getLocale,localeKeyAudit,missingLocaleKeys,normalizeLocale,setLocale,t} from '../apps/desktop/dist/i18n.js';

test('host locale catalogs share stable keys and placeholders',()=>{
  assert.deepEqual(localeKeyAudit(),{matchingKeys:true,missingInEnglish:[],placeholderMismatches:[]});
});

test('locale selection normalizes supported English and Chinese entry points',()=>{
  assert.equal(normalizeLocale('en-GB'),'en-US');
  assert.equal(normalizeLocale('zh-Hans-CN'),'zh-CN');
  assert.equal(normalizeLocale('fr-FR'),'zh-CN');
});

test('host text changes locale while provider-owned text remains literal',()=>{
  setLocale('en-US');
  assert.equal(getLocale(),'en-US');
  assert.equal(t('status.connected'),'Connected');
  assert.equal(t('error.operation_failed',{message:'Provider-owned details'}),'Action not completed: Provider-owned details');
  assert.equal(t('provider.business.text'),'provider.business.text');
  assert.ok(missingLocaleKeys().includes('provider.business.text'));
  setLocale('zh-CN');
  assert.equal(t('status.connected'),'已连接');
});
