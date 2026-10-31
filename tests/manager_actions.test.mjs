import test from 'node:test';
import assert from 'node:assert/strict';
import {acceptedProviderDrop,copyManagerDescriptor,previewDroppedProvider} from '../apps/desktop/dist/manager_actions.js';

const snapshot=(system,data)=>({system,scene:{data}});

test('Given a drop in the manager, When it contains one .wcp file, Then it is sent to preview',async()=>{
  assert.equal(acceptedProviderDrop('drop',['C:/Downloads/demo.WCP']),'C:/Downloads/demo.WCP');
  assert.equal(acceptedProviderDrop('drop',['a.wcp','b.wcp']),null);
  assert.equal(acceptedProviderDrop('drop',['folder']),null);
  assert.equal(acceptedProviderDrop('over',['demo.wcp']),null);
  const calls=[];
  const api={};
  await previewDroppedProvider('C:/Downloads/demo.wcp',async(id,value)=>{calls.push([id,value]);return id;},async(id)=>calls.push(['wait',id]),api);
  assert.deepEqual(calls,[
    ['pack-path','C:/Downloads/demo.wcp'],['wait','pack-path'],
    ['pack-preview-action',null],['wait','pack-preview-action'],
  ]);
});

test('Given the World Manager copy control, When clicked, Then only the Host copies its descriptor path',async()=>{
  let copyRequests=0;
  const copyPath=async()=>{copyRequests+=1;};
  assert.equal(await copyManagerDescriptor(snapshot(true,{}),copyPath),true);
  assert.equal(copyRequests,1);
  assert.equal(await copyManagerDescriptor(snapshot(false,{}),copyPath),false);
  assert.equal(copyRequests,1);
});
