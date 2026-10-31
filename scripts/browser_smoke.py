"""Real browser checks of the shipped renderer. Does NOT exercise Tauri/Win32/Rust."""
from __future__ import annotations
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('WINCRAFT_EVIDENCE',str(ROOT/'evidence/local')))
OUT.mkdir(parents=True,exist_ok=True)
log=(OUT/'preview-server.log').open('w',encoding='utf-8')
server=subprocess.Popen(['node',str(ROOT/'scripts/dev-server.mjs')],cwd=ROOT,stdout=log,stderr=log)
checks=[]
offline=os.environ.get('WINCRAFT_OFFLINE_BROWSER')=='1'

def offline_modules(page):
    html=(ROOT/'apps/desktop/dist/index.html').read_text(encoding="utf-8")
    html=re.sub(r'<link[^>]*>', '', html)
    html=re.sub(r'<script[\s\S]*?</script>', '', html)
    page.set_content(html)
    for stylesheet in ('style.css','fit.css'):
        page.add_style_tag(content=(ROOT/'apps/desktop/dist'/stylesheet).read_text(encoding="utf-8"))
    modules={}
    def load(name):
        if name in modules:return modules[name]
        source=(ROOT/'apps/desktop/dist'/name).read_text(encoding="utf-8")
        if name.endswith('.json'):
            source='export default '+json.dumps(json.loads(source),ensure_ascii=False)+';'
        source=re.sub(r"from ['\"]\./([^'\"]+)['\"](?:\s+with\s+\{\s*type\s*:\s*['\"]json['\"]\s*\})?", lambda m:'from '+json.dumps(load(m.group(1))), source)
        modules[name]=page.evaluate('(source)=>URL.createObjectURL(new Blob([source],{type:"text/javascript"}))',source)
        return modules[name]
    main=load('main.js')
    page.add_script_tag(type='module',url=main)
    return modules

