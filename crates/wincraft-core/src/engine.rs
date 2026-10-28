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

#[derive(Clone, Debug)]
pub struct ScopeRevocation {
    pub scope_id: Uuid,
    pub generation: u64,
    pub sessions: Vec<Uuid>,
}

#[derive(Clone, Debug)]
pub struct ScopedStructurePatchResult {
    pub snapshot: Snapshot,
    pub revoked_scopes: Vec<ScopeRevocation>,
}

fn valid_data_namespace(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || "_-".contains(character))
}

fn rewrite_scope_binding_value(
    value: &mut Value,
    namespace: &str,
    to_global_path: bool,
) -> Result<()> {
    match value {
        Value::Object(object) if object.contains_key("$path") => {
            if object.len() != 1 {
                return Err(Fault::new(
                    "INVALID_SCENE",
                    "a data binding must contain only $path",
                ));
            }
            let path = object
                .get("$path")
                .and_then(Value::as_str)
                .ok_or_else(|| Fault::new("INVALID_SCENE", "$path must be a string"))?;
            let prefix = format!("/{namespace}");
            let rewritten = if to_global_path {
                if path.is_empty() {
                    prefix
                } else if path.starts_with('/') {
                    format!("{prefix}{path}")
                } else {
                    return Err(Fault::new(
                        "INVALID_SCENE",
                        "scope data path must be a JSON pointer",
                    ));
                }
            } else if path == prefix {
                String::new()
            } else if let Some(suffix) = path.strip_prefix(&format!("{prefix}/")) {
                format!("/{suffix}")
            } else {
                return Err(Fault::new(
                    "SCOPE_DATA_FORBIDDEN",
                    "component binding is outside its data namespace",
                ));
            };
            object.insert("$path".into(), Value::String(rewritten));
            Ok(())
        }
        Value::Object(object) => {
            for value in object.values_mut() {
                rewrite_scope_binding_value(value, namespace, to_global_path)?;
            }
            Ok(())
        }
        Value::Array(values) => {
            for value in values {
                rewrite_scope_binding_value(value, namespace, to_global_path)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn rewrite_scope_node_bindings(
    node: &mut Node,
    namespace: &str,
    to_global_path: bool,
) -> Result<()> {
    for value in node.props.values_mut() {
        rewrite_scope_binding_value(value, namespace, to_global_path)?;
    }
    for child in &mut node.children {
        rewrite_scope_node_bindings(child, namespace, to_global_path)?;
    }
    Ok(())
}

fn validate_parent_binding_value(value: &Value, namespaces: &[String]) -> Result<()> {
    match value {
        Value::Object(object) if object.contains_key("$path") => {
            if object.len() != 1 {
                return Err(Fault::new(
                    "INVALID_SCENE",
                    "a data binding must contain only $path",
                ));
            }
            let path = object
                .get("$path")
                .and_then(Value::as_str)
                .ok_or_else(|| Fault::new("INVALID_SCENE", "$path must be a string"))?;
            if !path.is_empty() && !path.starts_with('/') {
                return Err(Fault::new(
                    "INVALID_SCENE",
                    "a data binding must be a JSON pointer",
                ));
            }
            if let Some(first) = path
                .strip_prefix('/')
                .and_then(|value| value.split('/').next())
            {
                let decoded = first.replace("~1", "/").replace("~0", "~");
                if namespaces.iter().any(|namespace| namespace == &decoded) {
                    return Err(Fault::new(
                        "SCOPE_DATA_FORBIDDEN",
                        "root layout cannot bind into a child scope namespace",
                    ));
                }
            }
            Ok(())
        }
        Value::Object(object) => {
            for child in object.values() {
                validate_parent_binding_value(child, namespaces)?;
            }
            Ok(())
        }
        Value::Array(values) => {
            for child in values {
                validate_parent_binding_value(child, namespaces)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn validate_parent_layout_bindings(
    node: &Node,
    owned_roots: &[Node],
    namespaces: &[String],
) -> Result<()> {
    let inside_scope = owned_roots.iter().any(|root| root.find(&node.id).is_some());
    if !inside_scope {
        for value in node.props.values() {
            validate_parent_binding_value(value, namespaces)?;
        }
    }
    for child in &node.children {
        validate_parent_layout_bindings(child, owned_roots, namespaces)?;
    }
    Ok(())
}

fn scope_join_key() -> String {
    format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple())
}

fn scope_is_read_only(node: &Node) -> bool {
    !(node.kind.interactive() || node.kind == Kind::KeyValue && node.props.contains_key("action"))
        && node.children.iter().all(scope_is_read_only)
}

fn revoke_component_scope(scope: &mut ComponentScope) -> bool {
    let Some(writer) = scope.writer.take() else {
        return false;
    };
    scope.epoch += 1;
    scope.readers.insert(writer.session, JoinMode::Read);
    scope.revision += 1;
    true
}

fn revoke_component_scope_if_owned(scope: &mut ComponentScope, session: Uuid) -> bool {
    if scope
        .writer
        .as_ref()
        .is_some_and(|writer| writer.session == session)
    {
        revoke_component_scope(scope)
    } else {
        false
    }
}

impl Engine {
    pub fn register(&mut self, name: String, operator: bool) -> Result<Uuid> {
        self.register_with_protocol(name, operator, ProtocolVersion::Stable03)
    }
    pub fn register_with_protocol(
        &mut self,
        name: String,
        operator: bool,
        protocol: ProtocolVersion,
    ) -> Result<Uuid> {
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
        self.sessions.insert(
            id,
            Session {
                id,
                name,
                operator,
                protocol,
            },
        );
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
    fn require_component_leases_protocol(&self, session: Uuid) -> Result<()> {
        self.session(session)?;
        if !self.sessions[&session].protocol.supports_component_leases() {
            return Err(Fault::new(
                "PROTOCOL_MISMATCH",
                "component leases require the 0.4-preview.1 protocol",
            ));
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
        let operator = self.operator(session);
        let stable_session = self.sessions[&session].protocol == ProtocolVersion::Stable03;
        Ok(self
            .worlds
            .values()
            .filter(|world| {
                let visible = operator
                    || world.readers.contains_key(&session)
                    || (!world.system && world.join_policy == JoinPolicy::OpenAuthenticated);
                visible
                    && !(stable_session
                        && world.ownership_mode == OwnershipMode::ScopedSubtrees
                        && !operator)
            })
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
            ownership_mode: OwnershipMode::ExclusiveWorld,
            authority: None,
            scopes: BTreeMap::new(),
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
        if world.ownership_mode == OwnershipMode::ScopedSubtrees {
            if mode == JoinMode::Write {
                return Err(Fault::new(
                    "SCOPE_REQUIRED",
                    "claim a component scope instead of the complete world",
                ));
            }
            if !operator
                && world.authority.as_ref().map(|authority| authority.session) != Some(session)
            {
                return Err(Fault::new(
                    "SCOPE_REQUIRED",
                    "join a component scope instead of the complete world",
                ));
            }
            world.readers.entry(session).or_insert(JoinMode::Read);
            let snapshot = if operator {
                world.snapshot()
            } else {
                Self::authority_snapshot(world)
            };
            return Ok(JoinResult {
                world: snapshot,
                lease: None,
            });
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
    pub fn partition_scopes(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        expected_revision: u64,
        definitions: &[ScopeDefinition],
        now: u64,
    ) -> Result<ScopePartitionResult> {
        self.require_component_leases_protocol(session)?;
        let world = self.writable(session, id, key, now)?;
        Self::revision(world, expected_revision)?;
        if world.system {
            return Err(Fault::new(
                "FORBIDDEN",
                "internal system worlds cannot be partitioned by a provider",
            ));
        }
        if world.write_blocked {
            return Err(Fault::new(
                "OPERATOR_HOLD",
                "local operator has held this world",
            ));
        }
        if world.readers.len() != 1 || !world.readers.contains_key(&session) {
            return Err(Fault::new(
                "SCOPE_TRANSITION_CONFLICT",
                "all other world readers must leave before ownership is partitioned",
            ));
        }
        if !(2..=32).contains(&definitions.len()) {
            return Err(Fault::new(
                "LIMIT",
                "scope partition requires 2..32 disjoint subtrees",
            ));
        }

        let mut roots = Vec::with_capacity(definitions.len());
        let mut namespaces = Vec::with_capacity(definitions.len());
        for definition in definitions {
            if !valid_data_namespace(&definition.data_namespace)
                || namespaces.contains(&definition.data_namespace)
            {
                return Err(Fault::new(
                    "INVALID_SCOPE",
                    "data namespaces must be unique bounded identifiers",
                ));
            }
            let root = world
                .scene
                .root
                .find(&definition.root_node_id)
                .cloned()
                .ok_or_else(|| Fault::new("NOT_FOUND", "scope root component is missing"))?;
            if !scope_is_read_only(&root) {
                return Err(Fault::new(
                    "SCOPE_INTERACTIONS_UNAVAILABLE",
                    "B07-01 scopes are display/data-only until component action routing is implemented",
                ));
            }
            let mut local_view = root.clone();
            rewrite_scope_node_bindings(&mut local_view, &definition.data_namespace, false)?;
            roots.push(root);
            namespaces.push(definition.data_namespace.clone());
        }
        for left in 0..roots.len() {
            for right in (left + 1)..roots.len() {
                if roots[left].find(&roots[right].id).is_some()
                    || roots[right].find(&roots[left].id).is_some()
                {
                    return Err(Fault::new(
                        "SCOPE_OVERLAP",
                        "scope roots must identify disjoint subtrees",
                    ));
                }
            }
        }
        validate_parent_layout_bindings(&world.scene.root, &roots, &namespaces)?;

        let mut next_scene = world.scene.clone();
        if next_scene.data.is_null() {
            next_scene.data = Value::Object(serde_json::Map::new());
        }
        let data = next_scene.data.as_object_mut().ok_or_else(|| {
            Fault::new(
                "INVALID_SCOPE",
                "scope data namespaces require an object-valued scene.data root",
            )
        })?;
        for namespace in &namespaces {
            data.entry(namespace.clone()).or_insert(Value::Null);
        }
        next_scene.validate()?;

        let mut scopes = BTreeMap::new();
        let mut grants = Vec::with_capacity(definitions.len());
        for definition in definitions {
            let scope_id = Uuid::new_v4();
            let join_key = scope_join_key();
            let scope = ComponentScope {
                id: scope_id,
                root_node_id: definition.root_node_id.clone(),
                data_namespace: definition.data_namespace.clone(),
                generation: 1,
                epoch: 0,
                revision: 1,
                join_key: join_key.clone(),
                writer: None,
                readers: BTreeMap::new(),
                ever_claimed: false,
            };
            grants.push(ScopeGrant {
                scope_id,
                root_node_id: definition.root_node_id.clone(),
                data_namespace: definition.data_namespace.clone(),
                generation: scope.generation,
                join_key,
            });
            scopes.insert(scope_id, scope);
        }

        world.scene = next_scene;
        Self::revoke(world, "whole-world lease partitioned into component scopes");
        world.ownership_mode = OwnershipMode::ScopedSubtrees;
        world.readers.clear();
        world.readers.insert(session, JoinMode::Read);
        world.epoch += 1;
        let authority_lease = LeaseKey {
            id: Uuid::new_v4(),
            epoch: world.epoch,
        };
        world.authority = Some(WorldAuthorityLease {
            key: authority_lease.clone(),
            session,
            expires_at: now + LEASE_MS,
        });
        world.scopes = scopes;
        world.touch();
        Ok(ScopePartitionResult {
            world_id: world.id,
            world_epoch: world.epoch,
            world_revision: world.revision,
            authority_lease,
            scopes: grants,
        })
    }
    pub fn join_scope(
        &mut self,
        session: Uuid,
        request: ScopeJoinRequest,
        now: u64,
    ) -> Result<ScopeJoinResult> {
        let ScopeJoinRequest {
            world_id,
            scope_id,
            generation,
            join_key,
            mode,
        } = request;
        self.require_component_leases_protocol(session)?;
        let operator = self.operator(session);
        let world = self
            .worlds
            .get_mut(&world_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if world.ownership_mode != OwnershipMode::ScopedSubtrees {
            return Err(Fault::new("SCOPE_MODE", "world has no component scopes"));
        }
        if world.system && !operator {
            return Err(Fault::new("FORBIDDEN", "system world is private"));
        }
        let scope = world
            .scopes
            .get_mut(&scope_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "scope missing"))?;
        if scope.generation != generation {
            return Err(Fault::new(
                "STALE_SCOPE",
                "scope generation no longer matches",
            ));
        }
        if scope.join_key != join_key {
            return Err(Fault::new("FORBIDDEN", "scope grant key required"));
        }
        if world
            .authority
            .as_ref()
            .is_none_or(|authority| authority.expires_at <= now)
        {
            return Err(Fault::new(
                "PARENT_AUTHORITY_REQUIRED",
                "the world authority must be active before a child scope can be joined",
            ));
        }
        let lease = if mode == JoinMode::Write {
            if world.write_blocked {
                return Err(Fault::new(
                    "OPERATOR_HOLD",
                    "local operator has held this world; release it in the manager",
                ));
            }
            if scope
                .writer
                .as_ref()
                .is_some_and(|writer| writer.expires_at <= now)
            {
                revoke_component_scope(scope);
            }
            if let Some(writer) = scope.writer.as_mut() {
                if writer.session != session {
                    return Err(Fault::new(
                        "WRITE_CONFLICT",
                        "component scope already has an exclusive writer",
                    ));
                }
                writer.expires_at = now + LEASE_MS;
                scope.readers.insert(session, JoinMode::Write);
                Some(writer.key.clone())
            } else {
                scope.epoch += 1;
                let key = ScopedLeaseKey {
                    scope_id,
                    lease_id: Uuid::new_v4(),
                    epoch: scope.epoch,
                    generation: scope.generation,
                };
                scope.writer = Some(ScopedWriteLease {
                    key: key.clone(),
                    session,
                    expires_at: now + LEASE_MS,
                });
                scope.readers.insert(session, JoinMode::Write);
                scope.ever_claimed = true;
                scope.revision += 1;
                Some(key)
            }
        } else {
            if scope.readers.get(&session) != Some(&JoinMode::Write) {
                scope.readers.insert(session, JoinMode::Read);
            }
            scope
                .writer
                .as_ref()
                .and_then(|writer| (writer.session == session).then(|| writer.key.clone()))
        };
        world.readers.insert(session, JoinMode::Read);
        world.touch();
        let snapshot = Self::build_scope_snapshot(world, world.scopes.get(&scope_id).unwrap())?;
        Ok(ScopeJoinResult { snapshot, lease })
    }
    pub fn read_scope(
        &self,
        session: Uuid,
        world_id: Uuid,
        scope_id: Uuid,
        generation: u64,
    ) -> Result<ScopeSnapshot> {
        self.require_component_leases_protocol(session)?;
        let world = self
            .worlds
            .get(&world_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if world.ownership_mode != OwnershipMode::ScopedSubtrees {
            return Err(Fault::new("SCOPE_MODE", "world has no component scopes"));
        }
        if world.system && !self.operator(session) {
            return Err(Fault::new("FORBIDDEN", "system world is private"));
        }
        let scope = world
            .scopes
            .get(&scope_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "scope missing"))?;
        if scope.generation != generation {
            return Err(Fault::new(
                "STALE_SCOPE",
                "scope generation no longer matches",
            ));
        }
        if !self.operator(session) && !scope.readers.contains_key(&session) {
            return Err(Fault::new("FORBIDDEN", "join the scope before reading"));
        }
        Self::build_scope_snapshot(world, scope)
    }

    pub fn read_scopes(&self, session: Uuid, world_id: Uuid) -> Result<Vec<ScopeSnapshot>> {
        self.require_component_leases_protocol(session)?;
        let world = self
            .worlds
            .get(&world_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if world.ownership_mode != OwnershipMode::ScopedSubtrees {
            return Err(Fault::new("SCOPE_MODE", "world has no component scopes"));
        }
        if world.system && !self.operator(session) {
            return Err(Fault::new("FORBIDDEN", "system world is private"));
        }
        world
            .scopes
            .values()
            .filter(|scope| scope.readers.contains_key(&session))
            .map(|scope| Self::build_scope_snapshot(world, scope))
            .collect()
    }
    pub fn patch_scope(
        &mut self,
        session: Uuid,
        world_id: Uuid,
        key: &ScopedLeaseKey,
        expected_scope_revision: u64,
        ops: &[SceneOp],
        now: u64,
    ) -> Result<ScopeSnapshot> {
        self.require_component_leases_protocol(session)?;
        let world = self
            .worlds
            .get_mut(&world_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        Self::require_scope_writer(world, session, key, now)?;
        let (root_node_id, namespace, current_revision) = {
            let scope = world.scopes.get(&key.scope_id).unwrap();
            (
                scope.root_node_id.clone(),
                scope.data_namespace.clone(),
                scope.revision,
            )
        };
        if current_revision != expected_scope_revision {
            return Err(Fault::new(
                "SCOPE_REVISION_CONFLICT",
                format!("expected {expected_scope_revision}, actual {current_revision}"),
            ));
        }
        let mut next_scene = world.scene.clone();
        for operation in ops {
            let scope_root = next_scene.root.find(&root_node_id).ok_or_else(|| {
                Fault::new(
                    "STALE_SCOPE",
                    "scope root component is no longer in the scene",
                )
            })?;
            let scoped_operation = match operation {
                SceneOp::Props { node_id, props } => {
                    if scope_root.find(node_id).is_none() {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "property update targets a component outside this scope",
                        ));
                    }
                    let mut props = props.clone();
                    for value in props.values_mut() {
                        rewrite_scope_binding_value(value, &namespace, true)?;
                    }
                    SceneOp::Props {
                        node_id: node_id.clone(),
                        props,
                    }
                }
                SceneOp::Insert {
                    parent,
                    index,
                    node,
                } => {
                    if scope_root.find(parent).is_none() {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "insert parent is outside this component scope",
                        ));
                    }
                    if !scope_is_read_only(node) {
                        return Err(Fault::new(
                            "SCOPE_INTERACTIONS_UNAVAILABLE",
                            "component actions are not routed by scope owner yet",
                        ));
                    }
                    let mut node = node.clone();
                    rewrite_scope_node_bindings(&mut node, &namespace, true)?;
                    SceneOp::Insert {
                        parent: parent.clone(),
                        index: *index,
                        node,
                    }
                }
                SceneOp::Remove { node_id } => {
                    if node_id == &root_node_id {
                        return Err(Fault::new(
                            "SCOPE_ROOT_IMMUTABLE",
                            "only the world authority may remove a scope root",
                        ));
                    }
                    if scope_root.find(node_id).is_none() {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "remove target is outside this component scope",
                        ));
                    }
                    SceneOp::Remove {
                        node_id: node_id.clone(),
                    }
                }
                SceneOp::Replace { node_id, node } => {
                    if scope_root.find(node_id).is_none() {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "replace target is outside this component scope",
                        ));
                    }
                    if node_id == &root_node_id && node.id != root_node_id {
                        return Err(Fault::new(
                            "SCOPE_ROOT_IMMUTABLE",
                            "a scope replacement must preserve its root component ID",
                        ));
                    }
                    if !scope_is_read_only(node) {
                        return Err(Fault::new(
                            "SCOPE_INTERACTIONS_UNAVAILABLE",
                            "component actions are not routed by scope owner yet",
                        ));
                    }
                    let mut node = node.clone();
                    rewrite_scope_node_bindings(&mut node, &namespace, true)?;
                    SceneOp::Replace {
                        node_id: node_id.clone(),
                        node,
                    }
                }
                SceneOp::Move {
                    node_id,
                    parent,
                    index,
                } => {
                    if node_id == &root_node_id {
                        return Err(Fault::new(
                            "SCOPE_ROOT_IMMUTABLE",
                            "only the world authority may move a scope root",
                        ));
                    }
                    if scope_root.find(node_id).is_none() || scope_root.find(parent).is_none() {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "move source and destination must both be inside this scope",
                        ));
                    }
                    SceneOp::Move {
                        node_id: node_id.clone(),
                        parent: parent.clone(),
                        index: *index,
                    }
                }
            };
            next_scene = next_scene.patch(std::slice::from_ref(&scoped_operation))?;
        }
        let final_scope_root = next_scene.root.find(&root_node_id).ok_or_else(|| {
            Fault::new(
                "STALE_SCOPE",
                "scope root component is no longer in the scene",
            )
        })?;
        if !scope_is_read_only(final_scope_root) {
            return Err(Fault::new(
                "SCOPE_INTERACTIONS_UNAVAILABLE",
                "component actions are not routed by scope owner yet",
            ));
        }
        world.scene = next_scene;
        let scope = world.scopes.get_mut(&key.scope_id).unwrap();
        scope.revision += 1;
        world.touch();
        Self::build_scope_snapshot(world, world.scopes.get(&key.scope_id).unwrap())
    }
    pub fn patch_scope_structure(
        &mut self,
        session: Uuid,
        world_id: Uuid,
        authority_lease: &LeaseKey,
        expected_revision: u64,
        ops: &[SceneOp],
        now: u64,
    ) -> Result<ScopedStructurePatchResult> {
        self.require_component_leases_protocol(session)?;
        let world = self.authority_writable(session, world_id, authority_lease, now)?;
        Self::revision(world, expected_revision)?;
        let mut next_scene = world.scene.clone();
        let mut revoked_ids = Vec::<Uuid>::new();

        for operation in ops {
            let active_scopes = world
                .scopes
                .iter()
                .filter(|(scope_id, _)| !revoked_ids.contains(scope_id))
                .map(|(_, scope)| scope)
                .collect::<Vec<_>>();
            let node_is_inside_scope = |node_id: &str| {
                active_scopes.iter().any(|scope| {
                    next_scene
                        .root
                        .find(&scope.root_node_id)
                        .is_some_and(|root| root.find(node_id).is_some())
                })
            };

            let root_operation = match operation {
                SceneOp::Props { node_id, props } => {
                    if node_is_inside_scope(node_id) {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "world authority cannot patch props inside a child scope",
                        ));
                    }
                    let target = next_scene
                        .root
                        .find(node_id)
                        .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
                    if target.kind.interactive()
                        || target.kind == Kind::KeyValue && props.contains_key("action")
                    {
                        return Err(Fault::new(
                            "SCOPE_INTERACTIONS_UNAVAILABLE",
                            "composition structure does not yet route component actions",
                        ));
                    }
                    let namespaces = active_scopes
                        .iter()
                        .map(|scope| scope.data_namespace.clone())
                        .collect::<Vec<_>>();
                    for value in props.values() {
                        validate_parent_binding_value(value, &namespaces)?;
                    }
                    operation.clone()
                }
                SceneOp::Insert {
                    parent,
                    index,
                    node,
                } => {
                    if node_is_inside_scope(parent) {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "world authority cannot insert into a child scope",
                        ));
                    }
                    if !scope_is_read_only(node) {
                        return Err(Fault::new(
                            "SCOPE_INTERACTIONS_UNAVAILABLE",
                            "composition structure does not yet route component actions",
                        ));
                    }
                    let namespaces = active_scopes
                        .iter()
                        .map(|scope| scope.data_namespace.clone())
                        .collect::<Vec<_>>();
                    validate_parent_layout_bindings(node, &[], &namespaces)?;
                    SceneOp::Insert {
                        parent: parent.clone(),
                        index: *index,
                        node: node.clone(),
                    }
                }
                SceneOp::Remove { node_id } => {
                    let target = next_scene
                        .root
                        .find(node_id)
                        .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
                    let is_scope_root = active_scopes
                        .iter()
                        .any(|scope| scope.root_node_id == *node_id);
                    if node_is_inside_scope(node_id) && !is_scope_root {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "world authority cannot remove a descendant owned by a child scope",
                        ));
                    }
                    for scope in &active_scopes {
                        if target.find(&scope.root_node_id).is_some()
                            && !revoked_ids.contains(&scope.id)
                        {
                            revoked_ids.push(scope.id);
                        }
                    }
                    SceneOp::Remove {
                        node_id: node_id.clone(),
                    }
                }
                SceneOp::Replace { node_id, node } => {
                    let target = next_scene
                        .root
                        .find(node_id)
                        .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
                    if node_is_inside_scope(node_id)
                        || active_scopes
                            .iter()
                            .any(|scope| target.find(&scope.root_node_id).is_some())
                    {
                        return Err(Fault::new(
                            "SCOPE_BOUNDARY",
                            "replace cannot rewrite a node that contains a child scope; remove it explicitly to revoke the child",
                        ));
                    }
                    if !scope_is_read_only(node) {
                        return Err(Fault::new(
                            "SCOPE_INTERACTIONS_UNAVAILABLE",
                            "composition structure does not yet route component actions",
                        ));
                    }
                    let namespaces = active_scopes
                        .iter()
                        .map(|scope| scope.data_namespace.clone())
                        .collect::<Vec<_>>();
                    validate_parent_layout_bindings(node, &[], &namespaces)?;
                    SceneOp::Replace {
                        node_id: node_id.clone(),
                        node: node.clone(),
                    }
                }
                SceneOp::Move {
                    node_id,
                    parent,
                    index,
                } => {
                    next_scene
                        .root
                        .find(node_id)
                        .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
                    let is_scope_root = active_scopes
                        .iter()
                        .any(|scope| scope.root_node_id == *node_id);
                    if node_is_inside_scope(node_id) && !is_scope_root {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "world authority may move a child scope root, not its internal nodes",
                        ));
                    }
                    if node_is_inside_scope(parent) {
                        return Err(Fault::new(
                            "SCOPE_FORBIDDEN",
                            "world authority cannot move layout into a child scope",
                        ));
                    }
                    SceneOp::Move {
                        node_id: node_id.clone(),
                        parent: parent.clone(),
                        index: *index,
                    }
                }
            };
            next_scene = next_scene.patch(std::slice::from_ref(&root_operation))?;
        }

        let mut revoked_scopes = Vec::new();
        for scope_id in &revoked_ids {
            let Some(scope) = world.scopes.get(scope_id) else {
                continue;
            };
            let mut sessions = scope.readers.keys().copied().collect::<Vec<_>>();
            if let Some(writer) = &scope.writer {
                sessions.push(writer.session);
            }
            sessions.sort_unstable();
            sessions.dedup();
            revoked_scopes.push(ScopeRevocation {
                scope_id: *scope_id,
                generation: scope.generation,
                sessions,
            });
            let data = next_scene.data.as_object_mut().ok_or_else(|| {
                Fault::new("INVALID_SCOPE", "composed scene data must be an object")
            })?;
            data.remove(&scope.data_namespace);
        }
        next_scene.validate()?;

        for scope_id in &revoked_ids {
            world.scopes.remove(scope_id);
        }
        for revocation in &revoked_scopes {
            for session in &revocation.sessions {
                let still_joined = world
                    .scopes
                    .values()
                    .any(|scope| scope.readers.contains_key(session));
                if !still_joined
                    && world.authority.as_ref().map(|authority| authority.session) != Some(*session)
                {
                    world.readers.remove(session);
                }
            }
        }
        world.scene = next_scene;
        world.touch();
        Ok(ScopedStructurePatchResult {
            snapshot: Self::authority_snapshot(world),
            revoked_scopes,
        })
    }

    pub fn replace_scope_data(
        &mut self,
        session: Uuid,
        world_id: Uuid,
        key: &ScopedLeaseKey,
        expected_scope_revision: u64,
        data: Value,
        now: u64,
    ) -> Result<ScopeSnapshot> {
        self.require_component_leases_protocol(session)?;
        let world = self
            .worlds
            .get_mut(&world_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        Self::require_scope_writer(world, session, key, now)?;
        let (namespace, current_revision) = {
            let scope = world.scopes.get(&key.scope_id).unwrap();
            (scope.data_namespace.clone(), scope.revision)
        };
        if current_revision != expected_scope_revision {
            return Err(Fault::new(
                "SCOPE_REVISION_CONFLICT",
                format!("expected {expected_scope_revision}, actual {current_revision}"),
            ));
        }
        let mut next_scene = world.scene.clone();
        let namespaces = next_scene
            .data
            .as_object_mut()
            .ok_or_else(|| Fault::new("INVALID_SCOPE", "composed scene data must be an object"))?;
        namespaces.insert(namespace, data);
        next_scene.validate()?;
        world.scene = next_scene;
        let scope = world.scopes.get_mut(&key.scope_id).unwrap();
        scope.revision += 1;
        world.touch();
        Self::build_scope_snapshot(world, world.scopes.get(&key.scope_id).unwrap())
    }
    pub fn renew_scope(
        &mut self,
        session: Uuid,
        world_id: Uuid,
        key: &ScopedLeaseKey,
        now: u64,
    ) -> Result<()> {
        self.require_component_leases_protocol(session)?;
        let world = self
            .worlds
            .get_mut(&world_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        Self::require_scope_writer(world, session, key, now)?;
        let scope = world.scopes.get_mut(&key.scope_id).unwrap();
        scope.writer.as_mut().unwrap().expires_at = now + LEASE_MS;
        Ok(())
    }
    pub fn leave_scope(&mut self, session: Uuid, world_id: Uuid, scope_id: Uuid) -> Result<()> {
        self.require_component_leases_protocol(session)?;
        let world = self
            .worlds
            .get_mut(&world_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if world.ownership_mode != OwnershipMode::ScopedSubtrees {
            return Err(Fault::new("SCOPE_MODE", "world has no component scopes"));
        }
        let scope = world
            .scopes
            .get_mut(&scope_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "scope missing"))?;
        let mut changed = false;
        if scope
            .writer
            .as_ref()
            .is_some_and(|writer| writer.session == session)
        {
            revoke_component_scope(scope);
            changed = true;
        }
        changed |= scope.readers.remove(&session).is_some();
        if world
            .authority
            .as_ref()
            .is_none_or(|authority| authority.session != session)
            && !world
                .scopes
                .values()
                .any(|other| other.readers.contains_key(&session))
        {
            world.readers.remove(&session);
        }
        if changed {
            world.touch();
        }
        Ok(())
    }
    pub fn read(&self, session: Uuid, id: Uuid) -> Result<Snapshot> {
        self.session(session)?;
        let world = self
            .worlds
            .get(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if world.ownership_mode == OwnershipMode::ScopedSubtrees {
            if self.operator(session) {
                return Ok(world.snapshot());
            }
            if !world.readers.contains_key(&session) {
                return Err(Fault::new(
                    "FORBIDDEN",
                    "join the world or a component scope before reading",
                ));
            }
            if world.authority.as_ref().map(|authority| authority.session) == Some(session) {
                return Ok(Self::authority_snapshot(world));
            }
            return Err(Fault::new(
                "SCOPE_REQUIRED",
                "read a granted component scope instead of the complete world",
            ));
        }
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
        if world.ownership_mode != OwnershipMode::ExclusiveWorld {
            return Err(Fault::new(
                "SCOPE_MODE",
                "whole-world writes are disabled after scope partitioning",
            ));
        }
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
    fn authority_writable(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        now: u64,
    ) -> Result<&mut World> {
        self.require_component_leases_protocol(session)?;
        let world = self
            .worlds
            .get_mut(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        if world.ownership_mode != OwnershipMode::ScopedSubtrees {
            return Err(Fault::new("LEASE_MODE", "world has no scoped authority"));
        }
        if world.write_blocked {
            return Err(Fault::new(
                "OPERATOR_HOLD",
                "local operator has held this world",
            ));
        }
        let authority = world
            .authority
            .as_ref()
            .ok_or_else(|| Fault::new("STALE_AUTHORITY", "world authority has been revoked"))?;
        if authority.session != session || authority.key != *key {
            return Err(Fault::new(
                "STALE_AUTHORITY",
                "world authority does not match",
            ));
        }
        if authority.expires_at <= now {
            return Err(Fault::new("LEASE_EXPIRED", "world authority has expired"));
        }
        Ok(world)
    }
    fn window_writable(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        now: u64,
    ) -> Result<&mut World> {
        let mode = self
            .worlds
            .get(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?
            .ownership_mode;
        match mode {
            OwnershipMode::ExclusiveWorld => self.writable(session, id, key, now),
            OwnershipMode::ScopedSubtrees => self.authority_writable(session, id, key, now),
        }
    }
    fn require_scope_writer(
        world: &World,
        session: Uuid,
        key: &ScopedLeaseKey,
        now: u64,
    ) -> Result<()> {
        if world.ownership_mode != OwnershipMode::ScopedSubtrees {
            return Err(Fault::new(
                "SCOPE_MODE",
                "world is not partitioned into scopes",
            ));
        }
        if world.write_blocked {
            return Err(Fault::new(
                "OPERATOR_HOLD",
                "local operator has held this world",
            ));
        }
        let scope = world
            .scopes
            .get(&key.scope_id)
            .ok_or_else(|| Fault::new("STALE_SCOPE", "scope has been revoked"))?;
        if scope.generation != key.generation {
            return Err(Fault::new(
                "STALE_SCOPE",
                "scope generation no longer matches",
            ));
        }
        if world
            .authority
            .as_ref()
            .is_none_or(|authority| authority.expires_at <= now)
        {
            return Err(Fault::new(
                "PARENT_AUTHORITY_REVOKED",
                "the parent world authority is no longer active",
            ));
        }
        let lease = scope
            .writer
            .as_ref()
            .ok_or_else(|| Fault::new("STALE_SCOPE_LEASE", "scope has no writer"))?;
        if lease.session != session || lease.key != *key {
            return Err(Fault::new(
                "STALE_SCOPE_LEASE",
                "writer, scope, lease or generation no longer matches",
            ));
        }
        if lease.expires_at <= now {
            return Err(Fault::new("LEASE_EXPIRED", "scope lease has expired"));
        }
        Ok(())
    }
    fn build_scope_snapshot(world: &World, scope: &ComponentScope) -> Result<ScopeSnapshot> {
        let mut root = world
            .scene
            .root
            .find(&scope.root_node_id)
            .cloned()
            .ok_or_else(|| Fault::new("NOT_FOUND", "scope root is no longer in the scene"))?;
        rewrite_scope_node_bindings(&mut root, &scope.data_namespace, false)?;
        let data = world
            .scene
            .data
            .as_object()
            .and_then(|namespaces| namespaces.get(&scope.data_namespace))
            .cloned()
            .unwrap_or(Value::Null);
        let status = if scope.writer.is_some() {
            "online"
        } else if scope.ever_claimed {
            "stale"
        } else {
            "vacant"
        };
        Ok(ScopeSnapshot {
            world_id: world.id,
            scope_id: scope.id,
            root_node_id: scope.root_node_id.clone(),
            generation: scope.generation,
            revision: scope.revision,
            sequence: world.sequence,
            writer: scope.writer.as_ref().map(|lease| lease.session),
            status: status.into(),
            root,
            data,
        })
    }
    fn authority_snapshot(world: &World) -> Snapshot {
        let mut snapshot = world.snapshot();
        if let Some(data) = snapshot.scene.data.as_object_mut() {
            for scope in world.scopes.values() {
                data.remove(&scope.data_namespace);
            }
        }
        for scope in world.scopes.values() {
            if let Some(node) = snapshot.scene.root.find_mut(&scope.root_node_id) {
                node.kind = crate::scene::Kind::Stack;
                node.props.clear();
                node.children.clear();
            }
        }
        snapshot
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
        let mode = self
            .worlds
            .get(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?
            .ownership_mode;
        let world = match mode {
            OwnershipMode::ExclusiveWorld => self.writable(session, id, key, now)?,
            OwnershipMode::ScopedSubtrees => self.authority_writable(session, id, key, now)?,
        };
        if mode == OwnershipMode::ScopedSubtrees {
            world.authority.as_mut().unwrap().expires_at = now + LEASE_MS;
        } else {
            world.writer.as_mut().unwrap().expires_at = now + LEASE_MS;
        }
        Ok(())
    }
    pub fn release(
        &mut self,
        session: Uuid,
        id: Uuid,
        key: &LeaseKey,
        now: u64,
    ) -> Result<Snapshot> {
        let mode = self
            .worlds
            .get(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?
            .ownership_mode;
        if mode == OwnershipMode::ScopedSubtrees {
            let world = self.authority_writable(session, id, key, now)?;
            world.authority = None;
            world.epoch += 1;
            Self::revoke_scopes_for_parent(world);
            world.touch();
            return Ok(Self::authority_snapshot(world));
        }
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
        if world.ownership_mode == OwnershipMode::ScopedSubtrees {
            let before = world.sequence;
            if world.authority.as_ref().map(|authority| authority.session) == Some(session) {
                world.authority = None;
                world.epoch += 1;
                Self::revoke_scopes_for_parent(world);
                world.touch();
            }
            let mut scope_changed = false;
            for scope in world.scopes.values_mut() {
                scope_changed |= revoke_component_scope_if_owned(scope, session);
                scope.readers.remove(&session);
            }
            world.readers.remove(&session);
            if scope_changed && world.sequence == before {
                world.touch();
            }
            return Ok(());
        }
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
        let world = self.window_writable(session, id, key, now)?;
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
        self.window_writable(session, id, key, now)?;
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
            w.authority = None;
            Self::revoke_scopes_for_parent(w);
            w.write_blocked = true;
        }
        w.window.visible = true;
        w.window.click_through = false;
        w.window.geometry_control = GeometryControl::Human;
        w.window.position_control = None;
        w.window.anchor = None;
        w.window.title_bar_visible = true;
        w.window.text_selectable = true;
        w.window.position = None;
        w.window.resizable = true;
        w.window.surface_opacity = 1.0;
        w.window.background_drag_enabled = true;
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
            let before = w.sequence;
            if w.writer.as_ref().map(|x| x.session) == Some(session) {
                Self::revoke(w, "provider disconnected");
            }
            if w.authority.as_ref().map(|x| x.session) == Some(session) {
                w.authority = None;
                w.epoch += 1;
                Self::revoke_scopes_for_parent(w);
                w.touch();
            }
            let mut scope_changed = false;
            for scope in w.scopes.values_mut() {
                scope_changed |= revoke_component_scope_if_owned(scope, session);
                scope.readers.remove(&session);
            }
            if scope_changed && w.sequence == before {
                w.touch();
            }
            w.readers.remove(&session);
            if w.sequence != before {
                changed.push(w.id);
            }
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
            if w.authority
                .as_ref()
                .is_some_and(|authority| authority.expires_at <= now)
            {
                w.authority = None;
                w.epoch += 1;
                Self::revoke_scopes_for_parent(w);
                w.touch();
            }
            let mut scope_changed = false;
            for scope in w.scopes.values_mut() {
                if scope
                    .writer
                    .as_ref()
                    .is_some_and(|writer| writer.expires_at <= now)
                {
                    scope_changed |= revoke_component_scope(scope);
                }
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
            if scope_changed && w.sequence == before {
                w.touch();
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
        self.interact_with_source(
            id,
            node_id,
            value,
            if context_action {
                InteractionSource::ContextMenu
            } else {
                InteractionSource::Click
            },
            expected_revision,
            now,
        )
    }
    pub fn native_window_action(
        &self,
        id: Uuid,
        node_id: &str,
        source: InteractionSource,
        expected_revision: u64,
        now: u64,
    ) -> Result<Option<NativeWindowAction>> {
        if source != InteractionSource::Click {
            return Ok(None);
        }
        let world = self
            .worlds
            .get(&id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "world missing"))?;
        Self::revision(world, expected_revision)?;
        let node = world
            .scene
            .root
            .find(node_id)
            .ok_or_else(|| Fault::new("NOT_FOUND", "component missing"))?;
        let Some(action) = node.props.get("native_window_action") else {
            return Ok(None);
        };
        if node.kind != Kind::Button {
            return Err(Fault::new(
                "FORBIDDEN",
                "native focus is only valid on buttons",
            ));
        }
        if world
            .writer
            .as_ref()
            .filter(|lease| lease.expires_at > now)
            .is_none()
        {
            return Err(Fault::new("OFFLINE", "no active writer"));
        }
        let disabled = node
            .props
            .get("disabled")
            .map(|value| {
                if let Some(path) = value.get("$path").and_then(Value::as_str) {
                    world
                        .scene
                        .data
                        .pointer(path)
                        .and_then(Value::as_bool)
                        .unwrap_or(false)
                } else {
                    value.as_bool().unwrap_or(false)
                }
            })
            .unwrap_or(false);
        if disabled {
            return Err(Fault::new("FORBIDDEN", "component disabled"));
        }
        let action = serde_json::from_value(action.clone())
            .map_err(|_| Fault::new("INVALID_SCENE", "invalid native window action"))?;
        Ok(Some(action))
    }
    pub fn interact_with_source(
        &mut self,
        id: Uuid,
        node_id: &str,
        value: Value,
        source: InteractionSource,
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
        let key_value_action = node.kind == Kind::KeyValue
            && node.props.get("action").and_then(Value::as_str).is_some();
        if !node.kind.interactive() && !key_value_action {
            return Err(Fault::new("FORBIDDEN", "component is not interactive"));
        }
        if node.kind == Kind::KeyValue {
            let key = value
                .as_object()
                .filter(|record| record.len() == 1)
                .and_then(|record| record.get("key"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if source != InteractionSource::Click || key.is_empty() || key.chars().count() > 64 {
                return Err(Fault::new(
                    "INVALID_EVENT",
                    "key_value action must be a click with one bounded row key",
                ));
            }
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
            Kind::Input | Kind::TextArea => {
                let max_bytes = if node.kind == Kind::TextArea {
                    32_768
                } else {
                    4_096
                };
                if !value.is_string() || value.as_str().unwrap().len() > max_bytes {
                    return Err(Fault::new(
                        "INVALID_EVENT",
                        format!("text input must be at most {max_bytes} UTF-8 bytes"),
                    ));
                }
            }
            Kind::Button => {
                if !value.is_null() {
                    return Err(Fault::new("INVALID_EVENT", "button carries null value"));
                }
            }
            Kind::KeyValue => {}
            _ => unreachable!(),
        }
        let action_property = match source {
            InteractionSource::Click => "action",
            InteractionSource::ContextMenu => "context_action",
            InteractionSource::Escape => {
                if node.kind != Kind::Button
                    || node.props.get("shortcut").and_then(Value::as_str) != Some("escape")
                {
                    return Err(Fault::new("FORBIDDEN", "Escape action is not registered"));
                }
                "shortcut_action"
            }
            InteractionSource::ControlEnter => {
                if node.kind != Kind::TextArea
                    || node.props.get("shortcut").and_then(Value::as_str) != Some("ctrl_enter")
                {
                    return Err(Fault::new(
                        "FORBIDDEN",
                        "Ctrl+Enter action is not registered",
                    ));
                }
                "shortcut_action"
            }
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

    fn revoke_scopes_for_parent(world: &mut World) {
        for scope in world.scopes.values_mut() {
            if let Some(writer) = scope.writer.take() {
                scope.readers.insert(writer.session, JoinMode::Read);
            }
            scope.epoch += 1;
            scope.generation += 1;
            scope.revision += 1;
            scope.join_key = scope_join_key();
        }
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
        let human_position = w.window.effective_position_control() == GeometryControl::Human;
        let human_size = w.window.geometry_control == GeometryControl::Human;
        if (!human_position && !human_size)
            || w.native.applied_window_revision != Some(w.window_revision)
        {
            return false;
        }
        let mut next = w.window.clone();
        if human_position {
            next.position = Some(position);
            next.anchor = None;
        }
        if human_size {
            next.width = width;
            next.height = height;
        }
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
