use crate::*;
use serde_json::Value;
use std::collections::BTreeMap;
use uuid::Uuid;

/// All mutations are serialized by the host. Time is a monotonic host clock;
/// callers cannot supply timestamps over the wire.
#[derive(Default)]
pub struct Engine {
    pub sessions: BTreeMap<Uuid, Session>,
    pub worlds: BTreeMap<Uuid, World>,
}
impl Engine {
    pub fn register(&mut self, name: String, operator: bool) -> Result<Uuid> {
        if self.sessions.len() >= 64 {
            return Err(Fault::new("LIMIT", "maximum 64 sessions"));
        }
        if name.trim().is_empty() || name.chars().count() > 80 {
            return Err(Fault::new(
                "INVALID_SESSION",
                "provider_name must contain 1..80 characters",
            ));
        }
        let id = Uuid::new_v4();
        self.sessions.insert(id, Session { id, name, operator });
        Ok(id)
    }
    pub fn operator(&self, session: Uuid) -> bool {
        self.sessions
            .get(&session)
            .map(|s| s.operator)
            .unwrap_or(false)
    }
    fn session(&self, session: Uuid) -> Result<()> {
        if !self.sessions.contains_key(&session) {
            return Err(Fault::new("SESSION_GONE", "session ended"));
        }
        Ok(())
    }
    fn admin(&self, session: Uuid) -> Result<()> {
        self.session(session)?;
        if !self.operator(session) {
            return Err(Fault::new(
                "FORBIDDEN",
                "local operator capability required",
            ));
        }
        Ok(())
    }
    pub fn list(&self, session: Uuid) -> Result<Vec<WorldSummary>> {
        self.session(session)?;
        Ok(self
            .worlds
            .values()
            .map(|w| {
                let sid = w.writer.as_ref().map(|x| x.session);
                WorldSummary {
                    id: w.id,
                    title: w.window.title.clone(),
                    system: w.system,
                    join_policy: w.join_policy,
                    write_blocked: w.write_blocked,
                    writer: sid,
                    writer_name: sid.and_then(|id| self.sessions.get(&id).map(|s| s.name.clone())),
                    status: w.status().into(),
                    revision: w.revision,
                    visible: w.window.visible,
                }
            })
            .collect())
    }
    pub fn create(
        &mut self,
        session: Uuid,
        window: WindowSpec,
        policy: JoinPolicy,
        claim: bool,
        system: bool,
        now: u64,
    ) -> Result<Created> {
        self.session(session)?;
        if system {
            self.admin(session)?;
        }
        if self.worlds.len() >= MAX_WORLDS {
            return Err(Fault::new("LIMIT", "maximum 16 worlds"));
        }
        window.validate()?;
        let id = Uuid::new_v4();
        let join_key = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
        let mut world = World {
            id,
            revision: 1,
            sequence: 1,
            window_revision: 1,
            epoch: 0,
            system,
            write_blocked: false,
            join_policy: policy,
            join_key: join_key.clone(),
            writer: None,
            readers: BTreeMap::new(),
            ever_claimed: false,
            window,
            scene: Scene::default(),
            native: NativeReport::default(),
            actions: vec![],
        };
        world.readers.insert(session, JoinMode::Read);
        let lease = if claim {
            Some(Self::grant(&mut world, session, now)?)
        } else {
            None
        };
        let snapshot = world.snapshot();
        self.worlds.insert(id, world);
        Ok(Created {
            world: snapshot,
            lease,
            join_key,
        })
    }
    fn grant(world: &mut World, session: Uuid, now: u64) -> Result<LeaseKey> {
        if let Some(current) = &mut world.writer {
            if current.expires_at <= now {
                Self::revoke(world, "lease expired");
            } else if current.session == session {
                current.expires_at = now + LEASE_MS;
                return Ok(current.key.clone());
            } else {
                return Err(Fault::new(
                    "WRITE_CONFLICT",
                    "world already has an exclusive writer",
                ));
            }
        }
        world.epoch += 1;
        let key = LeaseKey {
            id: Uuid::new_v4(),
            epoch: world.epoch,
        };
        world.writer = Some(WriteLease {
            key: key.clone(),
            session,
            expires_at: now + LEASE_MS,
        });
        world.readers.insert(session, JoinMode::Write);
        world.ever_claimed = true;
        world.touch();
        Ok(key)
    }
    fn revoke(world: &mut World, reason: &str) {
        if let Some(lease) = world.writer.take() {
            world.readers.insert(lease.session, JoinMode::Read);
            world.epoch += 1;
            for action in &mut world.actions {
                if action.status == "pending" {
                    action.status = "error".into();
                    action.message = Some(reason.into());
                }
            }
            world.touch();
        }
    }
    pub fn join(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: Option<&str>,
        mode: JoinMode,
        now: u64,
    ) -> Result<JoinResult> {
        self.session(session)?;
        let operator = self.operator(session);
        let world = self
            .worlds
            .get_mut(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if world.system && !operator {
            return Err(Fault::new("FORBIDDEN", "system world is private"));
        }
        if !operator
            && !world.readers.contains_key(&session)
            && world.join_policy == JoinPolicy::Invite
            && key != Some(world.join_key.as_str())
        {
            return Err(Fault::new(
                "FORBIDDEN",
                "join_key required; discovery does not grant membership",
            ));
        }
        if mode == JoinMode::Write && world.write_blocked {
            return Err(Fault::new(
                "OPERATOR_HOLD",
                "local operator has held this world; release it in the manager",
            ));
        }
        let lease = if mode == JoinMode::Write {
            Some(Self::grant(world, session, now)?)
        } else {
            world.readers.entry(session).or_insert(JoinMode::Read);
            None
        };
        Ok(JoinResult {
            world: world.snapshot(),
            lease,
        })
    }
    pub fn read(&self, session: Uuid, id: Uuid) -> Result<Snapshot> {
        self.session(session)?;
        let world = self
            .worlds
            .get(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if !self.operator(session) && !world.readers.contains_key(&session) {
            return Err(Fault::new(
                "FORBIDDEN",
                "join the world before reading its scene",
            ));
        }
        Ok(world.snapshot())
    }
    fn writable(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        now: u64,
    ) -> Result<&mut World> {
        self.session(session)?;
        let world = self
            .worlds
            .get_mut(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        let lease = world
            .writer
            .as_ref()
            .ok_or_else(|| Fault::new("STALE_LEASE", "world has no writer"))?;
        if lease.session != session || lease.key != *key || lease.key.epoch != world.epoch {
            return Err(Fault::new(
                "STALE_LEASE",
                "writer, lease id or fencing epoch no longer matches",
            ));
        }
        if lease.expires_at <= now {
            return Err(Fault::new("LEASE_EXPIRED", "lease has expired"));
        }
        Ok(world)
    }
    fn revision(world: &World, expected: u64) -> Result<()> {
        if world.revision != expected {
            return Err(Fault::new(
                "REVISION_CONFLICT",
                format!("expected {expected}, actual {}", world.revision),
            ));
        }
        Ok(())
    }
    pub fn renew(&mut self, session: Uuid, id: Uuid, key: &LeaseKey, now: u64) -> Result<()> {
        let world = self.writable(session, id, key, now)?;
        world.writer.as_mut().unwrap().expires_at = now + LEASE_MS;
        Ok(())
    }
    pub fn release(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        now: u64,
    ) -> Result<Snapshot> {
        let world = self.writable(session, id, key, now)?;
        Self::revoke(world, "write lease released");
        Ok(world.snapshot())
    }
    pub fn leave(&mut self, session: Uuid, id: Uuid) -> Result<()> {
        self.session(session)?;
        let world = self
            .worlds
            .get_mut(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if world.writer.as_ref().map(|w| w.session) == Some(session) {
            Self::revoke(world, "provider left");
        }
        world.readers.remove(&session);
        Ok(())
    }
    pub fn replace_scene(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        expected: u64,
        scene: Scene,
        now: u64,
    ) -> Result<Snapshot> {
        let world = self.writable(session, id, key, now)?;
        Self::revision(world, expected)?;
        scene.validate()?;
        world.scene = scene;
        world.touch();
        Ok(world.snapshot())
    }
    pub fn patch_scene(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        expected: u64,
        ops: &[SceneOp],
        now: u64,
    ) -> Result<Snapshot> {
        let world = self.writable(session, id, key, now)?;
        Self::revision(world, expected)?;
        let next = world.scene.patch(ops)?;
        world.scene = next;
        world.touch();
        Ok(world.snapshot())
    }
    pub fn set_data(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        expected: u64,
        data: Value,
        now: u64,
    ) -> Result<Snapshot> {
        let world = self.writable(session, id, key, now)?;
        Self::revision(world, expected)?;
        let mut next = world.scene.clone();
        next.data = data;
        next.validate()?;
        world.scene = next;
        world.touch();
        Ok(world.snapshot())
    }
    pub fn configure(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        expected: u64,
        patch: &WindowPatch,
        now: u64,
    ) -> Result<Snapshot> {
        let world = self.writable(session, id, key, now)?;
        Self::revision(world, expected)?;
        let next = patch.apply(&world.window)?;
        if next != world.window {
            world.window = next;
            world.window_revision += 1;
            world.touch();
            world.native = NativeReport::default();
        }
        Ok(world.snapshot())
    }
    pub fn destroy(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        now: u64,
    ) -> Result<Vec<Uuid>> {
        self.writable(session, id, key, now)?;
        let world = self.worlds.remove(&id).unwrap();
        Ok(world.readers.keys().copied().collect())
    }
    /// Trusted local operator action. Not a remote-provider privilege or normal write bypass.
    pub fn rescue(&mut self, session: Uuid, id: Uuid) -> Result<Snapshot> {
        self.admin(session)?;
        let w = self
            .worlds
            .get_mut(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if !w.system {
            Self::revoke(w, "local operator revoked write lease");
            w.write_blocked = true;
        }
        w.window.visible = true;
        w.window.click_through = false;
        w.window.geometry_control = GeometryControl::Human;
        w.window.title_bar_visible = true;
        w.window.text_selectable = true;
        w.window.position = None;
        w.window.resizable = true;
        w.window.surface_opacity = 1.0;
        w.window_revision += 1;
        w.native = NativeReport::default();
        w.touch();
        Ok(w.snapshot())
    }
    pub fn operator_release_hold(&mut self, session: Uuid, id: Uuid) -> Result<()> {
        self.admin(session)?;
        let w = self
            .worlds
            .get_mut(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        w.write_blocked = false;
        w.touch();
        Ok(())
    }
    pub fn operator_visibility(&mut self, session: Uuid, id: Uuid, visible: bool) -> Result<()> {
        self.admin(session)?;
        let w = self
            .worlds
            .get_mut(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if w.window.visible != visible {
            w.window.visible = visible;
            w.window_revision += 1;
            w.touch();
        }
        Ok(())
    }
    pub fn operator_destroy(&mut self, session: Uuid, id: Uuid) -> Result<Vec<Uuid>> {
        self.admin(session)?;
        let world = self
            .worlds
            .remove(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        Ok(world.readers.keys().copied().collect())
    }
    pub fn disconnect(&mut self, session: Uuid) -> Vec<Uuid> {
        let mut changed = vec![];
        for w in self.worlds.values_mut() {
            if w.writer.as_ref().map(|x| x.session) == Some(session) {
                Self::revoke(w, "provider disconnected");
                changed.push(w.id);
            }
            w.readers.remove(&session);
        }
        self.sessions.remove(&session);
        changed
    }
    pub fn expire(&mut self, now: u64) -> Vec<Uuid> {
        let mut changed = vec![];
        for w in self.worlds.values_mut() {
            let before = w.sequence;
            if w.writer
                .as_ref()
                .map(|x| x.expires_at <= now)
                .unwrap_or(false)
            {
                Self::revoke(w, "write lease expired");
            }
            let mut expired = false;
            for a in &mut w.actions {
                if a.status == "pending" && a.deadline <= now {
                    a.status = "error".into();
                    a.message = Some("provider acknowledgement timed out".into());
                    expired = true;
                }
            }
            if expired {
                w.sequence += 1;
            }
            if w.sequence != before {
                changed.push(w.id);
            }
        }
        changed
    }
    /// Called only by trusted renderer IPC; action comes from the accepted scene, not from caller input.
    pub fn interact(
        &mut self,
        id: Uuid,
        node_id: &str,
        value: Value,
        context_action: bool,
        expected_revision: u64,
        now: u64,
    ) -> Result<(Uuid, UiEvent)> {
        let w = self
            .worlds
            .get_mut(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        Self::revision(w, expected_revision)?;
        let lease = w
            .writer
            .as_ref()
            .filter(|l| l.expires_at > now)
            .ok_or_else(|| Fault::new("OFFLINE", "no active writer"))?
            .clone();
        let node = w
            .scene
            .root
            .find(node_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
        if !node.kind.interactive() {
            return Err(Fault::new("FORBIDDEN", "component is not interactive"));
        }
        let disabled = node
            .props
            .get("disabled")
            .map(|v| {
                if let Some(path) = v.get("$path").and_then(Value::as_str) {
                    w.scene
                        .data
                        .pointer(path)
                        .and_then(Value::as_bool)
                        .unwrap_or(false)
                } else {
                    v.as_bool().unwrap_or(false)
                }
            })
            .unwrap_or(false);
        if disabled {
            return Err(Fault::new("FORBIDDEN", "component disabled"));
        }
        match node.kind {
            Kind::Input => {
                if !value.is_string() || value.as_str().unwrap().len() > 4096 {
                    return Err(Fault::new(
                        "INVALID_EVENT",
                        "input must be at most 4096 UTF-8 bytes",
                    ));
                }
            }
            Kind::Button => {
                if !value.is_null() {
                    return Err(Fault::new("INVALID_EVENT", "button carries null value"));
                }
            }
            _ => unreachable!(),
        }
        let action_property = if context_action {
            "context_action"
        } else {
            "action"
        };
        let action = node
            .props
            .get(action_property)
            .and_then(Value::as_str)
            .ok_or_else(|| Fault::new("FORBIDDEN", "component has no registered context action"))?
            .to_owned();
        if w.actions.iter().filter(|a| a.status == "pending").count() >= 32 {
            return Err(Fault::new("LIMIT", "too many pending actions"));
        }
        while w.actions.len() >= 48 {
            if let Some(i) = w.actions.iter().position(|a| a.status != "pending") {
                w.actions.remove(i);
            } else {
                break;
            }
        }
        let event = UiEvent {
            id: Uuid::new_v4(),
            world_id: id,
            component_id: node_id.into(),
            action: action.clone(),
            value,
            lease_epoch: lease.key.epoch,
            revision: w.revision,
        };
        w.actions.push(ActionState {
            id: event.id,
            component_id: node_id.into(),
            action,
            status: "pending".into(),
            message: None,
            writer: Some(lease.session),
            lease_epoch: lease.key.epoch,
            deadline: now + ACTION_TIMEOUT_MS,
        });
        w.sequence += 1;
        Ok((lease.session, event))
    }
    pub fn acknowledge(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        acknowledgement: ActionAcknowledgement,
        now: u64,
    ) -> Result<()> {
        let w = self.writable(session, id, key, now)?;
        let a = w
            .actions
            .iter_mut()
            .find(|a| a.id == acknowledgement.event_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "action missing"))?;
        if a.writer != Some(session) || a.lease_epoch != key.epoch {
            return Err(Fault::new(
                "STALE_LEASE",
                "action belonged to another writer",
            ));
        }
        if a.status != "pending" {
            return Err(Fault::new(
                "ACTION_FINISHED",
                "action already completed or timed out",
            ));
        }
        if a.deadline <= now {
            return Err(Fault::new("ACTION_TIMEOUT", "action deadline elapsed"));
        }
        a.status = if acknowledgement.ok { "ok" } else { "error" }.into();
        a.message = acknowledgement
            .message
            .map(|s| s.chars().take(512).collect());
        w.sequence += 1;
        Ok(())
    }
    pub fn native_report(&mut self, id: Uuid, expected: u64, report: NativeReport) -> bool {
        let Some(w) = self.worlds.get_mut(&id) else {
            return false;
        };
        if w.window_revision != expected || w.native == report {
            return false;
        }
        w.native = report;
        w.sequence += 1;
        true
    }
    pub fn observe_geometry(
        &mut self,
        id: Uuid,
        position: Position,
        width: f64,
        height: f64,
    ) -> bool {
        let Some(w) = self.worlds.get_mut(&id) else {
            return false;
        };
        if w.window.geometry_control != GeometryControl::Human
            || w.native.applied_window_revision != Some(w.window_revision)
        {
            return false;
        }
        let mut next = w.window.clone();
        next.position = Some(position);
        next.width = width;
        next.height = height;
        if next.validate().is_err() || next == w.window {
            return false;
        }
        w.window = next;
        w.window_revision += 1;
        w.native.applied_window_revision = Some(w.window_revision);
        w.touch();
        true
    }
}
