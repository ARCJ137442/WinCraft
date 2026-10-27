use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    sync::{Arc, Mutex, MutexGuard},
    time::Instant,
};
use tokio::{
    sync::{broadcast, watch},
    task::JoinHandle,
};
use uuid::Uuid;
use wincraft_core::*;

#[derive(Clone, Debug)]
pub enum Notice {
    Directed(Uuid, Value),
    Deleted { world_id: Uuid, members: Vec<Uuid> },
}

#[derive(Clone, Debug)]
pub struct StateChange {
    pub world_id: Uuid,
    pub sequence: u64,
    pub source: EventSource,
    pub cause_id: Option<String>,
}

#[cfg(test)]
mod capability_tests {
    use super::{Hub, StateChange};
    use serde_json::json;
    use wincraft_core::{
        EventSource, Fault, InteractionSource, JoinPolicy, Kind, NativeWindowOperation, Node,
        Scene, ShortcutSpec, WindowSpec,
    };

    fn native_action_world(hub: &Hub) -> (uuid::Uuid, uuid::Uuid, wincraft_core::LeaseKey, u64) {
        let mut core = hub.lock();
        let session = core.register("native-action.test".into(), false).unwrap();
        let created = core
            .create(
                session,
                WindowSpec::default(),
                JoinPolicy::Invite,
                true,
                false,
                hub.now(),
            )
            .unwrap();
        let lease = created.lease.unwrap();
        let scene = Scene {
            root: Node::new(
                "root",
                Kind::Stack,
                json!({}),
                vec![Node::new(
                    "activate-app",
                    Kind::Button,
                    json!({
                        "label":"Activate app",
                        "action":"app.activate",
                        "context_action":"app.context",
                        "native_window_action":{"application":"obsidian","operation":"activate"}
                    }),
                    vec![],
                )],
            ),
            ..Scene::default()
        };
        let updated = core
            .replace_scene(
                session,
                created.world.id,
                &lease,
                created.world.revision,
                scene,
                hub.now(),
            )
            .unwrap();
        (session, updated.id, lease, updated.revision)
    }

    #[test]
    fn host_advertises_multiline_text_and_escape_shortcut_capabilities() {
        let capabilities = Hub::new(false).capabilities();
        assert!(capabilities["components"]
            .as_array()
            .unwrap()
            .iter()
            .any(|component| component == "textarea"));
        assert!(capabilities["keyboard_shortcuts"]
            .as_array()
            .unwrap()
            .iter()
            .any(|shortcut| shortcut == "escape"));
        assert!(capabilities["keyboard_shortcuts"]
            .as_array()
            .unwrap()
            .iter()
            .any(|shortcut| shortcut == "ctrl_enter"));
        assert!(capabilities["button_features"]
            .as_array()
            .unwrap()
            .iter()
            .any(|feature| feature == "selection_groups"));
        assert!(capabilities["scene_features"]
            .as_array()
            .unwrap()
            .iter()
            .any(|feature| feature == "theme_tokens"));
        assert!(!capabilities["button_features"]
            .as_array()
            .unwrap()
            .iter()
            .any(|feature| feature == "external_window_actions"));
        let native_capabilities = Hub::new(true).capabilities();
        assert!(native_capabilities["button_features"]
            .as_array()
            .unwrap()
            .iter()
            .any(|feature| feature == "external_window_actions"));
        assert!(native_capabilities["event_subscriptions"]["events"]
            .as_array()
            .unwrap()
            .iter()
            .any(
                |event| event["type"] == "window.geometry_changed" && event["delivery"] == "state"
            ));
    }

    #[test]
    fn native_window_action_runs_before_provider_ack_only_on_native_hosts() {
        let headless = Hub::new(false);
        let (session, world_id, _lease, revision) = native_action_world(&headless);
        let mut notices = headless.subscribe();
        let mut called = false;
        let error = headless
            .interact_with_source_with_native_window_action(
                world_id,
                "activate-app",
                serde_json::Value::Null,
                InteractionSource::Click,
                revision,
                |_| {
                    called = true;
                    Ok(())
                },
            )
            .unwrap_err();
        assert_eq!(error.code, "UNSUPPORTED_CAPABILITY");
        assert!(!called);
        assert!(matches!(
            notices.try_recv(),
            Err(tokio::sync::broadcast::error::TryRecvError::Empty)
        ));
        headless.disconnect(session);

        let native = Hub::new(true);
        let (session, world_id, _lease, revision) = native_action_world(&native);
        let mut called = false;
        let event_id = native
            .interact_with_source_with_native_window_action(
                world_id,
                "activate-app",
                serde_json::Value::Null,
                InteractionSource::Click,
                revision,
                |action| {
                    assert_eq!(action.operation, NativeWindowOperation::Activate);
                    called = true;
                    Ok(())
                },
            )
            .unwrap();
        assert!(called);
        assert!(!event_id.is_nil());
        native.disconnect(session);
    }

