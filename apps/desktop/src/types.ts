export type Kind = 'stack'|'row'|'text'|'metric'|'progress'|'badge'|'button'|'input'|'textarea'|'key_value'|'icon'|'bar_chart'|'divider';
export interface ComponentNode { id:string; kind:Kind; props:Record<string,unknown>; children:ComponentNode[] }
export interface ThemeTokens {
  background:string; foreground:string; accent:string; font_scale:number; radius_px:number; spacing_px:number;
}
export interface Scene { root:ComponentNode; data:unknown; theme?:ThemeTokens }
export interface ActionState { id:string; component_id:string; action:string; status:'pending'|'ok'|'error'; message:string|null }
export type WorkAreaCorner = 'top_left'|'top_right'|'bottom_left'|'bottom_right';
export interface WorkAreaAnchor { corner:WorkAreaCorner; margin_x:number; margin_y:number }
export interface WindowSpec {
  title:string; width:number; height:number; position:{x:number;y:number}|null; anchor:WorkAreaAnchor|null;
  always_on_top:boolean; visible:boolean; resizable:boolean; title_bar_visible:boolean; background_drag_enabled:boolean; text_selectable:boolean; decorations:boolean;
  skip_taskbar:boolean; click_through:boolean; geometry_control:'provider'|'human'; position_control:'provider'|'human'|null; surface_opacity:number;
}
export interface Snapshot {
  id:string; revision:number; sequence:number; window_revision:number; epoch:number;
  system:boolean; writer:string|null; status:'online'|'stale'|'vacant';
  window:WindowSpec; scene:Scene;
  native:{ state:string; applied_window_revision:number|null; error:string|null };
  actions:ActionState[];
}
export interface TauriApi {
  core:{invoke<T>(command:string,args?:Record<string,unknown>):Promise<T>};
  event:{listen<T>(event:string,handler:(event:{payload:T})=>void):Promise<()=>void>};
  webview:{getCurrentWebview():{onDragDropEvent(handler:(event:{payload:{type:string;paths?:string[]}})=>void):Promise<()=>void>}};
}
declare global { interface Window { __TAURI__?:TauriApi } }
