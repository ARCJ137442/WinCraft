import type {Snapshot,TauriApi} from './types.js';

export function acceptedProviderDrop(type:string,paths:readonly string[]):string|null {
  if(type!=='drop'||paths.length!==1)return null;
  const path=paths[0];
  return path&&path.toLowerCase().endsWith('.wcp')?path:null;
}

export async function copyManagerDescriptor(snapshot:Snapshot|null,copyPath:()=>Promise<unknown>):Promise<boolean> {
  if(!snapshot?.system)return false;
  await copyPath();
  return true;
}

export async function previewDroppedProvider(
  path:string,
  send:(nodeId:string,value:unknown)=>Promise<unknown>,
  wait:(eventId:string,api:TauriApi)=>Promise<void>,
  api:TauriApi,
):Promise<void> {
  const pathEvent=await send('pack-path',path);
  if(typeof pathEvent==='string')await wait(pathEvent,api);
  const previewEvent=await send('pack-preview-action',null);
  if(typeof previewEvent==='string')await wait(previewEvent,api);
}