    #[test]
    fn native_window_action_failure_does_not_dispatch_or_ack_the_provider_event() {
        let native = Hub::new(true);
        let (session, world_id, _lease, revision) = native_action_world(&native);
        let mut notices = native.subscribe();
        let mut attempts = 0;
        let error = native
            .interact_with_source_with_native_window_action(
                world_id,
                "activate-app",
                serde_json::Value::Null,
                InteractionSource::Click,
                revision,
                |_| {
                    attempts += 1;
                    Err(Fault::new(
                        "NATIVE_WINDOW_ACTION_FAILED",
                        "Windows rejected foreground activation",
                    ))
                },
            )
            .unwrap_err();

        assert_eq!(attempts, 1);
        assert_eq!(error.code, "NATIVE_WINDOW_ACTION_FAILED");
        assert_eq!(error.message, "Windows rejected foreground activation");
        assert!(matches!(
            notices.try_recv(),
            Err(tokio::sync::broadcast::error::TryRecvError::Empty)
        ));
        assert!(native
            .renderer_snapshot(world_id)
            .unwrap()
            .actions
            .is_empty());
        native.disconnect(session);
    }

    #[test]
    fn native_window_action_without_host_work_still_dispatches_static_provider_action() {
        let native = Hub::new(true);
        let (session, world_id, _lease, revision) = native_action_world(&native);
        let mut notices = native.subscribe();
        let event_id = native
            .interact_with_source_with_native_window_action(
                world_id,
                "activate-app",
                serde_json::Value::Null,
                InteractionSource::ContextMenu,
                revision,
                |_| panic!("context gestures must not execute a click-only host action"),
            )
            .unwrap();
        assert!(!event_id.is_nil());
        assert!(matches!(
            notices.try_recv(),
            Ok(super::Notice::Directed(
                target_session,
                ref message
            )) if target_session == session && message["event"] == "interaction"
        ));
        let snapshot = native.renderer_snapshot(world_id).unwrap();
        assert_eq!(snapshot.actions.len(), 1);
        assert_eq!(snapshot.actions[0].status, "pending");
        native.disconnect(session);
    }

    #[test]
    fn disconnect_revokes_session_shortcuts_without_touching_another_session() {
        let hub = Hub::new(false);
        let (first, second) = {
            let mut core = hub.lock();
            (
                core.register("shortcut-a".into(), false).unwrap(),
                core.register("shortcut-b".into(), false).unwrap(),
            )
        };
        hub.register_shortcut(
            first,
            ShortcutSpec {
                chord: "Ctrl+Shift+W".into(),
                action: "recall".into(),
            },
        )
        .unwrap();
        hub.register_shortcut(
            second,
            ShortcutSpec {
                chord: "Ctrl+Shift+T".into(),
                action: "toggle".into(),
            },
        )
        .unwrap();
        assert!(hub.shortcut_registered("Ctrl+Shift+W"));
        hub.disconnect(first);
        assert!(!hub.shortcut_registered("Ctrl+Shift+W"));
        assert!(hub.shortcut_registered("Ctrl+Shift+T"));
        hub.disconnect(second);
        assert!(!hub.shortcut_registered("Ctrl+Shift+T"));
    }

    #[test]
    fn coalescible_state_updates_do_not_consume_the_occurrence_queue() {
        let hub = Hub::new(false);
        let (_session, world_id, _lease, _revision) = native_action_world(&hub);
        let mut occurrences = hub.subscribe();
        let mut state_updates = hub.subscribe_state();

        for sequence in 1..=512 {
            hub.publish_state_change(StateChange {
                world_id,
                sequence,
                source: EventSource::Human,
                cause_id: None,
            });
        }
        hub.publish_state_change(StateChange {
            world_id,
            sequence: 511,
            source: EventSource::Provider,
            cause_id: Some("stale".into()),
        });

        let latest = hub.latest_state_changes();
        assert_eq!(latest.len(), 1);
        assert_eq!(latest[0].world_id, world_id);
        assert_eq!(latest[0].sequence, 512);
        assert_eq!(latest[0].source, EventSource::Human);
        assert_eq!(*state_updates.borrow_and_update(), 512);
        assert!(matches!(
            occurrences.try_recv(),
            Err(tokio::sync::broadcast::error::TryRecvError::Empty)
        ));
    }

