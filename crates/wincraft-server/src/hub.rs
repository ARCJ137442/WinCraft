use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    sync::{Arc, Mutex, MutexGuard},
    time::Instant,
};
use tokio::sync::broadcast;
use uuid::Uuid;
use wincraft_core::*;

#[derive(Clone, Debug)]
pub enum Notice {
    Changed(Uuid),
    Directed(Uuid, Value),
    Deleted { world_id: Uuid, members: Vec<Uuid> },
}
#[derive(Clone)]
pub struct Hub {
    core: Arc<Mutex<Engine>>,
    born: Instant,
    pub host_id: Uuid,
    pub native_windows: bool,
    events: broadcast::Sender<Notice>,
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
        Self {
            core: Arc::new(Mutex::new(Engine::default())),
            born: Instant::now(),
            host_id: Uuid::new_v4(),
            native_windows,
            events,
        }
    }
    pub fn lock(&self) -> MutexGuard<'_, Engine> {
        self.core.lock().expect("engine mutex poisoned")
    }
    pub fn now(&self) -> u64 {
        self.born.elapsed().as_millis().min(u64::MAX as u128) as u64
    }
    pub fn subscribe(&self) -> broadcast::Receiver<Notice> {
        self.events.subscribe()
    }
    pub fn changed(&self, id: Uuid) {
        let _ = self.events.send(Notice::Changed(id));
    }
    pub fn deleted(&self, id: Uuid, members: Vec<Uuid>) {
        let _ = self.events.send(Notice::Deleted {
            world_id: id,
            members,
        });
    }
    pub fn disconnect(&self, sid: Uuid) {
        let ids = self.lock().disconnect(sid);
        for id in ids {
            self.changed(id);
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
        json!({"protocol":PROTOCOL,"transport":["websocket"],"window_scope":"exclusive_writer",
            "read_model":"immutable_snapshots","dynamic_scene":true,"component_leases":false,
            "native_windows":self.native_windows,"remote":"authenticated_ssh_tunnel",
            "max_worlds":MAX_WORLDS,"max_message_bytes":MAX_PAYLOAD,"lease_ms":LEASE_MS,
            "components":["stack","row","text","metric","progress","badge","button","input","key_value","divider"],
            "window_properties":["title","width","height","position","always_on_top","visible","resizable","title_bar_visible","decorations","skip_taskbar","click_through","geometry_control","surface_opacity"],
            "not_implemented":["component_leases","follow_cursor","attach_to_foreign_window","native_opacity","arbitrary_code","builtin_tls"]})
    }
    pub fn reply(&self, sid: Uuid, req: Request) -> Value {
        if req.id.is_empty() || req.id.len() > 80 || req.method.len() > 80 {
            return json!({"id":req.id,"ok":false,"error":Fault::new("INVALID_REQUEST","id and method too long or empty")});
        }
        match self.dispatch(sid, &req.method, req.params) {
            Ok(result) => json!({"id":req.id,"ok":true,"result":result}),
            Err(error) => json!({"id":req.id,"ok":false,"error":error}),
        }
    }
    pub fn dispatch(&self, sid: Uuid, method: &str, params: Value) -> Result<Value> {
        let now = self.now();
        let mut e = self.lock();
        if !e.sessions.contains_key(&sid) {
            return Err(Fault::new("SESSION_GONE", "session missing"));
        }
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
        drop(e);
        if let Some(id) = changed {
            self.changed(id);
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
        let (sid, event) = self.lock().interact(
            id,
            node,
            value,
            context_action,
            expected_revision,
            self.now(),
        )?;
        let event_id = event.id;
        let _ = self.events.send(Notice::Directed(
            sid,
            json!({"event":"interaction","data":event}),
        ));
        self.changed(id);
        Ok(event_id)
    }
    pub fn start_housekeeping(&self) {
        let hub = self.clone();
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(std::time::Duration::from_millis(200));
            loop {
                interval.tick().await;
                let ids = hub.lock().expire(hub.now());
                for id in ids {
                    hub.changed(id);
                }
            }
        });
    }
}