try:
    for _ in range(80):
        if server.poll() is not None:
            raise RuntimeError('Preview server exited; see preview-server.log')
        try:
            urllib.request.urlopen('http://127.0.0.1:1420/',timeout=.3).close()
            break
        except Exception:
            time.sleep(.1)
    else:
        raise RuntimeError('Preview server did not become ready')
    with sync_playwright() as p:
        executable=os.environ.get('CHROMIUM_PATH')
        browser=p.chromium.launch(**({'executable_path':executable} if executable else {}),args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1000,'height':1000},device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        modules=offline_modules(page) if offline else {}
        if not offline: page.goto('http://127.0.0.1:1420/')
        page.wait_for_selector('[data-component-id="clock"]')
        assert page.locator('#preview').is_visible()
        preview_text=page.locator('#preview').inner_text()
        assert ('非原生窗口验收' in preview_text) or ('not native window acceptance' in preview_text.lower()),preview_text
        checks.append('preview_is_explicitly_labelled')
        assert page.locator('#minimize').get_attribute('aria-label') in ('最小化窗口','Minimize window')
        assert page.locator('#close').evaluate("el=>el.previousElementSibling?.id")=='minimize'
        assert page.locator('#world').get_attribute('tabindex') is None
        assert page.locator('#scene').get_attribute('tabindex')=='0'
        assert page.locator('#status').get_attribute('role')=='status'
        assert page.locator('#status').get_attribute('aria-live')=='polite'
        checks.append('host_shell_has_status_semantics_without_an_extra_tab_stop')
        assert not page.locator('.status-line').is_visible(), 'healthy online status should be hidden'
        assert page.locator('#drag').get_attribute('role')=='button'
        assert page.locator('#drag').get_attribute('tabindex')=='0'
        assert page.locator('#drag').get_attribute('aria-expanded')=='true'
        collapse_result=page.evaluate('''() => {
            const drag=document.getElementById('drag');
            const clickTitle=(pointerId)=>{
              drag.dispatchEvent(new PointerEvent('pointerdown',{button:0,pointerId,clientX:20,clientY:20,bubbles:true}));
              window.dispatchEvent(new PointerEvent('pointerup',{button:0,pointerId,clientX:21,clientY:20,bubbles:true}));
            };
            clickTitle(7);
            const collapsed=document.body.dataset.contentCollapsed==='true'
              &&drag.getAttribute('aria-expanded')==='false'
              &&getComputedStyle(document.getElementById('scene')).display==='none';
            clickTitle(8);
            const expanded=document.body.dataset.contentCollapsed==='false'
              &&drag.getAttribute('aria-expanded')==='true'
              &&getComputedStyle(document.getElementById('scene')).display!=='none';
            const badge=document.createElement('span');badge.className='block-badge';document.body.append(badge);
            const emptyBadgeHidden=getComputedStyle(badge).display==='none';badge.remove();
            return {collapsed,expanded,emptyBadgeHidden};
        }''')
        assert collapse_result=={'collapsed':True,'expanded':True,'emptyBadgeHidden':True},collapse_result
        checks.append('titlebar_click_collapses_and_expands_content_without_drag')
        checks.append('empty_healthy_status_badges_are_hidden')
        checks.append('separate_minimize_control_is_present')
        assert page.locator('#world').evaluate('el=>getComputedStyle(el).opacity')=='0.8'
        checks.append('default_surface_opacity_is_80_percent')
        selection=page.evaluate('''() => {
            const world=document.querySelector('#world');
            const content=document.querySelector('#scene');
            const text=document.querySelector('.block-text');
            const titlebar=document.querySelector('.chrome');
            const defaults={world:getComputedStyle(world).userSelect,titlebar:getComputedStyle(titlebar).userSelect};
            world.style.setProperty('--world-text-selection','none');
            const disabled=getComputedStyle(world).userSelect;
            text.style.userSelect='text';
            titlebar.style.userSelect='text';
            const overridden=getComputedStyle(text).userSelect;
            const chromeOverride=getComputedStyle(titlebar).userSelect;
            return {defaults,disabled,overridden,chromeOverride,content:content.className};
        }''')
        assert selection['defaults']=={'world':'text','titlebar':'none'},selection
        assert selection['disabled']=='none' and selection['overridden']=='text',selection
        assert selection['chromeOverride']=='none',selection
        checks.append('window_text_selection_default_component_override_and_unselectable_titlebar')
        native_style=page.evaluate('''() => {
            document.body.classList.remove('preview-body');
            const result={
                htmlOverflow:getComputedStyle(document.documentElement).overflowY,
                bodyOverflow:getComputedStyle(document.body).overflowY,
                worldOverflow:getComputedStyle(document.querySelector('.world')).overflowY,
                worldScrollbar:getComputedStyle(document.querySelector('.world')).scrollbarWidth,
                sceneOverflow:getComputedStyle(document.querySelector('.scene')).overflowY,
                sceneScrollbar:getComputedStyle(document.querySelector('.scene')).scrollbarWidth,
            };
            document.body.classList.add('preview-body');
            return result;
        }''')
        assert native_style=={'htmlOverflow':'hidden','bodyOverflow':'hidden','worldOverflow':'hidden','worldScrollbar':'none','sceneOverflow':'auto','sceneScrollbar':'none'},native_style
        checks.append('native_surface_uses_hidden_scrollbars')
        page.screenshot(path=str(OUT/'world-preview.png'),full_page=True)
        page.locator('#input-note').fill('未提交的中文草稿')
        page.evaluate('window.savedInput=document.querySelector("#input-note")')
        page.locator('[data-component-id="pause"]').click()
        assert page.locator('#input-note').input_value()=='未提交的中文草稿'
        assert page.evaluate('window.savedInput===document.querySelector("#input-note")')
        checks.append('draft_and_dom_identity_survive_unrelated_updates')
        page.locator('[data-component-id="structure"]').click()
        assert page.locator('[data-component-id="result"]').count()==1, page.locator('#error').inner_text()
        assert page.locator('[data-component-id="progress"]').count()==0
        assert page.evaluate('window.savedInput===document.querySelector("#input-note")')
        checks.append('dynamic_component_replacement_without_world_reload')
        page.locator('#input-note').press('Enter')
        action_message=page.locator('#action-status').inner_text()
        assert action_message.startswith(('操作已确认','Action confirmed')),action_message
        checks.append('input_event_returns_through_preview_provider')
        result=page.evaluate('''async (urls) => {
            const {SceneRenderer}=await import(urls.renderer);
            const {demoSnapshot}=await import(urls.demo);
            const mount=document.createElement('div');document.body.append(mount);
            const renderer=new SceneRenderer(mount,async()=>{},()=>{});
            const s=demoSnapshot();s.scene.root.children[1].props.text='<img src=x onerror="window.pwned=true">';
            renderer.render(s);
            const literal=mount.querySelector('[data-component-id="title"]').textContent;
            const noMarkup=mount.querySelector('img')===null;
            s.status='stale';s.sequence++;renderer.render(s);
            const disabled=[...mount.querySelectorAll('button,input')].every(x=>x.disabled);
            const input=mount.querySelector('input');
            s.status='online';s.sequence++;renderer.render(s);
            input.value='正在组合';input.dispatchEvent(new Event('compositionstart'));
            s.scene.data.note='不应覆盖';s.sequence++;renderer.render(s);
            const ime=input.value==='正在组合';
            mount.remove();return {literal,noMarkup,disabled,ime,pwned:window.pwned===true};
        }''', {'renderer':modules.get('renderer.js','http://127.0.0.1:1420/renderer.js'),'demo':modules.get('demo.js','http://127.0.0.1:1420/demo.js')})
        assert result['noMarkup'] and not result['pwned'] and result['literal'].startswith('<img')
        checks.append('provider_text_is_literal_not_html')
        assert result['disabled']
        checks.append('stale_world_disables_interaction')
        assert result['ime']
        checks.append('composition_is_not_overwritten')
        if offline:
            page.evaluate('''async (urls)=>{
                const {SceneRenderer}=await import(urls.renderer);const {demoSnapshot}=await import(urls.demo);
                const scene=demoSnapshot(true);const r=new SceneRenderer(document.getElementById('scene'),async()=>{},()=>{});
                r.render(scene);document.getElementById('title').textContent=scene.window.title;
                document.getElementById('action-status').textContent='';
            }''',{'renderer':modules['renderer.js'],'demo':modules['demo.js']})
        else:
            page.goto('http://127.0.0.1:1420/?preview=manager')
        page.wait_for_selector('[data-component-id="default-title"], [data-component-id="title"]')
        assert '世界管理器' in page.locator('#title').inner_text()
        assert page.locator('[data-component-id="new"]').is_visible()
        page.screenshot(path=str(OUT/'manager-preview.png'),full_page=True)
        checks.append('manager_fixture_uses_same_renderer')
        module_urls={'renderer':modules.get('renderer.js','http://127.0.0.1:1420/renderer.js'),'demo':modules.get('demo.js','http://127.0.0.1:1420/demo.js'),'i18n':modules.get('i18n.js','http://127.0.0.1:1420/i18n.js')}
        manager_scroll=page.evaluate('''async (urls) => {
            const {SceneRenderer}=await import(urls.renderer);const {demoSnapshot}=await import(urls.demo);
            const sample=demoSnapshot(true);const text=(id,value)=>({id,kind:'text',props:{text:value},children:[]});
            const button=(id,label,action)=>({id,kind:'button',props:{label,action},children:[]});
            sample.scene={data:{},root:{id:'manager-root',kind:'stack',props:{gap:12},children:[
              {id:'toolbar',kind:'row',props:{gap:8},children:[button('new','新建空白世界','new_world'),button('refresh','刷新','refresh')]},
              ...Array.from({length:16},(_,i)=>({id:`managed-${i}`,kind:'stack',props:{gap:8},children:[
                text(`managed-title-${i}`,`世界 ${i+1} · ${'很长的仪表盘说明'.repeat(5)}`),
                text(`managed-status-${i}`,'窗口显示中 · provider online'),
                button(`managed-show-${i}`,'显示窗口',`visibility_show:${i}`)
              ]}))
            ]}};
            const world=document.getElementById('world');const scene=document.getElementById('scene');
            document.body.classList.remove('preview-body');document.body.dataset.system='true';
            world.style.width='620px';world.style.height='320px';world.style.minHeight='0';world.style.maxHeight='320px';
            const renderer=new SceneRenderer(scene,async()=>null,()=>{});renderer.render(sample);
            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
            const header=document.querySelector('.chrome');const headerTopBefore=header.getBoundingClientRect().top;
            const before=scene.scrollTop;scene.scrollTop=scene.scrollHeight;
            await new Promise(resolve=>requestAnimationFrame(resolve));
            const headerTopAfter=header.getBoundingClientRect().top;
            document.body.dataset.titleBarVisible='false';const titleBarCanHide=getComputedStyle(header).display==='none';
            document.body.dataset.titleBarVisible='true';const titleBarCanShow=getComputedStyle(header).display!=='none';
            return {canScroll:scene.scrollTop>before,sceneOverflows:scene.scrollHeight>scene.clientHeight+1,
              worldWindowStaysBounded:world.scrollHeight<=world.clientHeight+1,
              worldOverflow:getComputedStyle(world).overflowY,sceneOverflow:getComputedStyle(scene).overflowY,
              managerScrollbar:getComputedStyle(scene).scrollbarWidth,toolbarSticky:getComputedStyle(scene.querySelector('[data-component-id="toolbar"]')).position,
              keyboardFocusable:scene.tabIndex===0,titleBarFixed:Math.abs(headerTopAfter-headerTopBefore)<=1,
              titleBarCanHide,titleBarCanShow};
        }''',module_urls)
        assert manager_scroll=={'canScroll':True,'sceneOverflows':True,'worldWindowStaysBounded':True,'worldOverflow':'hidden','sceneOverflow':'auto','managerScrollbar':'thin','toolbarSticky':'sticky','keyboardFocusable':True,'titleBarFixed':True,'titleBarCanHide':True,'titleBarCanShow':True},manager_scroll
        checks.append('manager_scroll_area_keeps_shell_fixed_and_reachable')
        context_result=page.evaluate('''async (urls) => {
            const {SceneRenderer}=await import(urls.renderer);const {demoSnapshot}=await import(urls.demo);
            const sample=demoSnapshot();const find=(node,id)=>node.id===id?node:node.children?.map(child=>find(child,id)).find(Boolean);
            const button=find(sample.scene.root,'structure');button.props.context_action='context_probe';
            const mount=document.createElement('div');document.body.append(mount);const calls=[];
            const renderer=new SceneRenderer(mount,async (...args)=>{calls.push(args);return `event-${calls.length}`;},()=>{});
            renderer.render(sample);mount.addEventListener('contextmenu',event=>{event.preventDefault();renderer.handleContextMenu(event);});
            const first=new MouseEvent('contextmenu',{bubbles:true,cancelable:true,button:2});
            mount.querySelector('[data-component-id="structure"]').dispatchEvent(first);
            await new Promise(resolve=>setTimeout(resolve,0));
            delete button.props.context_action;sample.sequence++;renderer.render(sample);
            const second=new MouseEvent('contextmenu',{bubbles:true,cancelable:true,button:2});
            mount.querySelector('[data-component-id="structure"]').dispatchEvent(second);
            await new Promise(resolve=>setTimeout(resolve,0));
            const result={registeredPrevented:first.defaultPrevented,unregisteredPrevented:second.defaultPrevented,calls};
            mount.remove();return result;
        }''',module_urls)
        assert context_result['registeredPrevented'] and context_result['unregisteredPrevented'],context_result
        assert context_result['calls']==[['structure',None,'context_menu']],context_result
        checks.append('native_context_menu_suppressed_and_registered_context_action_routed')
        form_result=page.evaluate('''async (urls) => {
            const {SceneRenderer}=await import(urls.renderer);const mount=document.createElement('div');document.body.append(mount);
            const calls=[];const scene={id:'form',revision:1,sequence:1,window:{},status:'online',actions:[],scene:{data:{},root:{id:'form-root',kind:'stack',props:{},children:[
              {id:'notes',kind:'textarea',props:{label:'备注',value:'',action:'notes.save',submit_label:'保存备注',shortcut:'ctrl_enter',shortcut_action:'submit:0'},children:[]},
              {id:'cancel',kind:'button',props:{label:'取消',action:'cancel.button',shortcut:'escape',shortcut_action:'cancel.escape'},children:[]}
            ]}}};
            const renderer=new SceneRenderer(mount,async(...args)=>{calls.push(args);return 'event';},()=>{});renderer.render(scene);
            const notes=mount.querySelector('textarea');const labelled=notes.labels?.[0]?.textContent==='备注';
            notes.value='第一行\\n第二行';notes.dispatchEvent(new Event('input',{bubbles:true}));
            scene.sequence++;scene.revision++;scene.scene.root.children[0].props.value='较旧的提供者值';renderer.render(scene);
            const draft=notes.value==='第一行\\n第二行';const label=mount.querySelector('.textarea-footer button').textContent;
            const ctrlEnter=new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true,bubbles:true,cancelable:true});notes.dispatchEvent(ctrlEnter);
            await new Promise(resolve=>setTimeout(resolve,0));
            const key=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});mount.dispatchEvent(key);
            await new Promise(resolve=>setTimeout(resolve,0));
            const composing=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});Object.defineProperty(composing,'isComposing',{value:true});mount.dispatchEvent(composing);
            await new Promise(resolve=>setTimeout(resolve,0));
            const result={labelled,draft,label,ctrlEnterPrevented:ctrlEnter.defaultPrevented,escapePrevented:key.defaultPrevented,compositionIgnored:!composing.defaultPrevented,calls};mount.remove();return result;
        }''',module_urls)
        assert form_result=={'labelled':True,'draft':True,'label':'保存备注','ctrlEnterPrevented':True,'escapePrevented':True,'compositionIgnored':True,'calls':[['notes','第一行\n第二行','control_enter'],['cancel',None,'escape']]},form_result
        checks.append('multiline_notes_preserve_draft_and_ctrl_enter_submits_with_escape_cancel')
        obsidian_workspace_result=page.evaluate('''async (urls)=>{
            const {SceneRenderer}=await import(urls.renderer);const mount=document.createElement('div');document.body.append(mount);const calls=[];
            const sample={id:'obsidian-workspace-fixture',revision:1,sequence:1,status:'online',actions:[],scene:{
              data:{focus_items:[{key:'窗口',value:'Synthetic tab'},{key:'文件数',value:42}]},
              root:{id:'obsidian-root',kind:'stack',props:{gap:8},children:[
                {id:'title-icon',kind:'icon',props:{name:'external',label:'打开现有 Obsidian 窗口'},children:[]},
                {id:'obsidian-workspace-title',kind:'button',props:{label:'Obsidian Workspace',action:'obsidian.activate',appearance:'title',native_window_action:{application:'obsidian',operation:'activate',title_contains:'Obsidian Workspace'}},children:[]},
                {id:'focus-items',kind:'key_value',props:{items:{$path:'/focus_items'}},children:[]},
                {id:'focus-progress',kind:'progress',props:{label:'Focus',value:30,max:100},children:[]}
              ]}
            }};
            const renderer=new SceneRenderer(mount,async(...args)=>{calls.push(args);return 'synthetic-action';},()=>{});renderer.render(sample);
            const title=mount.querySelector('[data-component-id="obsidian-workspace-title"]');title.click();
            await new Promise(resolve=>setTimeout(resolve,0));
            const result={titleAppearance:title.dataset.appearance,svgCount:mount.querySelectorAll('svg').length,
              nativeOperation:sample.scene.root.children[1].props.native_window_action.operation,
              activeTab:mount.querySelector('.kv-primary')?.textContent,progressCount:mount.querySelectorAll('.block-progress').length,
              calls};mount.remove();return result;
        }''',module_urls)
        assert obsidian_workspace_result=={'titleAppearance':'title','svgCount':1,'nativeOperation':'activate','activeTab':'Synthetic tab','progressCount':1,'calls':[['obsidian-workspace-title',None,'click']]},obsidian_workspace_result
        checks.append('obsidian_workspace_activation_metadata_and_focus_visuals_render_and_dispatch')
        focus_result=page.evaluate('''async (urls) => {
            const {SceneRenderer}=await import(urls.renderer);const mount=document.createElement('div');document.body.append(mount);
            let sample={id:'focus',revision:1,sequence:1,status:'online',actions:[],scene:{data:{},root:{id:'focus-root',kind:'stack',props:{},children:[
              {id:'notes',kind:'input',props:{label:'Notes',value:'',action:'notes.save'},children:[]}
            ]}}};
            const renderer=new SceneRenderer(mount,async()=> 'late-event',()=>{});renderer.render(sample);
            const notes=mount.querySelector('input');const submit=mount.querySelector('.block-input button');
            notes.value='draft';notes.dispatchEvent(new Event('input',{bubbles:true}));notes.focus();
            notes.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
            await new Promise(resolve=>setTimeout(resolve,0));submit.focus();
            sample={...sample,revision:2,sequence:2,actions:[{id:'late-event',component_id:'notes',status:'ok'}]};renderer.render(sample);
            return {activeIsSubmit:document.activeElement===submit,focusWasNotStolen:document.activeElement!==notes};
        }''',module_urls)
        assert focus_result=={'activeIsSubmit':True,'focusWasNotStolen':True},focus_result
        checks.append('late_action_ack_does_not_steal_focus')
        selection_result=page.evaluate('''async (urls) => {
            const {SceneRenderer}=await import(urls.renderer);const mount=document.createElement('div');mount.id='selection-group-test';document.body.append(mount);
            const button=(id,label,pressed)=>({id,kind:'button',props:{label,action:`select:${id}`,selection_group:'q0',selection_mode:'single',pressed},children:[]});
            const sample={id:'choice',revision:1,sequence:1,status:'online',actions:[],scene:{data:{},root:{id:'choice-root',kind:'stack',props:{},children:[button('one','One',true),button('two','Two',false),{id:'notes',kind:'textarea',props:{label:'Notes',value:'',action:'notes'},children:[]}]}}};
            const calls=[];let renderer;let pendingFocusPreserved=false;renderer=new SceneRenderer(mount,async(id,value,source)=>{
              calls.push([id,value,source]);if(id==='two'){
                sample.sequence++;sample.revision++;sample.scene.root.children[0].props.pressed=false;sample.scene.root.children[1].props.pressed=true;
                sample.actions=[{id:'event',component_id:'two',action:'select:two',status:'pending',message:null}];renderer.render(sample);
                pendingFocusPreserved=document.activeElement===mount.querySelector('[data-component-id="two"]')
                  &&!mount.querySelector('[data-component-id="two"]').disabled
                  &&mount.querySelector('[data-component-id="two"]').getAttribute('aria-disabled')==='true';
                sample.sequence++;sample.actions[0].status='ok';renderer.render(sample);
              }return 'event';
            },()=>{});renderer.render(sample);
            const one=mount.querySelector('[data-component-id="one"]');const two=mount.querySelector('[data-component-id="two"]');const notes=mount.querySelector('textarea');
            const before={one:one.tabIndex,two:two.tabIndex,notes:notes.tabIndex};one.focus();one.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}));
            await new Promise(resolve=>setTimeout(resolve,0));const after={active:document.activeElement.dataset.componentId,one:one.tabIndex,two:two.tabIndex,pressed:two.getAttribute('aria-pressed'),calls,pendingFocusPreserved};return {before,after};
        }''',module_urls)
        assert selection_result=={'before':{'one':0,'two':-1,'notes':0},'after':{'active':'two','one':-1,'two':0,'pressed':'true','calls':[['two',None,'click']],'pendingFocusPreserved':True}},selection_result
        checks.append('selection_group_has_one_tab_stop_and_arrow_keys_select_single_choice')
        page.keyboard.press('Tab')
        tab_focus=page.evaluate('document.activeElement?.id')
        assert tab_focus=='textarea-notes',tab_focus
        page.locator('#selection-group-test').evaluate('el=>el.remove()')
        checks.append('tab_from_selected_option_moves_directly_to_notes')
        layout_result=page.evaluate('''async (urls) => {
            const {SceneRenderer}=await import(urls.renderer);const {demoSnapshot}=await import(urls.demo);
            const longCjk='仪表盘待推进事项与阶段说明'.repeat(14);const longToken='WincraftDashboardValueWithoutBreaks'.repeat(6);
            const leaf=(id,kind,props)=>({id,kind,props,children:[]});
            const sample=demoSnapshot();sample.scene={data:{},root:{id:'overflow-root',kind:'stack',props:{gap:8},children:[
              leaf('overflow-title','text',{text:longCjk,size:'title'}),
              {id:'overflow-row',kind:'row',props:{gap:12},children:[
                leaf('overflow-metric','metric',{label:longCjk,value:longToken,unit:longCjk,caption:longCjk}),
                leaf('overflow-kv','key_value',{items:[{key:longCjk,value:longToken},{key:'状态',value:longCjk}]})
              ]},
              leaf('overflow-badge','badge',{text:longToken}),
              leaf('overflow-button','button',{label:longCjk,action:'probe'}),
              leaf('overflow-input','input',{label:longCjk,value:'',placeholder:longToken,action:'probe-input'})
            ]}};
            const world=document.createElement('main');world.className='world';world.style.width='160px';world.style.height='auto';world.style.maxHeight='none';world.style.minHeight='0';
            const scene=document.createElement('section');scene.className='scene';const mount=document.createElement('div');scene.append(mount);world.append(scene);document.body.classList.add('preview-body');document.body.append(world);
            const renderer=new SceneRenderer(mount,async()=>null,()=>{});renderer.render(sample);
            const results=[];
            for(const width of [160,240,560]){
              world.style.width=`${width}px`;
              await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
              const targets=[...world.querySelectorAll('.block-text,.block-badge,.metric-label,.metric-value,.metric-unit,.metric-caption,.kv-row dt,.kv-row dd,.block-button,.block-input label')];
              const overflow=targets.filter(el=>el.scrollWidth>el.clientWidth+1).map(el=>el.className||el.dataset.componentId);
              const first=world.getBoundingClientRect().height;
              await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
              const second=world.getBoundingClientRect().height;
              results.push({width,overflow,stable:Math.abs(first-second)<=1,height:first});
            }
            world.remove();return results;
        }''',module_urls)
        assert all(not result['overflow'] and result['stable'] for result in layout_result),layout_result
        checks.append('long_dashboard_text_wraps_without_overflow_and_layout_settles')
        locale_result=page.evaluate('''async (urls)=>{
            const {setLocale,t}=await import(urls.i18n);const providerText=document.querySelector('[data-component-id="title"]')?.textContent;
            const fallback=document.createElement('span');fallback.dataset.i18n='host.translation.missing';document.body.append(fallback);
            setLocale('en-US');const chrome=document.querySelector('.chrome');const english={lang:document.documentElement.lang,minimize:document.getElementById('minimize').getAttribute('aria-label'),preview:document.getElementById('preview').textContent,chromeFits:chrome.scrollWidth<=chrome.clientWidth+1,bodyFits:document.body.scrollWidth<=window.innerWidth+1};
            const missing=t('host.translation.missing');const missingMarked=fallback.dataset.translationFallback==='host.translation.missing'&&Number(document.documentElement.dataset.localeFallbackCount)>0;
            setLocale('zh-CN');const unchanged=document.querySelector('[data-component-id="title"]')?.textContent===providerText;
            fallback.remove();return {english,missing,missingMarked,providerTextUnchanged:unchanged};
        }''',module_urls)
        assert locale_result['english']['lang']=='en-US' and locale_result['english']['minimize']=='Minimize window',locale_result
        assert 'Browser preview' in locale_result['english']['preview'],locale_result
        assert locale_result['english']['chromeFits'] and locale_result['english']['bodyFits'],locale_result
        assert locale_result['missing']=='host.translation.missing' and locale_result['missingMarked'],locale_result
        assert locale_result['providerTextUnchanged'],locale_result
        checks.append('host_locales_fallback_and_provider_text_preserved')
        theme_result=page.evaluate('''async (urls)=>{
            const {SceneRenderer}=await import(urls.renderer);const id='theme-boundary-test';
            const world=document.createElement('main');world.id=id;world.className='world';
            const chrome=document.createElement('header');chrome.className='chrome';chrome.textContent='WinCraft trusted chrome';
            const scene=document.createElement('section');scene.className='scene';world.append(chrome,scene);document.body.append(world);
            const theme={background:'#111827',foreground:'#F9FAFB',accent:'#67E8F9',font_scale:0.9,radius_px:12,spacing_px:24};
            const sample={id:'theme-world',revision:1,sequence:1,status:'online',actions:[],scene:{data:{},theme,root:{id:'theme-root',kind:'stack',props:{gap:12},children:[
              {id:'theme-title',kind:'text',props:{text:'Theme preview',size:'heading'},children:[]},
              {id:'theme-button',kind:'button',props:{label:'Action',action:'probe',tone:'accent'},children:[]},
              {id:'theme-progress',kind:'progress',props:{label:'Progress',value:50,max:100},children:[]}
            ]}}};
            const renderer=new SceneRenderer(scene,async()=>null,()=>{});renderer.render(sample);
            const button=scene.querySelector('button');const initial={
              background:getComputedStyle(scene).backgroundColor,
              foreground:getComputedStyle(scene).color,
              trustedChromeColor:getComputedStyle(chrome).color,
              radius:getComputedStyle(button).borderRadius,
              gap:scene.firstElementChild.style.gap,
              font:getComputedStyle(scene).fontSize
            };
            sample.sequence++;sample.scene.theme={...theme,background:'url(javascript:alert(1))'};
            renderer.render(sample);
            const invalidFallback=scene.style.getPropertyValue('--wc-theme-background')==='';
            sample.sequence++;sample.scene.theme=theme;renderer.render(sample);
            const beforeZoom=getComputedStyle(scene).fontSize;
            const zoomIn=new KeyboardEvent('keydown',{key:'+',code:'Equal',shiftKey:true,ctrlKey:true,bubbles:true,cancelable:true});
            document.dispatchEvent(zoomIn);
            const userZoom=document.documentElement.style.getPropertyValue('--wc-user-font-scale');
            const afterZoom=getComputedStyle(scene).fontSize;
            const input=document.createElement('input');scene.append(input);input.focus();
            const editableZoom=new KeyboardEvent('keydown',{key:'+',code:'Equal',shiftKey:true,ctrlKey:true,bubbles:true,cancelable:true});
            input.dispatchEvent(editableZoom);
            const editableIgnored=!editableZoom.defaultPrevented&&document.documentElement.style.getPropertyValue('--wc-user-font-scale')===userZoom;
            input.remove();document.activeElement?.blur?.();
            const reset=new KeyboardEvent('keydown',{key:'0',code:'Digit0',ctrlKey:true,bubbles:true,cancelable:true});document.dispatchEvent(reset);
            const resetUsesTheme=document.documentElement.style.getPropertyValue('--wc-user-font-scale')===''&&getComputedStyle(scene).fontSize===beforeZoom;
            return {initial,invalidFallback,userZoom,afterZoom,editableIgnored,resetUsesTheme,worldId:id};
        }''',module_urls)
        assert theme_result['initial']['background']=='rgb(17, 24, 39)',theme_result
        assert theme_result['initial']['foreground']=='rgb(249, 250, 251)',theme_result
        assert theme_result['initial']['trustedChromeColor']=='rgb(200, 214, 228)',theme_result
        assert theme_result['initial']['radius']=='12px' and theme_result['initial']['gap']=='24px',theme_result
        assert theme_result['initial']['font']=='12.6px',theme_result
        assert theme_result['invalidFallback'],theme_result
        assert theme_result['userZoom']=='1.1' and theme_result['afterZoom']=='15.4px',theme_result
        assert theme_result['editableIgnored'] and theme_result['resetUsesTheme'],theme_result
        page.emulate_media(forced_colors='active',reduced_motion='reduce')
        preference_result=page.locator(f"#{theme_result['worldId']} .scene").evaluate('''scene=>{
            const probe=document.createElement('span');probe.style.backgroundColor='Canvas';document.body.append(probe);
            const canvas=getComputedStyle(probe).backgroundColor;probe.remove();
            const progress=scene.querySelector('.progress-fill');
            return {forcedColors:getComputedStyle(scene).backgroundColor===canvas,reducedMotion:getComputedStyle(progress).transitionDuration==='0s'};
        }''')
        assert preference_result=={'forcedColors':True,'reducedMotion':True},preference_result
        page.emulate_media(forced_colors='none',reduced_motion='no-preference')
        page.locator(f"#{theme_result['worldId']}").evaluate('el=>el.remove()')
        checks.extend(['theme_tokens_are_bounded_and_leave_trusted_chrome_host_owned','local_zoom_overrides_provider_font_scale_and_skips_editable_controls','forced_colors_and_reduced_motion_override_theme'])
        assert not errors,errors
        checks.append('no_browser_runtime_errors')
        browser.close()
    result={'status':'PASS','scope':('Chromium offline DOM with compiled TypeScript modules loaded via in-memory blobs; mock provider; NOT native desktop' if offline else 'Chromium + actual compiled TypeScript + mock provider; NOT native desktop'),'checks':checks}
    (OUT/'browser-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
finally:
    server.terminate()
    try:server.wait(timeout=3)
    except subprocess.TimeoutExpired:server.kill();server.wait()
    log.close()
