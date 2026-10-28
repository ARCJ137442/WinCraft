//! A local provider that builds the manager/settings world using the SAME scene
//! vocabulary and exclusive-writer engine as external providers. Only explicit
//! operator actions (rescue/destroy) have extra authority.
use crate::{Hub, Notice};
use serde_json::{json, Value};
use std::{sync::OnceLock, time::Duration};
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
fn manager_text(locale: &str, key: &str) -> String {
    static ZH: OnceLock<Value> = OnceLock::new();
    static EN: OnceLock<Value> = OnceLock::new();
    let (slot, source) = if locale == "en-US" {
        (
            &EN,
            include_str!("../../../apps/desktop/src/locales/en-US.json"),
        )
    } else {
        (
            &ZH,
            include_str!("../../../apps/desktop/src/locales/zh-CN.json"),
        )
    };
    let catalog = slot.get_or_init(|| serde_json::from_str(source).unwrap_or(Value::Null));
    catalog
        .get(key)
        .and_then(Value::as_str)
        .or_else(|| {
            let fallback = ZH.get_or_init(|| {
                serde_json::from_str(include_str!("../../../apps/desktop/src/locales/zh-CN.json"))
                    .unwrap_or(Value::Null)
            });
            fallback.get(key).and_then(Value::as_str)
        })
        .unwrap_or(key)
        .to_owned()
}
fn node(id: impl Into<String>, kind: Kind, props: Value, children: Vec<Node>) -> Node {
    Node::new(&id.into(), kind, props, children)
}
impl ManagerProvider {
    pub fn install(hub: &Hub) -> Result<Self> {
        let mut e = hub.lock();
        let session = e.register("host.manager".into(), true)?;
        let locale = hub.locale();
        let window = WindowSpec {
            title: manager_text(&locale, "manager.window_title"),
            width: 620.0,
            height: 700.0,
            always_on_top: true,
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
        hub.apply_state_change(self.world_id, EventSource::Human, None, |core| {
            core.operator_visibility(self.session, self.world_id, true)?;
            Ok(true)
        })?;
        Ok(())
    }
    pub fn rescue_all(&self, hub: &Hub) {
        let ids: Vec<_> = hub.lock().worlds.keys().copied().collect();
        for id in ids {
            let _ = hub.apply_state_change(id, EventSource::Human, None, |core| {
                core.rescue(self.session, id).map(|_| true)
            });
        }
    }
    pub fn blank(&self, hub: &Hub) -> Result<Value> {
        hub.dispatch(
            self.session,
            "world.create",
            json!({"window":{"title":manager_text(&hub.locale(),"manager.default_world")},"join_policy":"open_authenticated","claim":false}),
        )
    }
    pub fn spawn(&self, hub: Hub, descriptor_path: String) {
        let manager = self.clone();
        tokio::spawn(async move {
            let mut settings = Settings {
                title: manager_text(&hub.locale(), "manager.default_world"),
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
                let value = event
                    .value
                    .as_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| manager_text(&hub.locale(), "manager.default_world"));
                s.title = value.chars().take(100).collect();
            }
            "settings.top" => {
                s.always_on_top = !s.always_on_top;
            }
            "settings.locale" => {
                let old_locale = hub.locale();
                let new_locale = if old_locale == "zh-CN" {
                    "en-US"
                } else {
                    "zh-CN"
                };
                if s.title == manager_text(&old_locale, "manager.default_world") {
                    s.title = manager_text(new_locale, "manager.default_world");
                }
                hub.set_locale(new_locale)?;
                let snapshot = hub.renderer_snapshot(self.world_id)?;
                hub.dispatch(
                    self.session,
                    "window.configure",
                    json!({"world_id":self.world_id,"lease":self.lease,"expected_revision":snapshot.revision,
                        "patch":{"title":manager_text(new_locale,"manager.window_title")}}),
                )?;
            }
            "close_cancel" => s.pending_close = None,
            a if a.starts_with("rescue:") => {
                let id = parse_id(a, "rescue:")?;
                hub.apply_state_change(
                    id,
                    EventSource::Operator,
                    Some(event.id.to_string()),
                    |core| core.rescue(self.session, id).map(|_| true),
                )?;
            }
            a if a.starts_with("release_hold:") => {
                let id = parse_id(a, "release_hold:")?;
                hub.apply_state_change(
                    id,
                    EventSource::Operator,
                    Some(event.id.to_string()),
                    |core| core.operator_release_hold(self.session, id).map(|_| true),
                )?;
            }
            a if a.starts_with("visibility_show:") => {
                let id = parse_id(a, "visibility_show:")?;
                hub.apply_state_change(
                    id,
                    EventSource::Operator,
                    Some(event.id.to_string()),
                    |core| {
                        core.operator_visibility(self.session, id, true)?;
                        Ok(true)
                    },
                )?;
            }
            a if a.starts_with("visibility_hide:") => {
                let id = parse_id(a, "visibility_hide:")?;
                hub.apply_state_change(
                    id,
                    EventSource::Operator,
                    Some(event.id.to_string()),
                    |core| {
                        core.operator_visibility(self.session, id, false)?;
                        Ok(true)
                    },
                )?;
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
        let locale = hub.locale();
        let summaries = hub.lock().list(self.session)?;
        let mut rows = vec![
            node(
                "hero",
                Kind::Text,
                json!({"text":manager_text(&locale,"manager.hero"),"size":"title"}),
                vec![],
            ),
            node(
                "sub",
                Kind::Text,
                json!({"text":manager_text(&locale,"manager.subtitle"),"tone":"muted"}),
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
                        json!({"label":manager_text(&locale,"manager.new_world"),"action":"new_world","tone":"accent"}),
                        vec![],
                    ),
                    node(
                        "refresh",
                        Kind::Button,
                        json!({"label":manager_text(&locale,"manager.refresh"),"action":"refresh"}),
                        vec![],
                    ),
                    node(
                        "locale",
                        Kind::Button,
                        json!({"label":manager_text(&locale,"manager.language_toggle"),"action":"settings.locale"}),
                        vec![],
                    ),
                ],
            ),
            node(
                "stats",
                Kind::Metric,
                json!({"label":manager_text(&locale,"manager.open_worlds"),"value":summaries.iter().filter(|w|!w.system).count(),"unit":manager_text(&locale,"manager.worlds_unit"),"caption":manager_text(&locale,"manager.manager_caption")}),
                vec![],
            ),
            node("settings-line", Kind::Divider, json!({}), vec![]),
            node(
                "settings-label",
                Kind::Text,
                json!({"text":manager_text(&locale,"manager.settings"),"size":"heading"}),
                vec![],
            ),
            node(
                "default-title",
                Kind::Input,
                json!({"label":manager_text(&locale,"manager.new_world_name"),"value":settings.title,"action":"settings.title","placeholder":manager_text(&locale,"manager.name_placeholder")}),
                vec![],
            ),
            node(
                "default-top",
                Kind::Button,
                json!({"label":manager_text(&locale,if settings.always_on_top{"manager.top_enabled"}else{"manager.top_disabled"}),"action":"settings.top"}),
                vec![],
            ),
            node(
                "descriptor",
                Kind::KeyValue,
                json!({"items":[{"key":manager_text(&locale,"manager.descriptor"),"value":descriptor},{"key":manager_text(&locale,"manager.save_policy_key"),"value":manager_text(&locale,"manager.save_policy")}]}),
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
                json!({"label":manager_text(&locale,"manager.rescue"),"action":format!("rescue:{id}")}),
                vec![],
            )];
            let visible = snap.window.visible;
            controls.push(node(
                format!("visibility-{id}"),
                Kind::Button,
                json!({
                    "label": manager_text(&locale,if visible { "manager.hide" } else { "manager.show" }),
                    "action": format!("visibility_{}:{id}", if visible { "hide" } else { "show" })
                }),
                vec![],
            ));
            if w.write_blocked {
                controls.push(node(
                    format!("unhold-{id}"),
                    Kind::Button,
                    json!({"label":manager_text(&locale,"manager.release_hold"),"action":format!("release_hold:{id}")}),
                    vec![],
                ));
            }
            if settings.pending_close == Some(w.id) {
                controls.push(node(format!("yes-{id}"),Kind::Button,json!({"label":manager_text(&locale,"manager.confirm_close"),"action":format!("close_confirm:{id}"),"tone":"danger"}),vec![]));
                controls.push(node(
                    format!("no-{id}"),
                    Kind::Button,
                    json!({"label":manager_text(&locale,"manager.cancel"),"action":"close_cancel"}),
                    vec![],
                ));
            } else {
                controls.push(node(
                    format!("c-{id}"),
                    Kind::Button,
                    json!({"label":manager_text(&locale,"manager.close_world"),"action":format!("close_request:{id}")}),
                    vec![],
                ));
            }
            rows.push(node(format!("w-{id}"),Kind::Stack,json!({"gap":10}),vec![
                node(format!("t-{id}"),Kind::Text,json!({"text":w.title,"size":"heading"}),vec![]),
                node(format!("b-{id}"),Kind::Badge,json!({"text":format!("{} · {}",manager_text(&locale,&format!("manager.world_status.{}",w.status)),w.writer_name.unwrap_or_else(||manager_text(&locale,"manager.no_writer"))),"tone":if w.status=="online"{"success"}else{"muted"}}),vec![]),
                node(format!("v-{id}"),Kind::Text,json!({"text":format!("{}: {} · {}: {}",manager_text(&locale,"manager.window"),manager_text(&locale,if snap.window.visible{"manager.window_visible"}else{"manager.window_hidden"}),manager_text(&locale,"manager.titlebar"),manager_text(&locale,if snap.window.title_bar_visible{"manager.titlebar_visible"}else{"manager.titlebar_hidden"})),"tone":"muted"}),vec![]),
                node(format!("i-{id}"),Kind::Text,json!({"text":format!("ID {id}"),"tone":"muted"}),vec![]),
                node(format!("n-{id}"),Kind::Text,json!({"text":format!("{}: {}{}",manager_text(&locale,"manager.native_state"),manager_text(&locale,&format!("native.{}",snap.native.state)),snap.native.error.map(|e|format!(" · {e}")).unwrap_or_default()),"tone":"muted"}),vec![]),
                node(format!("controls-{id}"),Kind::Row,json!({"gap":8}),controls),
                node(format!("d-{id}"),Kind::Divider,json!({}),vec![]),
            ]));
        }
        let scene = Scene {
            root: node("root", Kind::Stack, json!({"gap":16}), rows),
            data: json!({"host_locale":locale}),
            theme: None,
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
        assert!(scene.contains("窗口: 窗口隐藏 · 标题栏: 标题栏显示"));
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

    #[test]
    fn manager_lists_an_invite_popup_world_without_changing_its_writer() {
        let hub = Hub::new(true);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let popup = {
            let mut core = hub.lock();
            let provider = core
                .register("popup-ask.synthetic".into(), false)
                .expect("provider registers");
            core.create(
                provider,
                wincraft_core::WindowSpec {
                    title: "Popup-Ask synthetic fixture".into(),
                    ..Default::default()
                },
                wincraft_core::JoinPolicy::Invite,
                true,
                false,
                hub.now(),
            )
            .expect("invite popup world creates")
        };
        let before = hub
            .renderer_snapshot(popup.world.id)
            .expect("provider snapshot exists");
        let settings = Settings {
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
        let manager_scene =
            serde_json::to_string(&manager_snapshot.scene).expect("manager scene serializes");
        assert!(manager_scene.contains("Popup-Ask synthetic fixture"));
        assert!(manager_scene.contains(&format!("visibility_hide:{}", popup.world.id)));

        let after = hub
            .renderer_snapshot(popup.world.id)
            .expect("popup provider snapshot remains");
        assert_eq!(after.epoch, before.epoch);
        assert_eq!(after.writer, before.writer);
        assert!(after.window.visible);
    }

    #[test]
    fn manager_language_toggle_localizes_internal_world_and_host_preference() {
        let hub = Hub::new(true);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let mut settings = Settings {
            title: "空白世界".into(),
            always_on_top: true,
            pending_close: None,
        };
        manager
            .refresh(&hub, &settings, "<descriptor>")
            .expect("manager refreshes");
        let initial = hub
            .renderer_snapshot(manager.world_id)
            .expect("manager snapshot exists");
        assert_eq!(initial.scene.data["host_locale"], "zh-CN");
        assert_eq!(
            initial
                .scene
                .root
                .find("locale")
                .and_then(|node| node.props.get("action"))
                .and_then(Value::as_str),
            Some("settings.locale")
        );

        manager
            .handle(
                &hub,
                &mut settings,
                &UiEvent {
                    id: Uuid::new_v4(),
                    world_id: manager.world_id,
                    component_id: "locale".into(),
                    action: "settings.locale".into(),
                    value: Value::Null,
                    lease_epoch: initial.epoch,
                    revision: initial.revision,
                },
            )
            .expect("language toggles through the internal provider");
        manager
            .refresh(&hub, &settings, "<descriptor>")
            .expect("English manager refreshes");

        let english = hub
            .renderer_snapshot(manager.world_id)
            .expect("manager snapshot exists");
        let scene = serde_json::to_string(&english.scene).expect("scene serializes");
        assert_eq!(hub.locale(), "en-US");
        assert_eq!(english.scene.data["host_locale"], "en-US");
        assert_eq!(english.window.title, "WinCraft · World Manager");
        assert!(scene.contains("Build windows from composable pieces"));
        assert!(scene.contains("Display language: 中文"));
        assert_eq!(
            english
                .scene
                .root
                .find("locale")
                .and_then(|node| node.props.get("action"))
                .and_then(Value::as_str),
            Some("settings.locale")
        );
    }
}
