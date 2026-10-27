import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {resolve,text,progress,clamp,newer,tone,number,errorDetails,displayActionFeedback} from '../apps/desktop/dist/bindings.js';
test('all linked stylesheets are included in the built Tauri frontend',()=>{
  const index=new URL('../apps/desktop/dist/index.html',import.meta.url);
  const html=readFileSync(index,'utf8');
  for(const [,href] of html.matchAll(/<link[^>]+href="([^"]+)"/gu)){
    assert.ok(existsSync(new URL(href,index)),`missing built stylesheet ${href}`);
  }
  const buildId=readFileSync(new URL('../apps/desktop/dist/build-id.txt',import.meta.url),'utf8').trim();
  assert.match(buildId,/^\d{8}T\d{9}Z$/u);
});
test('literal values stay literal',()=>{assert.equal(resolve('x',{}),'x');assert.equal(resolve(4,{}),4);});
test('JSON pointer reads nested fields and arrays',()=>{assert.equal(resolve({$path:'/a/0/value'},{a:[{value:42}]}),42);});
test('escaped pointer fields',()=>{assert.equal(resolve({$path:'/a~1b/~0key'},{'a/b':{'~key':3}}),3);});
test('missing and malformed paths produce undefined',()=>{assert.equal(resolve({$path:'/missing'},{}),undefined);assert.equal(resolve({$path:'bad'},{}),undefined);assert.equal(resolve({$path:'/bad~4'},{}),undefined);});
test('prototype traversal is forbidden',()=>{assert.equal(resolve({$path:'/__proto__/x'},{}),undefined);assert.equal(resolve({$path:'/constructor'},{}),undefined);});
test('root pointer',()=>{const data={x:1};assert.equal(resolve({$path:''},data),data);});
test('progress is finite and bounded',()=>{assert.equal(progress(40,80),50);assert.equal(progress(-10,100),0);assert.equal(progress(500,100),100);assert.equal(progress(50,0),0);assert.equal(progress(NaN,100),0);});
test('number parser does not execute/coerce strings',()=>{assert.equal(number('10',9),9);assert.equal(number(Infinity,9),9);assert.equal(clamp(5,0,3),3);});
test('tone whitelist does not become raw CSS',()=>{assert.equal(tone('danger'),'danger');assert.equal(tone('url(https://evil)'), 'normal');});
test('nulls and structs have deterministic text',()=>{assert.equal(text(null),'—');assert.equal(text({a:1}),'{"a":1}');assert.equal(text('<script/>'),'<script/>');});
test('late initial fetch cannot replace event state',()=>{assert.equal(newer({id:'w',sequence:10},{id:'w',sequence:9}),false);assert.equal(newer({id:'w',sequence:10},{id:'w',sequence:10}),false);assert.equal(newer({id:'w',sequence:10},{id:'w',sequence:11}),true);});
test('cross-world snapshot rejected after first binding',()=>{assert.equal(newer({id:'w',sequence:1},{id:'other',sequence:99}),false);assert.equal(newer(null,{id:'w',sequence:1}),true);});
test('Tauri fault objects and JSON strings preserve code and message',()=>{
  const expected={code:'REVISION_CONFLICT',message:'expected 1653, actual 1654'};
  for(const actual of [expected,JSON.stringify(expected),new Error(JSON.stringify(expected))]){
    const result=errorDetails(actual);
    assert.equal(result.code,expected.code);
    assert.match(result.message,/界面刚更新/u);
    assert.ok(result.message.includes(expected.message));
  }
});
test('ordinary errors stay readable',()=>{
  assert.deepEqual(errorDetails('offline'),{code:null,message:'offline'});
  assert.deepEqual(errorDetails(new Error('offline')),{code:null,message:'offline'});
});
test('local conflict notice overrides an older acknowledged action',()=>{
  const oldAck={id:'old',status:'ok',message:null};
  const notice={state:'error',message:'界面刚更新，本次操作未执行。'};
  assert.deepEqual(displayActionFeedback([oldAck],null,notice),notice);
});
test('tracked action status does not borrow another action acknowledgement',()=>{
  const actions=[
    {id:'sent',status:'pending',message:null},
    {id:'other',status:'ok',message:null},
  ];
  assert.deepEqual(displayActionFeedback(actions,'sent',null),{state:'pending',message:'等待提供者确认'});
});
