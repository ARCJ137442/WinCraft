import {clamp,number,progress,resolve,text,tone} from './bindings.js';
import {t} from './i18n.js';
import type {ComponentNode,Kind,Snapshot,ThemeTokens} from './types.js';

type InteractionSource='click'|'context_menu'|'escape'|'control_enter';
type Interact=(nodeId:string,value:unknown,source:InteractionSource)=>Promise<unknown>;
const TEXTAREA_MAX_LENGTH=8192;
const THEME_COLOR=/^#[0-9a-f]{6}$/i;
const THEME_CSS_PROPERTIES=[
  '--wc-theme-background','--wc-theme-foreground','--wc-theme-accent',
  '--wc-theme-font-scale','--wc-theme-radius','--wc-theme-spacing-scale',
] as const;
const ICON_PATHS:Readonly<Record<string,readonly string[]>>={
  pin:['M8 3.5h8l-.8 4.2 2.3 2.3v1.5H6.5V10l2.3-2.3z','M12 11.5V21'],
  link:['M10 13.5a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.7 1.7','M14 10.5a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.7-1.7'],
  external:['M14 3h7v7','M10 14 21 3','M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6'],
  clock:['M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18','M12 7v5l3 2'],
  check:['M5 12.5 10 17l9-10'],
};
interface View {
  kind:Kind; element:HTMLElement; parts:Record<string,HTMLElement>;
  contextAction?:string; shortcut?:string; selectionGroup?:string; selectionMode?:'single'|'multiple'; pressed?:boolean;
  dirty?:boolean; composing?:boolean; submitted?:string;
}
function element<K extends keyof HTMLElementTagNameMap>(tag:K,cls=''):HTMLElementTagNameMap[K] {
  const el=document.createElement(tag);el.className=cls;return el;
}
function write(el:HTMLElement|undefined,value:string):void { if(el && el.textContent!==value)el.textContent=value; }
function createVectorIcon(name:unknown,label?:unknown):SVGSVGElement|null {
  if(typeof name!=='string'||!Object.hasOwn(ICON_PATHS,name))return null;
  const paths=ICON_PATHS[name];if(!paths)return null;
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width','16');svg.setAttribute('height','16');
  svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.8');
  svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');
  if(typeof label==='string'&&label.length){svg.setAttribute('role','img');svg.setAttribute('aria-label',label);}
  else svg.setAttribute('aria-hidden','true');
  for(const data of paths){const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',data);svg.append(path);}
  return svg;
}
function themeRgb(value:unknown):[number,number,number]|null {
  if(typeof value!=='string'||!THEME_COLOR.test(value))return null;
  return [1,3,5].map(offset=>Number.parseInt(value.slice(offset,offset+2),16)) as [number,number,number];
}
function linearChannel(value:number):number {
  const srgb=value/255;
  return srgb<=0.04045?srgb/12.92:((srgb+0.055)/1.055)**2.4;
}
function contrastRatio(first:[number,number,number],second:[number,number,number]):number {
  const luminance=(color:[number,number,number])=>
    0.2126*linearChannel(color[0])+0.7152*linearChannel(color[1])+0.0722*linearChannel(color[2]);
  const a=luminance(first);const b=luminance(second);
  return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
}
function validTheme(theme:ThemeTokens|undefined):theme is ThemeTokens {
  if(!theme||typeof theme!=='object')return false;
  const background=themeRgb(theme.background);const foreground=themeRgb(theme.foreground);const accent=themeRgb(theme.accent);
  return Boolean(background&&foreground&&accent
    &&Number.isFinite(theme.font_scale)&&theme.font_scale>=0.9&&theme.font_scale<=2
    &&Number.isInteger(theme.radius_px)&&theme.radius_px>=0&&theme.radius_px<=32
    &&Number.isInteger(theme.spacing_px)&&theme.spacing_px>=0&&theme.spacing_px<=32
    &&contrastRatio(background,foreground)>=4.5&&contrastRatio(background,accent)>=4.5);
}

/** Stable keys preserve input drafts and DOM identity while other providers' data changes.
 * Scope is one world; different worlds have different maps and WebViews.
 */
export class SceneRenderer {
  private views=new Map<string,View>();
  private order:string[]=[];
  private pendingFocusRestore=new Map<string,{componentId:string;target:HTMLElement}>();
  private pendingActions=new Map<string,string>();
  private snapshot:Snapshot|null=null;
  private inFlight=new Set<string>();
  private themeSpacingScale=1;
  constructor(private mount:HTMLElement,private interact:Interact,private onError:(e:unknown)=>void){
    mount.addEventListener('keydown',this.handleKeyDown);
  }
  private handleKeyDown=(event:KeyboardEvent):void=>{
    if(event.isComposing||event.defaultPrevented)return;
    const target=event.target instanceof Element?event.target.closest<HTMLElement>('[data-component-id]'):null;
    const nodeId=target?.dataset.componentId;
    const view=nodeId?this.views.get(nodeId):undefined;
    if(event.key==='Escape'&&!event.altKey&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey){
      for(const [id,candidate] of this.views){
        if(candidate.kind==='button'&&candidate.shortcut==='escape'){
          event.preventDefault();void this.send(id,null,'escape');return;
        }
      }
    }
    if(event.key==='Enter'&&event.ctrlKey&&!event.altKey&&!event.metaKey&&!event.shiftKey&&view?.kind==='textarea'&&view.shortcut==='ctrl_enter'){
      event.preventDefault();void this.send(nodeId!, (view.parts.input as HTMLTextAreaElement).value, 'control_enter');return;
    }
    if(view?.kind==='button'&&view.selectionGroup&&view.selectionMode&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key)){
      const siblings=this.order.filter(id=>this.views.get(id)?.selectionGroup===view.selectionGroup);
      const current=siblings.indexOf(nodeId!);
      if(current<0||siblings.length<2)return;
      const backwards=event.key==='ArrowUp'||event.key==='ArrowLeft';
      const nextIndex=(current+(backwards?siblings.length-1:1))%siblings.length;
      const nextId=siblings[nextIndex];
      if(!nextId)return;
      const next=this.views.get(nextId);
      if(!next)return;
      event.preventDefault();next.element.focus();
      if(view.selectionMode==='single')void this.send(nextId,null);
    }
  };
  render(snapshot:Snapshot):void {
    this.snapshot=snapshot;
    for(const [componentId,eventId] of this.pendingActions){
      const action=snapshot.actions.find(candidate=>candidate.id===eventId);
      if(action&&action.status!=='pending'){
        this.pendingActions.delete(componentId);
        this.inFlight.delete(componentId);
      }
    }
    this.applyTheme(snapshot.scene.theme);
    const seen=new Set<string>();
    const order:string[]=[];
    const walk=(node:ComponentNode):HTMLElement=>{
      seen.add(node.id);
      order.push(node.id);
      let view=this.views.get(node.id);
      if(!view || view.kind!==node.kind) {
        view?.element.remove();
        view=this.create(node);this.views.set(node.id,view);
      }
      view.element.dataset.componentId=node.id;
      const p:Record<string,unknown>={};
      for(const [key,value] of Object.entries(node.props))p[key]=resolve(value,snapshot.scene.data);
      this.update(view,node,p,snapshot);
      if(node.kind==='stack'||node.kind==='row') {
        node.children.forEach((child,index)=>{
          const childElement=walk(child);
          if(view!.element.children[index]!==childElement)view!.element.insertBefore(childElement,view!.element.children[index]??null);
        });
        while(view.element.children.length>node.children.length)view.element.lastElementChild?.remove();
      }
      return view.element;
    };
    const root=walk(snapshot.scene.root);
    this.order=order;
    if(this.mount.firstElementChild!==root)this.mount.replaceChildren(root);
    for(const [id,view] of this.views)if(!seen.has(id)){
      view.element.remove();this.views.delete(id);this.inFlight.delete(id);this.pendingActions.delete(id);
    }
    this.applySelectionTabStops(order);
    for(const [eventId,pending] of this.pendingFocusRestore){
      if(!this.views.has(pending.componentId)){this.pendingFocusRestore.delete(eventId);continue;}
      const action=snapshot.actions.find(candidate=>candidate.id===eventId);
      if(!action||action.status==='pending')continue;
      const active=document.activeElement;
      const focusStillBelongsToAction=active===pending.target;
      if(snapshot.status==='online'&&focusStillBelongsToAction&&this.mount.contains(pending.target)&&!pending.target.matches(':disabled'))pending.target.focus();
      this.pendingFocusRestore.delete(eventId);
    }
  }
  private applyTheme(theme:ThemeTokens|undefined):void {
    if(!validTheme(theme)){
      for(const property of THEME_CSS_PROPERTIES)this.mount.style.removeProperty(property);
      this.themeSpacingScale=1;return;
    }
    this.mount.style.setProperty('--wc-theme-background',theme.background);
    this.mount.style.setProperty('--wc-theme-foreground',theme.foreground);
    this.mount.style.setProperty('--wc-theme-accent',theme.accent);
    this.mount.style.setProperty('--wc-theme-font-scale',String(theme.font_scale));
    this.mount.style.setProperty('--wc-theme-radius',`${theme.radius_px}px`);
    this.mount.style.setProperty('--wc-theme-spacing-scale',String(theme.spacing_px/12));
    this.themeSpacingScale=theme.spacing_px/12;
  }
  private applySelectionTabStops(order:string[]):void{
    const groups=new Map<string,string[]>();
    for(const id of order){const group=this.views.get(id)?.selectionGroup;if(group){const members=groups.get(group)??[];members.push(id);groups.set(group,members);}}
    for(const ids of groups.values()){
      const primary=ids.find(id=>this.views.get(id)?.pressed)??ids[0];
      for(const id of ids){const view=this.views.get(id);if(view)view.element.tabIndex=id===primary?0:-1;}
    }
  }
  handleContextMenu(event:MouseEvent):void {
    const target=event.target;
    if(!(target instanceof Element))return;
    const nodeId=target.closest<HTMLElement>('[data-component-id]')?.dataset.componentId;
    if(!nodeId)return;
    const view=this.views.get(nodeId);
    if(!view?.contextAction)return;
    const value=view.kind==='input'||view.kind==='textarea'?(view.parts.input as HTMLInputElement|HTMLTextAreaElement).value:null;
    void this.send(nodeId,value,'context_menu');
  }
  private create(node:ComponentNode):View {
    const parts:Record<string,HTMLElement>={};
    let el:HTMLElement;
    switch(node.kind) {
      case 'stack': case 'row': el=element('div',`block-${node.kind}`);break;
      case 'text':el=element('p','block-text');break;
      case 'badge':el=element('span','block-badge');break;
      case 'divider':el=element('hr','block-divider');break;
      case 'metric':{
        el=element('article','block-metric');parts.label=element('p','metric-label');
        const line=element('div','metric-line');parts.value=element('strong','metric-value');parts.unit=element('span','metric-unit');
        line.append(parts.value,parts.unit);parts.caption=element('p','metric-caption');el.append(parts.label,line,parts.caption);break;
      }
      case 'progress':{
        el=element('div','block-progress');const line=element('div','progress-label');
        parts.label=element('span');parts.value=element('span');line.append(parts.label,parts.value);
        const track=element('div','progress-track');parts.fill=element('div','progress-fill');track.append(parts.fill);
        el.append(line,track);el.setAttribute('role','progressbar');break;
      }
      case 'icon':el=element('span','block-icon');break;
      case 'bar_chart':{
        el=element('figure','block-bar-chart');parts.label=element('figcaption','chart-label');el.append(parts.label);break;
      }
      case 'button':{
        const button=element('button','block-button');button.type='button';
        button.addEventListener('click',()=>void this.send(node.id,null));el=button;break;
      }
      case 'input':{
        el=element('div','block-input');parts.label=element('label');const row=element('div','input-row');
        const input=element('input');input.type='text';input.maxLength=1024;input.id=`input-${node.id}`;
        parts.label.setAttribute('for',input.id);
        const submit=element('button','block-button compact');submit.type='button';submit.textContent=t('input.submit');
        parts.input=input;parts.submit=submit;
        const doSubmit=()=>{const view=this.views.get(node.id);if(view && !view.composing){view.submitted=input.value;void this.send(node.id,input.value);}};
        input.addEventListener('input',()=>{const view=this.views.get(node.id);if(view)view.dirty=true;});
        input.addEventListener('compositionstart',()=>{const view=this.views.get(node.id);if(view)view.composing=true;});
        input.addEventListener('compositionend',()=>{const view=this.views.get(node.id);if(view)view.composing=false;});
        input.addEventListener('keydown',(e)=>{if(e.key==='Enter' && !e.isComposing){e.preventDefault();doSubmit();}});
        submit.addEventListener('click',doSubmit);row.append(input,submit);el.append(parts.label,row);break;
      }
      case 'textarea':{
        el=element('div','block-input block-textarea');parts.label=element('label');
        const input=element('textarea');input.maxLength=TEXTAREA_MAX_LENGTH;input.id=`textarea-${node.id}`;
        parts.label.setAttribute('for',input.id);
        const footer=element('div','textarea-footer');parts.counter=element('span','textarea-counter');
        parts.counter.id=`textarea-count-${node.id}`;parts.counter.setAttribute('aria-live','off');
        input.setAttribute('aria-describedby',parts.counter.id);
        const submit=element('button','block-button compact');submit.type='button';
        parts.input=input;parts.submit=submit;
        const doSubmit=()=>{const view=this.views.get(node.id);if(view&&!view.composing){view.submitted=input.value;void this.send(node.id,input.value);}};
        input.addEventListener('input',()=>{const view=this.views.get(node.id);if(view)view.dirty=true;write(parts.counter,`${input.value.length}/${TEXTAREA_MAX_LENGTH}`);});
        input.addEventListener('compositionstart',()=>{const view=this.views.get(node.id);if(view)view.composing=true;});
        input.addEventListener('compositionend',()=>{const view=this.views.get(node.id);if(view)view.composing=false;});
        submit.addEventListener('click',doSubmit);footer.append(parts.counter,submit);el.append(parts.label,input,footer);break;
      }
      case 'key_value':el=element('dl','block-key-value');break;
      default:el=element('p');el.textContent=t('component.unsupported');
    }
    return {kind:node.kind,element:el,parts};
  }
  private update(view:View,node:ComponentNode,p:Record<string,unknown>,snapshot:Snapshot):void {
    const el=view.element;el.dataset.tone=tone(p.tone);
    view.contextAction=typeof p.context_action==='string'?p.context_action:undefined;
    const pending=snapshot.actions.some(a=>a.component_id===node.id && a.status==='pending');
    const disabled=snapshot.status!=='online'||p.disabled===true||pending||this.inFlight.has(node.id);
    switch(node.kind) {
      case 'stack':case 'row':{
        el.style.gap=`${clamp(number(p.gap,12)*this.themeSpacingScale,0,48)}px`;
        el.style.alignItems=p.align==='center'?'center':p.align==='end'?'flex-end':'stretch';break;
      }
      case 'text':el.dataset.size=['title','heading','small'].includes(String(p.size))?String(p.size):'body';write(el,text(p.text));break;
      case 'badge':write(el,text(p.text));break;
      case 'metric':write(view.parts.label,text(p.label));write(view.parts.value,text(p.value));write(view.parts.unit,p.unit===undefined?'':text(p.unit));write(view.parts.caption,p.caption===undefined?'':text(p.caption));break;
      case 'progress':{
        const percent=progress(p.value,p.max);write(view.parts.label,text(p.label));write(view.parts.value,`${percent.toFixed(0)}%`);
        view.parts.fill!.style.width=`${percent}%`;el.setAttribute('aria-valuemin','0');el.setAttribute('aria-valuemax','100');el.setAttribute('aria-valuenow',String(percent));el.setAttribute('aria-label',text(p.label));break;
      }
      case 'icon':{
        el.replaceChildren();const icon=createVectorIcon(p.name,p.label);
        if(icon)el.append(icon);else el.hidden=true;
        if(icon)el.hidden=false;
        break;
      }
      case 'bar_chart':{
        const label=text(p.label);write(view.parts.label,label);el.setAttribute('aria-label',label);
        const items=Array.isArray(p.items)?p.items.slice(0,8):[];
        const values=items.map(item=>item&&typeof item==='object'?number((item as Record<string,unknown>).value,0):0);
        const maxValue=Math.max(1,...values);
        const rows:HTMLElement[]=items.map((item,index)=>{
          const record=item&&typeof item==='object'?item as Record<string,unknown>:{};
          const row=element('div','chart-row');row.dataset.tone=tone(record.tone);
          const rowLabel=element('span','chart-row-label');write(rowLabel,text(record.label));
          const track=element('span','chart-track');track.setAttribute('role','progressbar');
          const bar=element('span','chart-bar');bar.style.width=`${clamp(values[index]!/maxValue*100,0,100)}%`;
          const value=element('span','chart-row-value');write(value,String(values[index]??0));
          track.setAttribute('aria-valuemin','0');track.setAttribute('aria-valuemax',String(maxValue));
          track.setAttribute('aria-valuenow',String(values[index]??0));track.setAttribute('aria-label',`${text(record.label)}: ${values[index]??0}`);
          track.append(bar);row.append(rowLabel,track,value);return row;
        });
        if(!rows.length){const empty=element('span','chart-empty');write(empty,t('chart.empty'));rows.push(empty);}
        el.replaceChildren(view.parts.label!,...rows);break;
      }
      case 'button':{
        write(el,text(p.label));view.shortcut=typeof p.shortcut==='string'?p.shortcut:undefined;
        view.selectionGroup=typeof p.selection_group==='string'?p.selection_group:undefined;
        view.selectionMode=p.selection_mode==='single'||p.selection_mode==='multiple'?p.selection_mode:undefined;
        view.pressed=p.pressed===true;
        const button=el as HTMLButtonElement;
        button.dataset.appearance=['link','title'].includes(String(p.appearance))?String(p.appearance):'default';
        button.disabled=snapshot.status!=='online'||p.disabled===true;
        button.setAttribute('aria-disabled',String(disabled));
        button.tabIndex=0;button.setAttribute('aria-busy',String(pending||this.inFlight.has(node.id)));
        if(view.selectionGroup)button.setAttribute('aria-pressed',String(view.pressed));else button.removeAttribute('aria-pressed');
        break;
      }
      case 'input':case 'textarea':{
        const input=view.parts.input as HTMLInputElement|HTMLTextAreaElement;const target=p.value===undefined?'':text(p.value);
        view.shortcut=node.kind==='textarea'&&typeof p.shortcut==='string'?p.shortcut:undefined;
        const completed=[...snapshot.actions].reverse().find(a=>a.component_id===node.id && a.status==='ok');
        // Only commit this draft when the provider projects the same value back.
        if(completed && view.submitted===input.value && target===input.value){view.dirty=false;view.submitted=undefined;}
        if(!view.dirty && !view.composing && document.activeElement!==input && input.value!==target)input.value=target;
        input.placeholder=p.placeholder===undefined?'':text(p.placeholder);input.disabled=snapshot.status!=='online'||p.disabled===true;
        const submit=view.parts.submit as HTMLButtonElement;
        submit.disabled=snapshot.status!=='online'||p.disabled===true;
        submit.setAttribute('aria-disabled',String(disabled));
        submit.setAttribute('aria-busy',String(pending||this.inFlight.has(node.id)));
        write(submit,p.submit_label===undefined?t('input.submit'):text(p.submit_label));
        if(view.parts.counter)write(view.parts.counter,`${input.value.length}/${TEXTAREA_MAX_LENGTH}`);
        write(view.parts.label,text(p.label));break;
      }
      case 'key_value':{
        const items=Array.isArray(p.items)?p.items.slice(0,64):[];
        const fragments=items.map(item=>{
          const record=(item && typeof item==='object')?item as Record<string,unknown>:{};
          const row=element('div','kv-row');row.dataset.tone=tone(record.tone);
          const key=element('dt','kv-key');const icon=createVectorIcon(record.icon);
          if(icon)key.append(icon);
          const keyLabel=element('span','kv-key-label');write(keyLabel,text(record.key));key.append(keyLabel);
          const value=element('dd','kv-value');const primary=element('span','kv-primary');write(primary,text(record.value));value.append(primary);
          if(typeof record.secondary==='string'&&record.secondary.length){const secondary=element('span','kv-secondary');write(secondary,record.secondary);value.append(secondary);}
          row.append(key,value);return row;
        });
        el.replaceChildren(...fragments);break;
      }
      case 'divider':break;
    }
  }
  private async send(id:string,value:unknown,source:InteractionSource='click'):Promise<void> {
    if(this.inFlight.has(id)||this.pendingActions.has(id)||!this.snapshot||this.snapshot.status!=='online')return;
    const active=document.activeElement;
    const activeNode=active instanceof HTMLElement?active.closest<HTMLElement>('[data-component-id]')?.dataset.componentId:undefined;
    const focusTarget=active instanceof HTMLElement&&activeNode===id?active:undefined;
    this.inFlight.add(id);this.render(this.snapshot);
    let waitingForResult=false;
    try{
      const eventId=await this.interact(id,value,source);
      if(typeof eventId==='string'){
        this.pendingActions.set(id,eventId);waitingForResult=true;
        if(focusTarget)this.pendingFocusRestore.set(eventId,{componentId:id,target:focusTarget});
      }
    }catch(error){this.onError(error);}finally{
      if(!waitingForResult)this.inFlight.delete(id);if(this.snapshot)this.render(this.snapshot);
    }
  }
}