    #[test]
    fn host_locale_is_shared_and_rejects_unknown_values() {
        let first = Hub::new(false);
        let second = first.clone();
        assert_eq!(first.locale(), "zh-CN");
        first.set_locale("en-US").unwrap();
        assert_eq!(second.locale(), "en-US");
        assert_eq!(
            first.set_locale("fr-FR").unwrap_err().code,
            "INVALID_LOCALE"
        );
    }
}
#[derive(Clone)]
pub struct Hub {
    core: Arc<Mutex<Engine>>,
    locale: Arc<Mutex<String>>,
    born: Instant,
    pub host_id: Uuid,
    pub native_windows: bool,
    events: broadcast::Sender<Notice>,
    state_changes: Arc<Mutex<BTreeMap<Uuid, StateChange>>>,
    state_updates: watch::Sender<u64>,
    shortcuts: Arc<Mutex<ShortcutRegistry>>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub id: String,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}
fn decode<T: DeserializeOwned>(v: Value) -> Result<T> {
    serde_json::from_value(v).map_err(|e| Fault::new("INVALID_PARAMS", e.to_string()))
}
fn encode<T: Serialize>(v: T) -> Result<Value> {
    serde_json::to_value(v).map_err(|e| Fault::new("INTERNAL", e.to_string()))
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CreateParams {
    #[serde(default)]
    window: WindowSpec,
    #[serde(default)]
    join_policy: JoinPolicy,
    #[serde(default = "yes")]
    claim: bool,
}
fn yes() -> bool {
    true
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct JoinParams {
    world_id: Uuid,
    #[serde(default)]
    join_key: Option<String>,
    mode: JoinMode,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WorldParams {
    world_id: Uuid,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LeaseParams {
    world_id: Uuid,
    lease: LeaseKey,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SceneParams {
    world_id: Uuid,
    lease: LeaseKey,
    expected_revision: u64,
    scene: Scene,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PatchParams {
    world_id: Uuid,
    lease: LeaseKey,
    expected_revision: u64,
    ops: Vec<SceneOp>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DataParams {
    world_id: Uuid,
    lease: LeaseKey,
    expected_revision: u64,
    data: Value,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WindowParams {
    world_id: Uuid,
    lease: LeaseKey,
    expected_revision: u64,
    patch: WindowPatch,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AckParams {
    world_id: Uuid,
    lease: LeaseKey,
    event_id: Uuid,
    ok: bool,
    #[serde(default)]
    message: Option<String>,
}

impl Hub {
    pub fn new(native_windows: bool) -> Self {
        let (events, _) = broadcast::channel(256);
        let (state_updates, _) = watch::channel(0);
        Self {
            core: Arc::new(Mutex::new(Engine::default())),
            locale: Arc::new(Mutex::new("zh-CN".into())),
            born: Instant::now(),
            host_id: Uuid::new_v4(),
            native_windows,
            events,
            state_changes: Arc::new(Mutex::new(BTreeMap::new())),
            state_updates,
            shortcuts: Arc::new(Mutex::new(ShortcutRegistry::default())),
        }
    }
    pub fn lock(&self) -> MutexGuard<'_, Engine> {
        self.core.lock().expect("engine mutex poisoned")
    }
    pub fn locale(&self) -> String {
        self.locale.lock().expect("locale mutex poisoned").clone()
    }
    pub fn set_locale(&self, locale: &str) -> Result<()> {
        if !matches!(locale, "zh-CN" | "en-US") {
            return Err(Fault::new(
                "INVALID_LOCALE",
                "locale must be zh-CN or en-US",
            ));
        }
        *self.locale.lock().expect("locale mutex poisoned") = locale.into();
        Ok(())
    }
    pub fn now(&self) -> u64 {
        self.born.elapsed().as_millis().min(u64::MAX as u128) as u64
    }
    pub fn subscribe(&self) -> broadcast::Receiver<Notice> {
        self.events.subscribe()
    }
    pub fn subscribe_state(&self) -> watch::Receiver<u64> {
        self.state_updates.subscribe()
    }
    pub fn latest_state_changes(&self) -> Vec<StateChange> {
        self.state_changes
            .lock()
            .expect("state changes mutex poisoned")
            .values()
            .cloned()
            .collect()
    }
    pub fn changed(&self, id: Uuid) {
        self.changed_with_source(id, EventSource::Host, None);
    }
    pub fn changed_with_source(&self, id: Uuid, source: EventSource, cause_id: Option<String>) {
        let sequence = self.lock().worlds.get(&id).map(|world| world.sequence);
        if let Some(sequence) = sequence {
            self.changed_at(id, sequence, source, cause_id);
        }
    }
    pub fn apply_state_change<F>(
        &self,
        id: Uuid,
        source: EventSource,
        cause_id: Option<String>,
        update: F,
    ) -> Result<bool>
    where
        F: FnOnce(&mut Engine) -> Result<bool>,
    {
        let (changed, sequence) = {
            let mut core = self.lock();
            let before = core.worlds.get(&id).map(|world| world.sequence);
            let changed = update(&mut core)?;
            let sequence = core.worlds.get(&id).map(|world| world.sequence);
            (changed && before != sequence, sequence)
        };
        if let Some(sequence) = sequence.filter(|_| changed) {
            self.changed_at(id, sequence, source, cause_id);
        }
        Ok(changed)
    }
    pub fn changed_at(
        &self,
        id: Uuid,
        sequence: u64,
        source: EventSource,
        cause_id: Option<String>,
    ) {
        let core = self.lock();
        if core.worlds.get(&id).map(|world| world.sequence) != Some(sequence) {
            return;
        }
        self.publish_state_change(StateChange {
            world_id: id,
            sequence,
            source,
            cause_id,
        });
    }
    fn publish_state_change(&self, change: StateChange) {
        let publish = {
            let mut changes = self
                .state_changes
                .lock()
                .expect("state changes mutex poisoned");
            if changes
                .get(&change.world_id)
                .is_some_and(|current| current.sequence >= change.sequence)
            {
                false
            } else {
                changes.insert(change.world_id, change);
                true
            }
        };
        if publish {
            self.state_updates
                .send_modify(|generation| *generation = generation.wrapping_add(1));
        }
    }
    pub fn deleted(&self, id: Uuid, members: Vec<Uuid>) {
        self.state_changes
            .lock()
            .expect("state changes mutex poisoned")
            .remove(&id);
        self.state_updates
            .send_modify(|generation| *generation = generation.wrapping_add(1));
        let _ = self.events.send(Notice::Deleted {
            world_id: id,
            members,
        });
    }
    pub fn disconnect(&self, sid: Uuid) {
        self.shortcuts
            .lock()
            .expect("shortcut registry mutex poisoned")
            .revoke_session(sid);
        let changes = {
            let mut core = self.lock();
            core.disconnect(sid)
                .into_iter()
                .filter_map(|id| core.worlds.get(&id).map(|world| (id, world.sequence)))
                .collect::<Vec<_>>()
        };
        for (id, sequence) in changes {
            self.changed_at(id, sequence, EventSource::System, None);
        }
    }

    #[allow(dead_code)]
    pub(crate) fn register_shortcut(&self, session: Uuid, spec: ShortcutSpec) -> Result<()> {
        self.shortcuts
            .lock()
            .expect("shortcut registry mutex poisoned")
            .register(session, spec)
    }

    #[allow(dead_code)]
    pub(crate) fn shortcut_registered(&self, chord: &str) -> bool {
        self.shortcuts
            .lock()
            .expect("shortcut registry mutex poisoned")
            .contains(chord)
    }
    pub(crate) fn disconnect_providers(&self) {
        let providers: Vec<_> = self
            .lock()
            .sessions
            .values()
            .filter(|session| !session.operator)
            .map(|session| session.id)
            .collect();
        for session in providers {
            self.disconnect(session);
        }
    }
    pub fn snapshots(&self) -> Vec<Snapshot> {
        self.lock().worlds.values().map(World::snapshot).collect()
    }
    pub fn renderer_snapshot(&self, id: Uuid) -> Result<Snapshot> {
        self.lock()
            .worlds
            .get(&id)
            .map(World::snapshot)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))
    }
    pub fn capabilities(&self) -> Value {
        let mut button_features = vec![
            "selection_groups",
            "appearance_variants",
            "key_value_actions",
        ];
        if self.native_windows {
            button_features.push("external_window_actions");
        }
        json!({"protocol":PROTOCOL,"transport":["websocket"],"window_scope":"exclusive_writer",
            "read_model":"immutable_snapshots","dynamic_scene":true,"component_leases":false,
            "event_subscriptions":{"scope":"session","max_subscriptions":32,"events":[
                {"type":"window.geometry_changed","delivery":"state"},
                {"type":"window.visibility_changed","delivery":"state"}
            ]},
            "native_windows":self.native_windows,"remote":"authenticated_ssh_tunnel",
            "max_worlds":MAX_WORLDS,"max_message_bytes":MAX_PAYLOAD,"lease_ms":LEASE_MS,
            "components":["stack","row","text","metric","progress","badge","button","input","textarea","key_value","icon","bar_chart","divider"],
            "keyboard_shortcuts":["escape","ctrl_enter"],
            "button_features":button_features,
            "scene_features":["theme_tokens","rich_key_value"],
            "window_properties":["title","width","height","position","anchor","always_on_top","visible","resizable","title_bar_visible","background_drag_enabled","text_selectable","decorations","skip_taskbar","click_through","geometry_control","surface_opacity"],
            "not_implemented":["component_leases","follow_cursor","attach_to_foreign_window","native_opacity","arbitrary_code","builtin_tls"]})
    }
    pub fn reply(&self, sid: Uuid, req: Request) -> Value {
        if req.id.is_empty() || req.id.len() > 80 || req.method.len() > 80 {
            return json!({"id":req.id,"ok":false,"error":Fault::new("INVALID_REQUEST","id and method too long or empty")});
        }
        match self.dispatch_with_cause(sid, &req.method, req.params, Some(req.id.clone())) {
            Ok(result) => json!({"id":req.id,"ok":true,"result":result}),
            Err(error) => json!({"id":req.id,"ok":false,"error":error}),
        }
    }
    pub fn dispatch(&self, sid: Uuid, method: &str, params: Value) -> Result<Value> {
        self.dispatch_with_cause(sid, method, params, None)
    }
    fn dispatch_with_cause(
        &self,
        sid: Uuid,
        method: &str,
        params: Value,
        cause_id: Option<String>,
    ) -> Result<Value> {
        let now = self.now();
        let mut e = self.lock();
        if !e.sessions.contains_key(&sid) {
            return Err(Fault::new("SESSION_GONE", "session missing"));
        }
        let source = if e.operator(sid) {
            EventSource::Operator
        } else {
            EventSource::Provider
        };
        let mut changed = None;
        let mut deleted = None;
        let value = match method {
            "session.ping" => {
                let mut renewed = vec![];
                for w in e.worlds.values_mut() {
                    if let Some(l) = &mut w.writer {
                        if l.session == sid && l.expires_at > now {
                            l.expires_at = now + LEASE_MS;
                            renewed.push(w.id);
                        }
                    }
                }
                json!({"renewed":renewed,"lease_ms":LEASE_MS})
            }
            "host.capabilities" => self.capabilities(),
            "world.list" => encode(e.list(sid)?)?,
            "world.create" => {
                let p: CreateParams = decode(params)?;
                let mut c = e.create(sid, p.window, p.join_policy, p.claim, false, now)?;
                if !self.native_windows {
                    e.native_report(
                        c.world.id,
                        c.world.window_revision,
                        NativeReport {
                            state: "unavailable".into(),
                            applied_window_revision: None,
                            error: Some("headless host: no native renderer".into()),
                        },
                    );
                    c.world = e.read(sid, c.world.id)?;
                }
                changed = Some(c.world.id);
                encode(c)?
            }
            "world.join" => {
                let p: JoinParams = decode(params)?;
                let r = e.join(sid, p.world_id, p.join_key.as_deref(), p.mode, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "world.snapshot" => {
                let p: WorldParams = decode(params)?;
                encode(e.read(sid, p.world_id)?)?
            }
            "world.leave" => {
                let p: WorldParams = decode(params)?;
                e.leave(sid, p.world_id)?;
                changed = Some(p.world_id);
                json!({})
            }
            "lease.renew" => {
                let p: LeaseParams = decode(params)?;
                e.renew(sid, p.world_id, &p.lease, now)?;
                json!({"lease_ms":LEASE_MS})
            }
            "lease.release" => {
                let p: LeaseParams = decode(params)?;
                let r = e.release(sid, p.world_id, &p.lease, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "scene.replace" => {
                let p: SceneParams = decode(params)?;
                let r =
                    e.replace_scene(sid, p.world_id, &p.lease, p.expected_revision, p.scene, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "scene.patch" => {
                let p: PatchParams = decode(params)?;
                let r =
                    e.patch_scene(sid, p.world_id, &p.lease, p.expected_revision, &p.ops, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "data.replace" => {
                let p: DataParams = decode(params)?;
                let r = e.set_data(sid, p.world_id, &p.lease, p.expected_revision, p.data, now)?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "window.configure" => {
                let p: WindowParams = decode(params)?;
                let r = e.configure(
                    sid,
                    p.world_id,
                    &p.lease,
                    p.expected_revision,
                    &p.patch,
                    now,
                )?;
                changed = Some(p.world_id);
                encode(r)?
            }
            "action.result" => {
                let p: AckParams = decode(params)?;
                e.acknowledge(
                    sid,
                    p.world_id,
                    &p.lease,
                    ActionAcknowledgement {
                        event_id: p.event_id,
                        ok: p.ok,
                        message: p.message,
                    },
                    now,
                )?;
                changed = Some(p.world_id);
                json!({})
            }
            "world.destroy" => {
                let p: LeaseParams = decode(params)?;
                let members = e.destroy(sid, p.world_id, &p.lease, now)?;
                deleted = Some((p.world_id, members));
                json!({})
            }
            _ => return Err(Fault::new("METHOD_NOT_FOUND", method)),
        };
        let changed = changed.and_then(|id| e.worlds.get(&id).map(|world| (id, world.sequence)));
        drop(e);
        if let Some((id, sequence)) = changed {
            self.changed_at(id, sequence, source, cause_id);
        }
        if let Some((id, members)) = deleted {
            self.deleted(id, members);
        }
        Ok(value)
    }
    pub fn interact(
        &self,
        id: Uuid,
        node: &str,
        value: Value,
        context_action: bool,
        expected_revision: u64,
    ) -> Result<Uuid> {
        self.interact_with_source(
            id,
            node,
            value,
            if context_action {
                InteractionSource::ContextMenu
            } else {
                InteractionSource::Click
            },
            expected_revision,
        )
    }
    pub fn interact_with_source(
        &self,
        id: Uuid,
        node: &str,
        value: Value,
        source: InteractionSource,
        expected_revision: u64,
    ) -> Result<Uuid> {
        self.interact_with_source_with_native_window_action(
            id,
            node,
            value,
            source,
            expected_revision,
            |_| Ok(()),
        )
    }
    pub fn interact_with_source_with_native_window_action<F>(
        &self,
        id: Uuid,
        node: &str,
        value: Value,
        source: InteractionSource,
        expected_revision: u64,
        focus: F,
    ) -> Result<Uuid>
    where
        F: FnOnce(&NativeWindowAction) -> Result<()>,
    {
        let now = self.now();
        let mut core = self.lock();
        if let Some(action) = core.native_window_action(id, node, source, expected_revision, now)? {
            if !self.native_windows {
                return Err(Fault::new(
                    "UNSUPPORTED_CAPABILITY",
                    "native external window actions are not available on this host",
                ));
            }
            focus(&action)?;
        }
        let (sid, event) =
            core.interact_with_source(id, node, value, source, expected_revision, now)?;
        let sequence = core.worlds.get(&id).map(|world| world.sequence);
        drop(core);
        let event_id = event.id;
        let _ = self.events.send(Notice::Directed(
            sid,
            json!({"event":"interaction","data":event}),
        ));
        if let Some(sequence) = sequence {
            self.changed_at(id, sequence, EventSource::Human, None);
        }
        Ok(event_id)
    }
    pub fn start_housekeeping(&self, mut shutdown: watch::Receiver<bool>) -> JoinHandle<()> {
        let hub = self.clone();
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(std::time::Duration::from_millis(200));
            loop {
                tokio::select! {
                    _ = shutdown.changed() => break,
                    _ = interval.tick() => {
                        let expired = {
                            let mut core = hub.lock();
                            core.expire(hub.now())
                                .into_iter()
                                .filter_map(|id| core.worlds.get(&id).map(|world| (id, world.sequence)))
                                .collect::<Vec<_>>()
                        };
                        for (id, sequence) in expired {
                            hub.changed_at(id, sequence, EventSource::System, None);
                        }
                    }
                }
            }
        })
    }
}
