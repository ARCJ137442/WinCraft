import type {Snapshot} from './types.js';
import {displayActionFeedback,errorDetails,newer,type ActionFeedback} from './bindings.js';
import {SceneRenderer} from './renderer.js';
import {demoSnapshot,previewController} from './demo.js';

const mount=document.getElementById('scene')!;
const status=document.getElementById('status')!;
const title=document.getElementById('title')!;
const errors=document.getElementById('error')!;
const actionStatus=document.getElementById('action-status')!;
const preview=document.getElementById('preview')!;
const frame=document.getElementById('world')!;
let current:Snapshot|null=null;
let interact:(id:string,value:unknown,contextAction:boolean)=>Promise<unknown>=async()=>{};
let actionId:string|null=null;
let actionFeedback:ActionFeedback|null=null;
let fitFrame=0;
let lastMeasuredHeight=0;
const renderActionStatus=(snapshot:Snapshot|null=current):void=>{
  const feedback=displayActionFeedback(snapshot?.actions??[],actionId,actionFeedback);
  actionStatus.textContent=feedback?.message??'';
  actionStatus.dataset.state=feedback?.state??'';
};
const report=(error:unknown)=>{errors.textContent=errorDetails(error).message;errors.hidden=false;};
const reportInteractionError=(error:unknown):void=>{
  const fault=errorDetails(error);
  actionId=null;
  errors.textContent='';errors.hidden=true;
  if(fault.code==='REVISION_CONFLICT'){
    actionFeedback={state:'error',message:'界面刚更新，本次操作未执行。请确认最新状态后重试。'};
    renderActionStatus(current);
    if(window.__TAURI__)void window.__TAURI__.core.invoke<Snapshot>('surface_snapshot').then(accept).catch(report);
    return;
  }
  actionFeedback={state:'error',message:fault.message?`操作未完成：${fault.message}`:'操作未完成'};
  renderActionStatus(current);
};
const sendInteraction=async(id:string,value:unknown,contextAction=false):Promise<unknown>=>{
  actionId=null;
  actionFeedback={state:'pending',message:'正在提交操作…'};
  errors.textContent='';errors.hidden=true;
  renderActionStatus(current);
  const eventId=await interact(id,value,contextAction);
  actionId=typeof eventId==='string'?eventId:null;
  actionFeedback={state:'pending',message:'等待提供者确认'};
  const accepted=actionId?current?.actions.find(item=>item.id===actionId):undefined;
  if(accepted && accepted.status!=='pending')actionFeedback=null;
  renderActionStatus(current);
  return eventId;
};
const renderer=new SceneRenderer(mount,(id,value,contextAction)=>sendInteraction(id,value,contextAction),reportInteractionError);
document.addEventListener('contextmenu',event=>{
  event.preventDefault();
  renderer.handleContextMenu(event);
});
function contentHeight():number {
  const children=[...frame.children] as HTMLElement[];
  const frameStyle=getComputedStyle(frame);
  let height=(parseFloat(frameStyle.borderTopWidth)||0)+(parseFloat(frameStyle.borderBottomWidth)||0);
  for(const child of children){
    if(child.hidden||getComputedStyle(child).display==='none')continue;
    const style=getComputedStyle(child);
    const margins=(parseFloat(style.marginTop)||0)+(parseFloat(style.marginBottom)||0);
    if(child===mount){
      const root=mount.firstElementChild as HTMLElement|null;
      const sceneStyle=getComputedStyle(mount);
      height+=(root?.getBoundingClientRect().height??0)
        +(parseFloat(sceneStyle.paddingTop)||0)+(parseFloat(sceneStyle.paddingBottom)||0)
        +(parseFloat(sceneStyle.borderTopWidth)||0)+(parseFloat(sceneStyle.borderBottomWidth)||0)
        +margins;
    }else height+=child.getBoundingClientRect().height+margins;
  }
  return Math.ceil(height);
}
function scheduleContentFit():void {
  if(!window.__TAURI__)return;
  if(fitFrame)cancelAnimationFrame(fitFrame);
  fitFrame=requestAnimationFrame(()=>{
    fitFrame=requestAnimationFrame(()=>{
      fitFrame=0;
      const height=contentHeight();
      if(!Number.isFinite(height)||height<80||height>10000||Math.abs(height-lastMeasuredHeight)<1)return;
      lastMeasuredHeight=height;
      void window.__TAURI__!.core.invoke('surface_content_height',{height}).catch(report);
    });
  });
}
if(typeof ResizeObserver!=='undefined')new ResizeObserver(scheduleContentFit).observe(frame);
function accept(next:Snapshot):void {
  if(!newer(current,next))return;
  current=next;title.textContent=next.window.title;
  const labels={online:'已连接',stale:'来源断开 · 保留最后状态',vacant:'等待提供者'};
  status.textContent=labels[next.status];status.dataset.state=next.status;
  frame.style.opacity=String(next.window.surface_opacity);
  document.body.dataset.geometry=next.window.geometry_control;
  document.body.dataset.system=String(next.system);
  document.body.dataset.titleBarVisible=String(next.window.title_bar_visible);
  document.getElementById('drag')!.setAttribute('aria-label',next.window.geometry_control==='human'?'拖动窗口':'窗口位置由提供者控制');
  renderer.render(next);
  const tracked=actionId?next.actions.find(item=>item.id===actionId):undefined;
  if(tracked && tracked.status!=='pending')actionFeedback=null;
  renderActionStatus(next);
  if(next.native.state==='error')report(next.native.error??'原生窗口应用失败');
  document.getElementById('revision')!.textContent=`r${next.revision} · ${next.system?'宿主自身提供者':'声明式组件世界'}`;
  scheduleContentFit();
}
async function start():Promise<void>{
  const api=window.__TAURI__;
  if(!api){
    preview.hidden=false;document.body.classList.add('preview-body');
    const sample=demoSnapshot(new URLSearchParams(location.search).get('preview')==='manager');
    interact=previewController(sample,accept);accept(sample);return;
  }
  interact=(nodeId,value,contextAction)=>api.core.invoke('surface_interact',{nodeId,value,contextAction,expectedRevision:current?.revision});
  // Subscribe before initial fetch; sequence ordering fences the fetch/event race.
  await api.event.listen<Snapshot>('world/snapshot',event=>accept(event.payload));
  accept(await api.core.invoke<Snapshot>('surface_snapshot'));
}
document.getElementById('drag')!.addEventListener('mousedown',event=>{
  if(event.button===0 && current?.window.geometry_control==='human' && window.__TAURI__){
    void window.__TAURI__.core.invoke('surface_drag').catch(report);
  }
});
document.getElementById('close')!.addEventListener('click',()=>{
  if(window.__TAURI__)void window.__TAURI__.core.invoke('surface_close').catch(report);
  else report('浏览器预览没有原生窗口可关闭。');
});
document.getElementById('minimize')!.addEventListener('click',()=>{
  if(window.__TAURI__)void window.__TAURI__.core.invoke('surface_minimize').catch(report);
  else report('浏览器预览没有原生窗口可最小化。');
});
void start().catch(report);
