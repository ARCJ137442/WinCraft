import {t} from './i18n.js';

const FONT_SCALE_KEY='wincraft.accessibility.font_scale';
const FONT_SCALE_MIN=0.8;
const FONT_SCALE_MAX=2;
const FONT_SCALE_STEP=0.1;

export type ZoomAction='in'|'out'|'reset';

export function normalizeUserFontScale(value:unknown):number|null {
  const parsed=typeof value==='number'?value:typeof value==='string'?Number(value):Number.NaN;
  if(!Number.isFinite(parsed))return null;
  const bounded=Math.min(FONT_SCALE_MAX,Math.max(FONT_SCALE_MIN,parsed));
  return Math.round(bounded*10)/10;
}

export function nextUserFontScale(current:number|null,action:ZoomAction):number|null {
  if(action==='reset')return null;
  const base=current??1;
  const offset=action==='in'?FONT_SCALE_STEP:-FONT_SCALE_STEP;
  return normalizeUserFontScale(base+offset);
}

function isEditableTarget(target:EventTarget|null):boolean {
  if(!(target instanceof Element))return false;
  if(target instanceof HTMLElement&&target.isContentEditable)return true;
  return Boolean(target.closest('input,textarea,select,[contenteditable="true"]'));
}

function zoomAction(event:KeyboardEvent):ZoomAction|null {
  if(event.code==='Digit0'||event.key==='0')return 'reset';
  if(event.code==='Equal'&&(event.shiftKey||event.key==='+'))return 'in';
  if(event.key==='+')return 'in';
  if(event.code==='Minus'||event.key==='-')return 'out';
  return null;
}

export function initializeAccessibility():void {
  let current:number|null=null;
  const announce=document.getElementById('accessibility-status');
  const apply=(scale:number|null):void=>{
    const root=document.documentElement;
    if(scale===null)root.style.removeProperty('--wc-user-font-scale');
    else root.style.setProperty('--wc-user-font-scale',String(scale));
  };
  const read=():number|null=>{
    try{return normalizeUserFontScale(window.localStorage.getItem(FONT_SCALE_KEY));}
    catch{return null;}
  };
  const persist=(scale:number|null):void=>{
    try{
      if(scale===null)window.localStorage.removeItem(FONT_SCALE_KEY);
      else window.localStorage.setItem(FONT_SCALE_KEY,String(scale));
    }catch{/* The in-memory preference remains active for this WebView. */}
  };
  const set=(scale:number|null,shouldPersist:boolean):void=>{
    current=scale;
    apply(scale);
    if(shouldPersist)persist(scale);
    if(announce)announce.textContent=scale===null
      ?t('accessibility.zoom_reset')
      :t('accessibility.zoom_changed',{percent:Math.round(scale*100)});
  };

  current=read();
  apply(current);
  document.addEventListener('keydown',event=>{
    if(event.isComposing||event.defaultPrevented||!event.ctrlKey||event.altKey||event.metaKey||isEditableTarget(event.target))return;
    const action=zoomAction(event);
    if(!action)return;
    event.preventDefault();
    set(nextUserFontScale(current,action),true);
  });
  window.addEventListener('storage',event=>{
    if(event.key===FONT_SCALE_KEY)set(normalizeUserFontScale(event.newValue),false);
  });
}
