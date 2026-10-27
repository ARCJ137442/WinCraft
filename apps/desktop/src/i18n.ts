import {catalogs as sourceCatalogs} from './locales/generated.js';

export type Locale='zh-CN'|'en-US';
type Catalog=Record<string,string>;
const catalogs:Record<Locale,Catalog>={'zh-CN':sourceCatalogs['zh-CN'],'en-US':sourceCatalogs['en-US']};
const missing=new Set<string>();
let activeLocale:Locale='zh-CN';
let storageListenerInstalled=false;

export function normalizeLocale(value:unknown):Locale {
  if(typeof value==='string'&&value.toLowerCase().startsWith('en'))return 'en-US';
  return 'zh-CN';
}

export function getLocale():Locale { return activeLocale; }

export function localeKeyAudit():{matchingKeys:boolean;missingInEnglish:string[];placeholderMismatches:string[]} {
  const zhKeys=Object.keys(catalogs['zh-CN']);const enKeys=new Set(Object.keys(catalogs['en-US']));
  const missingInEnglish=zhKeys.filter(key=>!enKeys.has(key));
  const placeholderMismatches:string[]=[];
  const names=(value:string)=>[...value.matchAll(/\{([^}]+)\}/gu)].map(match=>match[1]??'').sort().join(',');
  for(const key of zhKeys)if(!enKeys.has(key)||names(catalogs['zh-CN'][key]??'')!==names(catalogs['en-US'][key]??''))placeholderMismatches.push(key);
  return {matchingKeys:missingInEnglish.length===0&&enKeys.size===zhKeys.length,missingInEnglish,placeholderMismatches};
}

export function t(key:string,params:Record<string,string|number>={}):string {
  const active=catalogs[activeLocale][key];
  const template=active??catalogs['zh-CN'][key]??key;
  if(active===undefined){
    missing.add(key);
    if(typeof document!=='undefined')document.documentElement.dataset.localeFallbackCount=String(missing.size);
  }
  return template.replace(/\{([^}]+)\}/gu,(_match,name:string)=>String(params[name]??`{${name}}`));
}

function updateStaticContent():void {
  if(typeof document==='undefined')return;
  document.documentElement.lang=activeLocale;
  document.body.dataset.locale=activeLocale;
  for(const element of document.querySelectorAll<HTMLElement>('[data-i18n]')){
    const key=element.dataset.i18n;
    if(key){
      element.textContent=t(key);
      if(missing.has(key))element.dataset.translationFallback=key;
      else delete element.dataset.translationFallback;
    }
  }
  const attributes=[
    ['data-i18n-aria-label','aria-label'],
    ['data-i18n-title','title'],
    ['data-i18n-placeholder','placeholder'],
  ] as const;
  for(const [dataKey,attribute] of attributes){
    for(const element of document.querySelectorAll<HTMLElement>(`[${dataKey}]`)){
      const key=element.getAttribute(dataKey);
      if(key){
        element.setAttribute(attribute,t(key));
        if(missing.has(key))element.dataset.translationFallback=key;
        else delete element.dataset.translationFallback;
      }
    }
  }
}

export function setLocale(value:unknown,persist=false):Locale {
  activeLocale=normalizeLocale(value);
  if(persist&&typeof window!=='undefined'){
    try{window.localStorage.setItem('wincraft.locale',activeLocale);}catch{/* Local preference persistence is optional. */}
  }
  updateStaticContent();
  if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('wincraft:locale',{detail:activeLocale}));
  return activeLocale;
}

export function initializeLocale(preferred?:unknown):Locale {
  let stored:string|null=null;
  if(typeof window!=='undefined'){
    try{stored=window.localStorage.getItem('wincraft.locale');}catch{/* Fall back to system language. */}
  }
  const systemLocale=typeof navigator!=='undefined'?navigator.language:'zh-CN';
  const locale=setLocale(preferred??stored??systemLocale,false);
  if(typeof window!=='undefined'&&!storageListenerInstalled){
    storageListenerInstalled=true;
    window.addEventListener('storage',event=>{
      if(event.key==='wincraft.locale'&&event.newValue)setLocale(event.newValue,false);
    });
  }
  return locale;
}

export function missingLocaleKeys():string[]{return [...missing].sort();}
