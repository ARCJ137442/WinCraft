/** Deliberately not an expression language. No eval, HTML, CSS strings or object mutation. */
export function resolve(value:unknown,data:unknown):unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
  const record=value as Record<string,unknown>;
  if (!Object.hasOwn(record,'$path') || typeof record.$path!=='string') return value;
  const path=record.$path;
  if (path==='') return data;
  if (!path.startsWith('/') || path.length>256) return undefined;
  let cursor:unknown=data;
  for (const raw of path.slice(1).split('/')) {
    if (/~(?![01])/u.test(raw)) return undefined;
    const part=raw.replace(/~1/g,'/').replace(/~0/g,'~');
    if (['__proto__','prototype','constructor'].includes(part)) return undefined;
    if (cursor===null || typeof cursor!=='object' || !Object.hasOwn(cursor,part)) return undefined;
    cursor=(cursor as Record<string,unknown>)[part];
  }
  return cursor;
}
export function text(value:unknown):string {
  if (value===null || value===undefined) return '—';
  if (typeof value==='string') return value;
  if (typeof value==='number' || typeof value==='boolean') return String(value);
  return JSON.stringify(value);
}
export function number(value:unknown,fallback=0):number {
  return typeof value==='number' && Number.isFinite(value) ? value : fallback;
}
export function clamp(value:number,min:number,max:number):number { return Math.min(max,Math.max(min,value)); }
export function progress(value:unknown,max:unknown):number {
  const denominator=number(max,100);
  return denominator>0 ? clamp(number(value)/denominator*100,0,100) : 0;
}
export function tone(value:unknown):string {
  return typeof value==='string' && ['accent','muted','success','warning','danger'].includes(value) ? value : 'normal';
}
export function errorDetails(error:unknown):{code:string|null;message:string} {
  const raw=error instanceof Error ? error.message : error;
  let value:unknown=raw;
  if(typeof value==='string'){
    const source=value;
    try{value=JSON.parse(source);}catch{return {code:null,message:source};}
  }
  if(value && typeof value==='object' && !Array.isArray(value)){
    const record=value as Record<string,unknown>;
    const code=typeof record.code==='string'?record.code:null;
    const message=typeof record.message==='string'?record.message:null;
    if(code||message)return {code,message:message??code??'操作失败'};
  }
  return {code:null,message:typeof raw==='string'?raw:JSON.stringify(raw)??String(raw)};
}
export type ActionFeedback={state:'pending'|'ok'|'error';message:string};
export function displayActionFeedback(
  actions:readonly {id:string;status:'pending'|'ok'|'error';message:string|null}[],
  trackedActionId:string|null,
  notice:ActionFeedback|null,
):ActionFeedback|null {
  if(notice)return notice;
  const action=trackedActionId?actions.find(item=>item.id===trackedActionId):actions.at(-1);
  if(!action)return null;
  const label=action.status==='pending'?'等待提供者确认':action.status==='ok'?'操作已确认':'操作失败';
  return {state:action.status,message:`${label}${action.message?' · '+action.message:''}`};
}
/** Event and initial fetch may race; a stale snapshot must not replace a newer one. */
export function newer(current:{id:string;sequence:number}|null,next:{id:string;sequence:number}):boolean {
  return current===null || (current.id===next.id && next.sequence>current.sequence);
}
