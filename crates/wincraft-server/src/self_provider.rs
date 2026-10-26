//! A local provider that builds the manager/settings world using the SAME scene
//! vocabulary and exclusive-writer engine as external providers. Only explicit
//! operator actions (rescue/destroy) have extra authority.
use crate::{Hub, Notice};
use serde_json::{json, Value};
use std::time::Duration;
use uuid::Uuid;
use wincraft_core::*;

#[derive(Clone)]
pub struct ManagerProvider {
    pub session: Uuid,
    pub world_id: Uuid,
    pub lease: LeaseKey,
}
#[derive(Clone)]
struct Settings {
    title: String,
    always_on_top: bool,
    pending_close: Option<Uuid>,
}
fn node(id: impl Into<String>, kind: Kind, props: Value, children: Vec<Node>) -> Node {
    Node::new(&id.into(), kind, props, children)
}
impl ManagerProvider {
    pub fn install(hub: &Hub) -> Result<Self> {
        let mut e = hub.lock();
        let session = e.register("host.manager".into(), true)?;
        let window = WindowSpec {
            title: "窗构 · 世界管理器".into(),
            width: 620.0,
            height: 700.0,
            always_on_top: false,
            visible: false,
            ..Default::default()
        };
        let c = e.create(session, window, JoinPolicy::Invite, true, true, hub.now())?;
        Ok(Self {
            session,
            world_id: c.world.id,
            lease: c.lease.unwrap(),
        })
    }
    pub fn show(&self, hub: &Hub) -> Result<()> {
        hub.lock()
            .operator_visibility(self.session, self.world_id, true)?;
        hub.changed(self.world_id);
        Ok(())
    }
    pub fn rescue_all(&self, hub: &Hub) {
        let ids: Vec<_> = hub.lock().worlds.keys().copied().collect();
        for id in ids {
            if hub.lock().rescue(self.session, id).is_ok() {
                hub.changed(id);
            }
        }
    }
    pub fn blank(&self, hub: &Hub) -> Result<Value> {
        hub.dispatch(
            self.session,
            "world.create",
            json!({"window":{"title":"空白世界"},"join_policy":"open_authenticated","claim":false}),
        )
    }
    pub fn spawn(&self, hub: Hub, descriptor_path: String) {
        let manager = self.clone();
        tokio::spawn(async move {
            let mut settings = Settings {
                title: "空白世界".into(),
                always_on_top: true,
                pending_close: None,
            };
            let mut events = hub.subscribe();
            let mut timer = tokio::time::interval(Duration::from_millis(750));
            loop {
                tokio::select! {
                    _=timer.tick()=>{
                        let _=hub.dispatch(manager.session,"session.ping",json!({}));
                        if let Err(e)=manager.refresh(&hub,&settings,&descriptor_path){eprintln!("manager refresh: {e}");}
                    },
                    event=events.recv()=>{
                        match event{
                            Ok(Notice::Directed(sid,value)) if sid==manager.session=>{
                                if let Some(data)=value.get("data"){
                                    if let Ok(event)=serde_json::from_value::<UiEvent>(data.clone()){
                                        let result=manager.handle(&hub,&mut settings,&event);
                                        let (ok,message)=match result{Ok(())=>(true,None),Err(e)=>(false,Some(e.to_string()))};
                                        let _=hub.dispatch(manager.session,"action.result",json!({"world_id":manager.world_id,"lease":manager.lease,
                                            "event_id":event.id,"ok":ok,"message":message}));
                                        let _=manager.refresh(&hub,&settings,&descriptor_path);
                                    }
                                }
                            },
                            Err(tokio::sync::broadcast::error::RecvError::Closed)=>break,
                            _=>{},
                        }
                    }
                }
            }
        });
    }
    fn handle(&self, hub: &Hub, s: &mut Settings, event: &UiEvent) -> Result<()> {
        match event.action.as_str() {
            "new_world" => {
                hub.dispatch(self.session,"world.create",json!({"window":{"title":s.title,"always_on_top":s.always_on_top},"join_policy":"open_authenticated","claim":false}))?;
            }
            "refresh" => {}
            "settings.title" => {
                s.title = event
                    .value
                    .as_str()
                    .unwrap_or("空白世界")
                    .chars()
                    .take(100)
                    .collect();
            }
            "settings.top" => {
                s.always_on_top = !s.always_on_top;
            }
            "close_cancel" => s.pending_close = None,
            a if a.starts_with("rescue:") => {
                let id = parse_id(a, "rescue:")?;
                hub.lock().rescue(self.session, id)?;
                hub.changed(id);
            }
            a if a.starts_with("release_hold:") => {
                let id = parse_id(a, "release_hold:")?;
                hub.lock().operator_release_hold(self.session, id)?;
                hub.changed(id);
            }
            a if a.starts_with("visibility_show:") => {
                let id = parse_id(a, "visibility_show:")?;
                hub.lock().operator_visibility(self.session, id, true)?;
                hub.changed(id);
            }
            a if a.starts_with("visibility_hide:") => {
                let id = parse_id(a, "visibility_hide:")?;
                hub.lock().operator_visibility(self.session, id, false)?;
                hub.changed(id);
            }
            a if a.starts_with("close_request:") => {
                s.pending_close = Some(parse_id(a, "close_request:")?)
            }
            a if a.starts_with("close_confirm:") => {
                let id = parse_id(a, "close_confirm:")?;
                if s.pending_close != Some(id) {
                    return Err(Fault::new(
                        "FORBIDDEN",
                        "confirm closing the selected world first",
                    ));
                }
                if id == self.world_id {
                    return Err(Fault::new("FORBIDDEN", "manager is protected"));
                }
                let members = hub.lock().operator_destroy(self.session, id)?;
                hub.deleted(id, members);
                s.pending_close = None;
            }
            _ => {
                return Err(Fault::new(
                    "UNKNOWN_ACTION",
                    "manager action not recognized",
                ))
            }
        }
        Ok(())
    }
    fn refresh(&self, hub: &Hub, settings: &Settings, descriptor: &str) -> Result<()> {
        let summaries = hub.lock().list(self.session)?;
        let mut rows = vec![
            node(
                "hero",
                Kind::Text,
                json!({"text":"让程序长出可组合的窗口","size":"title"}),
                vec![],
            ),
            node(
                "sub",
                Kind::Text,
                json!({"text":"世界即窗口 · 一个写入者，多个快照观察者","tone":"muted"}),
                vec![],
            ),
            node(
                "toolbar",
                Kind::Row,
                json!({"gap":8}),
                vec![
                    node(
                        "new",
                        Kind::Button,
                        json!({"label":"新建空白世界","action":"new_world","tone":"accent"}),
                        vec![],
                    ),
                    node(
                        "refresh",
                        Kind::Button,
                        json!({"label":"刷新","action":"refresh"}),
                        vec![],
                    ),
                ],
            ),
            node(
                "stats",
                Kind::Metric,
                json!({"label":"开放的世界","value":summaries.iter().filter(|w|!w.system).count(),"unit":"个","caption":"管理器自身也是内部提供者构建的世界"}),
                vec![],
            ),
            node("settings-line", Kind::Divider, json!({}), vec![]),
            node(
                "settings-label",
                Kind::Text,
                json!({"text":"本次会话的默认设置","size":"heading"}),
                vec![],
            ),
            node(
                "default-title",
                Kind::Input,
                json!({"label":"新世界名称","value":settings.title,"action":"settings.title","placeholder":"输入后按 Enter 提交"}),
                vec![],
            ),
            node(
                "default-top",
                Kind::Button,
                json!({"label":if settings.always_on_top{"默认置顶：开启"}else{"默认置顶：关闭"},"action":"settings.top"}),
                vec![],
            ),
            node(
                "descriptor",
                Kind::KeyValue,
                json!({"items":[{"key":"连接描述文件","value":descriptor},{"key":"保存策略","value":"不保存业务状态、借用关系与设置；重启可重建"}]}),
                vec![],
            ),
            node("worlds-line", Kind::Divider, json!({}), vec![]),
        ];
        for w in summaries.into_iter().filter(|w| !w.system) {
            let id = w.id.to_string();
            let snap = hub.renderer_snapshot(w.id)?;
            let mut controls = vec![node(
                format!("r-{id}"),
                Kind::Button,
                json!({"label":"接管并找回","action":format!("rescue:{id}")}),
                vec![],
            )];
            let visible = snap.window.visible;
            controls.push(node(
                format!("visibility-{id}"),
                Kind::Button,
                json!({
                    "label": if visible { "隐藏窗口" } else { "显示窗口" },
                    "action": format!("visibility_{}:{id}", if visible { "hide" } else { "show" })
                }),
                vec![],
            ));
            if w.write_blocked {
                controls.push(node(
                    format!("unhold-{id}"),
                    Kind::Button,
                    json!({"label":"解除接管","action":format!("release_hold:{id}")}),
                    vec![],
                ));
            }
            if settings.pending_close == Some(w.id) {
                controls.push(node(format!("yes-{id}"),Kind::Button,json!({"label":"确认关闭","action":format!("close_confirm:{id}"),"tone":"danger"}),vec![]));
                controls.push(node(
                    format!("no-{id}"),
                    Kind::Button,
                    json!({"label":"取消","action":"close_cancel"}),
                    vec![],
                ));
            } else {
                controls.push(node(
                    format!("c-{id}"),
                    Kind::Button,
                    json!({"label":"关闭世界","action":format!("close_request:{id}")}),
                    vec![],
                ));
            }
            rows.push(node(format!("w-{id}"),Kind::Stack,json!({"gap":10}),vec![
                node(format!("t-{id}"),Kind::Text,json!({"text":w.title,"size":"heading"}),vec![]),
                node(format!("b-{id}"),Kind::Badge,json!({"text":format!("{} · {}",w.status,w.writer_name.unwrap_or_else(||"无写入者".into())),"tone":if w.status=="online"{"success"}else{"muted"}}),vec![]),
                node(format!("v-{id}"),Kind::Text,json!({"text":format!("窗口：{} · 标题栏：{}",if snap.window.visible{"显示"}else{"隐藏"},if snap.window.title_bar_visible{"显示"}else{"隐藏"}),"tone":"muted"}),vec![]),
                node(format!("i-{id}"),Kind::Text,json!({"text":format!("ID {id}"),"tone":"muted"}),vec![]),
                node(format!("n-{id}"),Kind::Text,json!({"text":format!("原生窗口：{}{}",snap.native.state,snap.native.error.map(|e|format!(" · {e}")).unwrap_or_default()),"tone":"muted"}),vec![]),
                node(format!("controls-{id}"),Kind::Row,json!({"gap":8}),controls),
                node(format!("d-{id}"),Kind::Divider,json!({}),vec![]),
            ]));
        }
        let scene = Scene {
            root: node("root", Kind::Stack, json!({"gap":16}), rows),
            data: json!({}),
        };
        let snapshot = hub.lock().read(self.session, self.world_id)?;
        if scene != snapshot.scene {
            hub.dispatch(self.session,"scene.replace",json!({"world_id":self.world_id,"lease":self.lease,"expected_revision":snapshot.revision,"scene":scene}))?;
        }
        Ok(())
    }
}
fn parse_id(action: &str, prefix: &str) -> Result<Uuid> {
    action
        .strip_prefix(prefix)
        .and_then(|s| s.parse().ok())
        .ok_or_else(|| Fault::new("INVALID_ACTION", "invalid world id"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manager_lists_hidden_worlds_and_can_show_without_destroying_them() {
        let hub = Hub::new(true);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let created = hub
            .dispatch(
                manager.session,
                "world.create",
                json!({
                    "window": {"title":"hidden fixture", "visible":false},
                    "join_policy":"open_authenticated",
                    "claim":false
                }),
            )
            .expect("hidden world creates");
        let world_id = Uuid::parse_str(
            created["world"]["id"]
                .as_str()
                .expect("created world id is present"),
        )
        .expect("created world id is valid");
        let mut settings = Settings {
            title: "fixture".into(),
            always_on_top: true,
            pending_close: None,
        };

        manager
            .refresh(&hub, &settings, "<descriptor>")
            .expect("manager refreshes");
        let manager_snapshot = hub
            .renderer_snapshot(manager.world_id)
            .expect("manager snapshot exists");
        let scene = serde_json::to_string(&manager_snapshot.scene).expect("scene serializes");
        assert!(scene.contains("窗口：隐藏 · 标题栏：显示"));
        assert!(scene.contains(&format!("visibility_show:{world_id}")));

        manager
            .handle(
                &hub,
                &mut settings,
                &UiEvent {
                    id: Uuid::new_v4(),
                    world_id: manager.world_id,
                    component_id: format!("visibility-{world_id}"),
                    action: format!("visibility_show:{world_id}"),
                    value: Value::Null,
                    lease_epoch: 0,
                    revision: manager_snapshot.revision,
                },
            )
            .expect("operator can resurface the world");

        let restored = hub
            .renderer_snapshot(world_id)
            .expect("hidden world remains alive");
        assert!(restored.window.visible);
        assert_eq!(restored.window.title, "hidden fixture");
    }
}
