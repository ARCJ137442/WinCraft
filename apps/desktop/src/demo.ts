import type {ComponentNode,Kind,Snapshot} from './types.js';
const node=(id:string,kind:Kind,props:Record<string,unknown>={},children:ComponentNode[]=[]):ComponentNode=>({id,kind,props,children});
export function demoSnapshot(manager=false):Snapshot {
  const scene=manager?{
    root:node('root','stack',{gap:18},[
      node('hero','text',{text:'让程序长出可组合的窗口',size:'title'}),
      node('sub','text',{text:'世界即窗口 · 一个写入者，多个快照观察者',tone:'muted'}),
      node('toolbar','row',{},[node('new','button',{label:'新建空白世界',action:'new_world',tone:'accent'}),node('refresh','button',{label:'刷新',action:'refresh'})]),
      node('count','metric',{label:'开放的世界',value:2,unit:'个',caption:'浏览器演示数据，不代表原生窗口已经创建'}),
      node('divider','divider'),node('settings','text',{text:'本次会话的默认设置',size:'heading'}),
      node('title','input',{label:'新世界名称',value:{$path:'/title'},action:'settings.title'}),
      node('top','button',{label:'默认置顶：开启',action:'settings.top'}),
      node('world','stack',{gap:10},[node('world-title','text',{text:'专注与后台任务',size:'heading'}),node('world-status','badge',{text:'online · demo.provider',tone:'success'}),node('world-controls','row',{},[node('rescue','button',{label:'接管并找回',action:'rescue'}),node('close','button',{label:'关闭世界',action:'close',tone:'danger'})])])
    ]),data:{title:'空白世界'}
  }:{root:node('root','stack',{gap:18},[
    node('eyebrow','badge',{text:'PROVIDER / 演示提供者',tone:'accent'}),
    node('title','text',{text:'把注意力留在眼前',size:'title'}),
    node('intro','text',{text:'这里的组件由声明生成。业务状态属于提供者，不属于窗口。',tone:'muted'}),
    node('metrics','row',{gap:16},[
      node('clock','metric',{label:'专注倒计时',value:{$path:'/clock'},unit:'',caption:'业务时间来自演示提供者'}),
      node('jobs','metric',{label:'已完成任务',value:{$path:'/done'},unit:'/ 12',caption:'一次窗口，多种组件'})
    ]),
    node('progress','progress',{label:'后台任务',value:{$path:'/progress'},max:100}),
    node('actions','row',{},[node('pause','button',{label:{$path:'/button'},action:'toggle_pause',tone:'accent'}),node('structure','button',{label:'替换结果区',action:'rebuild'})]),
    node('note','input',{label:'给提供者发一条消息',placeholder:'输入后按 Enter；更新不会抹掉草稿',value:{$path:'/note'},action:'note'}),
    node('meta','key_value',{items:[{key:'窗口策略',value:'人类可拖动 · 托盘可找回'},{key:'写入模型',value:'窗口级独占租约'},{key:'演示边界',value:'无 Rust 服务、无原生窗口控制'}]})
  ]),data:{clock:'24:18',done:7,progress:58,button:'暂停',note:''}};
  return {id:manager?'preview-manager':'preview-world',revision:1,sequence:1,window_revision:1,epoch:1,system:manager,writer:'demo',status:'online',
    window:{title:manager?'窗构 · 世界管理器':'专注与后台任务',width:620,height:700,position:null,always_on_top:true,visible:true,resizable:true,title_bar_visible:true,decorations:false,skip_taskbar:true,click_through:false,geometry_control:'human',surface_opacity:0.8},
    scene,native:{state:'preview',applied_window_revision:null,error:null},actions:[]};
}
export function previewController(snapshot:Snapshot,accept:(s:Snapshot)=>void):(id:string,value:unknown)=>Promise<string> {
  let current=snapshot;
  return async(id,value)=>{
    current=structuredClone(current);current.sequence++;current.revision++;
    const data=current.scene.data as Record<string,unknown>;
    if(id==='pause'){data.button=data.button==='暂停'?'继续':'暂停';}
    else if(id==='note'){data.note=String(value);}
    else if(id==='title'){data.title=String(value);}
    else if(id==='structure'){
      const root=current.scene.root;
      const index=root.children.findIndex(n=>n.id==='progress');
      if(index>=0)root.children[index]=node('result','badge',{text:'结果区已动态替换 · 无需重启窗口',tone:'success'});
    }
    const actionId=`preview-${current.sequence}`;
    current.actions.push({id:actionId,component_id:id,action:'preview',status:'ok',message:'仅浏览器演示'});
    accept(current);
    return actionId;
  };
}
