import {clamp,number,progress,resolve,text,tone} from './bindings.js';
import type {ComponentNode,Kind,Snapshot} from './types.js';

type Interact=(nodeId:string,value:unknown,contextAction:boolean)=>Promise<unknown>;
interface View {
  kind:Kind; element:HTMLElement; parts:Record<string,HTMLElement>;
  contextAction?:string; dirty?:boolean; composing?:boolean; submitted?:string;
}
function element<K extends keyof HTMLElementTagNameMap>(tag:K,cls=''):HTMLElementTagNameMap[K] {
  const el=document.createElement(tag);el.className=cls;return el;
}
function write(el:HTMLElement|undefined,value:string):void { if(el && el.textContent!==value)el.textContent=value; }

/** Stable keys preserve input drafts and DOM identity while other providers' data changes.
 * Scope is one world; different worlds have different maps and WebViews.
 */
export class SceneRenderer {
  private views=new Map<string,View>();
  private snapshot:Snapshot|null=null;
  private inFlight=new Set<string>();
  constructor(private mount:HTMLElement,private interact:Interact,private onError:(e:unknown)=>void){}
  render(snapshot:Snapshot):void {
    this.snapshot=snapshot;
    const seen=new Set<string>();
    const walk=(node:ComponentNode):HTMLElement=>{
      seen.add(node.id);
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
    if(this.mount.firstElementChild!==root)this.mount.replaceChildren(root);
    for(const [id,view] of this.views)if(!seen.has(id)){view.element.remove();this.views.delete(id);this.inFlight.delete(id);}
  }
  handleContextMenu(event:MouseEvent):void {
    const target=event.target;
    if(!(target instanceof Element))return;
    const nodeId=target.closest<HTMLElement>('[data-component-id]')?.dataset.componentId;
    if(!nodeId)return;
    const view=this.views.get(nodeId);
    if(!view?.contextAction)return;
    const value=view.kind==='input'?(view.parts.input as HTMLInputElement).value:null;
    void this.send(nodeId,value,true);
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
      case 'button':{
        const button=element('button','block-button');button.type='button';
        button.addEventListener('click',()=>void this.send(node.id,null));el=button;break;
      }
      case 'input':{
        el=element('div','block-input');parts.label=element('label');const row=element('div','input-row');
        const input=element('input');input.type='text';input.maxLength=1024;input.id=`input-${node.id}`;
        parts.label.setAttribute('for',input.id);
        const submit=element('button','block-button compact');submit.type='button';submit.textContent='提交';
        parts.input=input;parts.submit=submit;
        const doSubmit=()=>{const view=this.views.get(node.id);if(view && !view.composing){view.submitted=input.value;void this.send(node.id,input.value);}};
        input.addEventListener('input',()=>{const view=this.views.get(node.id);if(view)view.dirty=true;});
        input.addEventListener('compositionstart',()=>{const view=this.views.get(node.id);if(view)view.composing=true;});
        input.addEventListener('compositionend',()=>{const view=this.views.get(node.id);if(view)view.composing=false;});
        input.addEventListener('keydown',(e)=>{if(e.key==='Enter' && !e.isComposing){e.preventDefault();doSubmit();}});
        submit.addEventListener('click',doSubmit);row.append(input,submit);el.append(parts.label,row);break;
      }
      case 'key_value':el=element('dl','block-key-value');break;
      default:el=element('p');el.textContent='不支持的组件';
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
        el.style.gap=`${clamp(number(p.gap,12),0,48)}px`;
        el.style.alignItems=p.align==='center'?'center':p.align==='end'?'flex-end':'stretch';break;
      }
      case 'text':el.dataset.size=['title','heading','small'].includes(String(p.size))?String(p.size):'body';write(el,text(p.text));break;
      case 'badge':write(el,text(p.text));break;
      case 'metric':write(view.parts.label,text(p.label));write(view.parts.value,text(p.value));write(view.parts.unit,p.unit===undefined?'':text(p.unit));write(view.parts.caption,p.caption===undefined?'':text(p.caption));break;
      case 'progress':{
        const percent=progress(p.value,p.max);write(view.parts.label,text(p.label));write(view.parts.value,`${percent.toFixed(0)}%`);
        view.parts.fill!.style.width=`${percent}%`;el.setAttribute('aria-valuemin','0');el.setAttribute('aria-valuemax','100');el.setAttribute('aria-valuenow',String(percent));el.setAttribute('aria-label',text(p.label));break;
      }
      case 'button':write(el,text(p.label));(el as HTMLButtonElement).disabled=disabled;el.setAttribute('aria-busy',String(pending));break;
      case 'input':{
        const input=view.parts.input as HTMLInputElement;const target=p.value===undefined?'':text(p.value);
        const completed=[...snapshot.actions].reverse().find(a=>a.component_id===node.id && a.status==='ok');
        // Only commit this draft when the provider projects the same value back.
        if(completed && view.submitted===input.value && target===input.value){view.dirty=false;view.submitted=undefined;}
        if(!view.dirty && !view.composing && document.activeElement!==input && input.value!==target)input.value=target;
        input.placeholder=p.placeholder===undefined?'':text(p.placeholder);input.disabled=snapshot.status!=='online'||p.disabled===true;
        (view.parts.submit as HTMLButtonElement).disabled=disabled;
        write(view.parts.label,text(p.label));break;
      }
      case 'key_value':{
        const items=Array.isArray(p.items)?p.items.slice(0,64):[];
        const fragments=items.map(item=>{
          const record=(item && typeof item==='object')?item as Record<string,unknown>:{};
          const row=element('div','kv-row');const key=element('dt');const value=element('dd');
          key.textContent=text(record.key);value.textContent=text(record.value);row.append(key,value);return row;
        });
        el.replaceChildren(...fragments);break;
      }
      case 'divider':break;
    }
  }
  private async send(id:string,value:unknown,contextAction=false):Promise<void> {
    if(this.inFlight.has(id) || !this.snapshot || this.snapshot.status!=='online')return;
    this.inFlight.add(id);this.render(this.snapshot);
    try{await this.interact(id,value,contextAction);}catch(error){this.onError(error);}finally{
      this.inFlight.delete(id);if(this.snapshot)this.render(this.snapshot);
    }
  }
}
