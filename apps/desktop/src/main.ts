import type {Snapshot} from './types.js';
import {displayActionFeedback,errorDetails,newer,type ActionFeedback} from './bindings.js';
import {SceneRenderer} from './renderer.js';
import {demoSnapshot,previewController} from './demo.js';
import {initializeAccessibility} from './accessibility.js';
import {getLocale,initializeLocale,setLocale,t} from './i18n.js';
import {allowsBackgroundWindowDrag,normalizeNativeContentHeight,normalizeNativeContentWidth,shouldShowConnectionStatus,titlebarMovementExceedsDragThreshold} from './window_behavior.js';

initializeAccessibility();
initializeLocale();

const mount=document.getElementById('scene')!;
const status=document.getElementById('status')!;
const statusLine=status.parentElement as HTMLElement;
const title=document.getElementById('title')!;
title.textContent=t('status.startup');
const dragBar=document.getElementById('drag')!;
const chrome=document.getElementById('chrome')!;
const brandMark=dragBar.querySelector<SVGSVGElement>('.brand-mark')!;
const minimizeButton=document.getElementById('minimize')!;
const closeButton=document.getElementById('close')!;
const errors=document.getElementById('error')!;
const actionStatus=document.getElementById('action-status')!;
const preview=document.getElementById('preview')!;
const frame=document.getElementById('world')!;
let current:Snapshot|null=null;
type InteractionSource='click'|'context_menu'|'escape'|'control_enter';
let interact:(id:string,value:unknown,source:InteractionSource)=>Promise<unknown>=async()=>{};
let actionId:string|null=null;
let actionFeedback:ActionFeedback|null=null;
let fitFrame=0;
let lastMeasuredHeight=0;
let lastMeasuredCollapsedWidth=0;
let contentCollapsed=false;
type DragSource='titlebar'|'background';
let pointerGesture:{pointerId:number;x:number;y:number;dragStarted:boolean;source:DragSource}|null=null;
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
    actionFeedback={state:'error',message:t('error.revision_conflict')};
    renderActionStatus(current);
    if(window.__TAURI__)void window.__TAURI__.core.invoke<Snapshot>('surface_snapshot').then(accept).catch(report);
    return;
  }
  actionFeedback={state:'error',message:fault.message?t('error.operation_failed',{message:fault.message}):t('error.action.failed')};
  renderActionStatus(current);
};
const sendInteraction=async(id:string,value:unknown,source:InteractionSource='click'):Promise<unknown>=>{
  actionId=null;
  actionFeedback={state:'pending',message:t('interaction.submitting')};
  errors.textContent='';errors.hidden=true;
  renderActionStatus(current);
  const eventId=await interact(id,value,source);
  actionId=typeof eventId==='string'?eventId:null;
  actionFeedback={state:'pending',message:t('interaction.pending')};
  const accepted=actionId?current?.actions.find(item=>item.id===actionId):undefined;
  if(accepted && accepted.status!=='pending')actionFeedback=null;
  renderActionStatus(current);
  return eventId;
};
const renderer=new SceneRenderer(mount,(id,value,source)=>sendInteraction(id,value,source),reportInteractionError);
document.addEventListener('contextmenu',event=>{
  event.preventDefault();
  renderer.handleContextMenu(event);
});
function contentHeight():number {
  const children=[...frame.children] as HTMLElement[];
  const frameStyle=getComputedStyle(frame);
  let height=(parseFloat(frameStyle.borderTopWidth)||0)+(parseFloat(frameStyle.borderBottomWidth)||0);
  for(const child of children){
    const style=getComputedStyle(child);
    if(child.hidden||style.display==='none')continue;
    // Screen-reader-only nodes use clipped boxes and negative margins; they do not occupy visible window height.
    if(child.classList.contains('sr-only'))continue;
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
function compactTitlebarWidth():number {
  const frameStyle=getComputedStyle(frame);
  const chromeStyle=getComputedStyle(chrome);
  const dragStyle=getComputedStyle(dragBar);
  const horizontalPadding=(parseFloat(chromeStyle.paddingLeft)||0)+(parseFloat(chromeStyle.paddingRight)||0);
  const frameBorders=(parseFloat(frameStyle.borderLeftWidth)||0)+(parseFloat(frameStyle.borderRightWidth)||0);
  const dragGap=parseFloat(dragStyle.columnGap||dragStyle.gap)||0;
  const titleWidth=Math.max(title.scrollWidth,title.getBoundingClientRect().width);
  return Math.ceil(frameBorders+horizontalPadding+brandMark.getBoundingClientRect().width+dragGap+titleWidth
    +minimizeButton.getBoundingClientRect().width+closeButton.getBoundingClientRect().width);
}
function scheduleContentFit(force=false):void {
  if(!window.__TAURI__)return;
  if(fitFrame)cancelAnimationFrame(fitFrame);
  fitFrame=requestAnimationFrame(()=>{
    fitFrame=requestAnimationFrame(()=>{
      fitFrame=0;
      const height=normalizeNativeContentHeight(contentHeight());
      if(height===null)return;
      if(contentCollapsed){
        const width=normalizeNativeContentWidth(compactTitlebarWidth());
        if(width===null||(!force&&Math.abs(height-lastMeasuredHeight)<1&&Math.abs(width-lastMeasuredCollapsedWidth)<1))return;
        lastMeasuredHeight=height;lastMeasuredCollapsedWidth=width;
        void window.__TAURI__!.core.invoke('surface_content_size',{collapsed:true,width,height}).catch(report);
        return;
      }
      if(force){
        lastMeasuredHeight=height;lastMeasuredCollapsedWidth=0;
        void window.__TAURI__!.core.invoke('surface_content_size',{collapsed:false,width:null,height:null})
          .then(()=>window.__TAURI__!.core.invoke('surface_content_height',{height,force:true}))
          .catch(report);
        return;
      }
      if(Math.abs(height-lastMeasuredHeight)<1)return;
      lastMeasuredHeight=height;
      void window.__TAURI__!.core.invoke('surface_content_height',{height,force}).catch(report);
    });
  });
}
function syncContentCollapse(forceResize=false):void {
  document.body.dataset.contentCollapsed=String(contentCollapsed);
  const key=contentCollapsed?'window.expand_content':'window.collapse_content';
  dragBar.setAttribute('aria-expanded',String(!contentCollapsed));
  dragBar.setAttribute('aria-label',`${title.textContent} · ${t(key)}`);
  dragBar.title=t(key);
  scheduleContentFit(forceResize);
}
function toggleContentCollapse():void {
  contentCollapsed=!contentCollapsed;
  syncContentCollapse(true);
}
syncContentCollapse();
if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>scheduleContentFit()).observe(frame);
function accept(next:Snapshot):void {
  if(!newer(current,next))return;
  current=next;title.textContent=next.window.title;
  syncContentCollapse();
  status.textContent=t(`status.${next.status}`);status.dataset.state=next.status;
  statusLine.hidden=!shouldShowConnectionStatus(next.status);
  frame.style.opacity=String(next.window.surface_opacity);
  frame.style.setProperty('--world-text-selection',next.window.text_selectable?'text':'none');
  frame.dataset.textSelectable=String(next.window.text_selectable);
  document.body.dataset.geometry=next.window.position_control??next.window.geometry_control;
  document.body.dataset.system=String(next.system);
  document.body.dataset.titleBarVisible=String(next.window.title_bar_visible);
  document.getElementById('drag')!.setAttribute('aria-label',t((next.window.position_control??next.window.geometry_control)==='human'?'geometry.drag_human':'geometry.drag_provider'));
  renderer.render(next);
  const tracked=actionId?next.actions.find(item=>item.id===actionId):undefined;
  if(tracked && tracked.status!=='pending')actionFeedback=null;
  renderActionStatus(next);
  if(next.native.state==='error')report(next.native.error??t('error.native_window'));
  document.getElementById('revision')!.textContent=`r${next.revision} · ${t(next.system?'revision.host_provider':'revision.declarative_world')}`;
  const data=next.scene.data&&typeof next.scene.data==='object'?next.scene.data as Record<string,unknown>:{};
  if(next.system&&typeof data.host_locale==='string'&&data.host_locale!==getLocale()){
    const locale=setLocale(data.host_locale,false);
    syncContentCollapse();
    if(window.__TAURI__)void window.__TAURI__.core.invoke('surface_locale_set',{locale}).catch(report);
  }
  scheduleContentFit();
}
async function start():Promise<void>{
  const api=window.__TAURI__;
  if(!api){
    preview.hidden=false;document.body.classList.add('preview-body');
    const sample=demoSnapshot(new URLSearchParams(location.search).get('preview')==='manager');
    interact=previewController(sample,accept);accept(sample);return;
  }
  void api.event.listen<string>('host/locale',event=>{setLocale(event.payload,false);syncContentCollapse();}).catch(report);
  void api.core.invoke<string>('surface_locale_get').then(locale=>setLocale(locale,false)).catch(report);
  interact=(nodeId,value,source)=>api.core.invoke('surface_interact',{nodeId,value,source,expectedRevision:current?.revision});
  // Subscribe before initial fetch; sequence ordering fences the fetch/event race.
  await api.event.listen<Snapshot>('world/snapshot',event=>accept(event.payload));
  accept(await api.core.invoke<Snapshot>('surface_snapshot'));
}
const interactiveTargetSelector='button,input,textarea,select,a,[role="button"],[contenteditable="true"]';
const textTargetSelector='#status-line,footer,#error,#action-status,.sr-only,.block-text,.block-badge,.metric-label,.metric-value,.metric-unit,.metric-caption,.progress-label,.chart-label,.chart-row-label,.chart-row-value,.kv-key-label,.kv-primary,.kv-secondary,.block-input label';
function isBackgroundDragAllowed(target:EventTarget|null):boolean {
  if(!(target instanceof Element)||!current)return false;
  const selection=window.getSelection();
  return allowsBackgroundWindowDrag({
    enabled:current.window.background_drag_enabled,
    positionControl:current.window.position_control??current.window.geometry_control,
    clickThrough:current.window.click_through,
    titleBar:target.closest('#chrome')!==null,
    interactive:target.closest(interactiveTargetSelector)!==null,
    text:target.closest(textTargetSelector)!==null,
    selectionActive:!!selection&&!selection.isCollapsed,
  });
}
function beginPointerGesture(event:PointerEvent,source:DragSource):void {
  if(event.button!==0)return;
  if(source==='titlebar'&&event.target instanceof Element&&event.target.closest('button'))return;
  if(source==='background'&&!isBackgroundDragAllowed(event.target))return;
  pointerGesture={pointerId:event.pointerId,x:event.clientX,y:event.clientY,dragStarted:false,source};
}
dragBar.addEventListener('pointerdown',event=>beginPointerGesture(event,'titlebar'));
frame.addEventListener('pointerdown',event=>beginPointerGesture(event,'background'));
window.addEventListener('pointermove',event=>{
  const gesture=pointerGesture;
  if(!gesture||gesture.pointerId!==event.pointerId||gesture.dragStarted)return;
  if(!titlebarMovementExceedsDragThreshold(gesture.x,gesture.y,event.clientX,event.clientY))return;
  gesture.dragStarted=true;
  if(current&&(current.window.position_control??current.window.geometry_control)==='human'&&!current.window.click_through&&window.__TAURI__){
    void window.__TAURI__.core.invoke('surface_drag',{dragSource:gesture.source}).catch(report);
  }
});
window.addEventListener('pointerup',event=>{
  const gesture=pointerGesture;
  if(!gesture||gesture.pointerId!==event.pointerId)return;
  pointerGesture=null;
  if(gesture.source==='titlebar'&&!gesture.dragStarted)toggleContentCollapse();
});
window.addEventListener('pointercancel',event=>{
  if(pointerGesture?.pointerId===event.pointerId)pointerGesture=null;
});
dragBar.addEventListener('keydown',event=>{
  if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleContentCollapse();}
});
document.getElementById('close')!.addEventListener('click',()=>{
  if(window.__TAURI__)void window.__TAURI__.core.invoke('surface_close').catch(report);
  else report(t('error.preview_close'));
});
document.getElementById('minimize')!.addEventListener('click',()=>{
  if(window.__TAURI__)void window.__TAURI__.core.invoke('surface_minimize').catch(report);
  else report(t('error.preview_minimize'));
});
void start().catch(report);
