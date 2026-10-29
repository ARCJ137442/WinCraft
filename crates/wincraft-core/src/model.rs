use crate::Scene;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use uuid::Uuid;

pub const PROTOCOL: &str = "0.3";
pub const COMPONENT_LEASES_PREVIEW_PROTOCOL: &str = "0.4-preview.1";
pub const MAX_WORLDS: usize = 16;
pub const MAX_SCOPES_PER_WORLD: usize = 32;
pub const LEASE_MS: u64 = 15_000;
pub const ACTION_TIMEOUT_MS: u64 = 10_000;
pub const MAX_PAYLOAD: usize = 262_144;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Fault {
    pub code: String,
    pub message: String,
}
impl Fault {
    pub fn new(code: &str, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
}
impl std::fmt::Display for Fault {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for Fault {}
pub type Result<T> = std::result::Result<T, Fault>;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum ProtocolVersion {
    #[default]
    Stable03,
    ComponentLeasesPreview01,
}
impl ProtocolVersion {
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            PROTOCOL => Some(Self::Stable03),
            COMPONENT_LEASES_PREVIEW_PROTOCOL => Some(Self::ComponentLeasesPreview01),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Stable03 => PROTOCOL,
            Self::ComponentLeasesPreview01 => COMPONENT_LEASES_PREVIEW_PROTOCOL,
        }
    }

    pub fn supports_component_leases(self) -> bool {
        matches!(self, Self::ComponentLeasesPreview01)
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum GeometryControl {
    Provider,
    #[default]
    Human,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum JoinPolicy {
    OpenAuthenticated,
    #[default]
    Invite,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum JoinMode {
    Read,
    Write,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum WindowEventType {
    #[serde(rename = "window.geometry_changed")]
    GeometryChanged,
    #[serde(rename = "window.visibility_changed")]
    VisibilityChanged,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum EventSource {
    Provider,
    Operator,
    Human,
    Host,
    System,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum EventDeliveryClass {
    State,
    Occurrence,
}

#[derive(Clone, Debug, Serialize)]
pub struct TypedWindowEvent {
    pub event_id: Uuid,
    pub subscription_id: Uuid,
    pub world_id: Uuid,
    #[serde(rename = "type")]
    pub event_type: WindowEventType,
    pub delivery: EventDeliveryClass,
    pub source: EventSource,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cause_id: Option<String>,
    pub sequence: u64,
    pub window_revision: u64,
    pub payload: Value,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Position {
    pub x: i32,
    pub y: i32,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WorkAreaCorner {
    TopLeft,
    TopRight,
    BottomLeft,
    BottomRight,
}

/// A logical-pixel anchor relative to the current monitor work area.
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct WorkAreaAnchor {
    pub corner: WorkAreaCorner,
    pub margin_x: f64,
    pub margin_y: f64,
}

impl WorkAreaAnchor {
    pub fn validate(&self) -> Result<()> {
        if !self.margin_x.is_finite()
            || !self.margin_y.is_finite()
            || !(0.0..=10_000.0).contains(&self.margin_x)
            || !(0.0..=10_000.0).contains(&self.margin_y)
        {
            return Err(Fault::new(
                "INVALID_WINDOW",
                "work area anchor margins must be finite and within 0..=10000 logical pixels",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(default, deny_unknown_fields)]
pub struct WindowSpec {
    pub title: String,
    /// Logical pixels. Positions are explicitly physical desktop pixels.
    pub width: f64,
    pub height: f64,
    pub position: Option<Position>,
    pub anchor: Option<WorkAreaAnchor>,
    pub always_on_top: bool,
    pub visible: bool,
    pub resizable: bool,
    pub title_bar_visible: bool,
    /// Lets blank, non-interactive renderer surfaces act as a native drag handle.
    pub background_drag_enabled: bool,
    /// Default text-selection behavior for the world; component styles may override it.
    pub text_selectable: bool,
    pub decorations: bool,
    pub skip_taskbar: bool,
    pub click_through: bool,
    pub geometry_control: GeometryControl,
    /// Optional independent owner for placement; absent values inherit `geometry_control`.
    pub position_control: Option<GeometryControl>,
    /// Alpha for the rendered surface over the transparent native window.
    pub surface_opacity: f64,
}
impl Default for WindowSpec {
    fn default() -> Self {
        Self {
            title: "空白世界".into(),
            width: 412.0,
            height: 300.0,
            position: None,
            anchor: None,
            always_on_top: true,
            visible: true,
            resizable: true,
            title_bar_visible: true,
            background_drag_enabled: true,
            text_selectable: true,
            decorations: false,
            skip_taskbar: true,
            click_through: false,
            geometry_control: GeometryControl::Human,
            position_control: None,
            surface_opacity: 0.8,
        }
    }
}
impl WindowSpec {
    pub fn effective_position_control(&self) -> GeometryControl {
        self.position_control.unwrap_or(self.geometry_control)
    }

    pub fn validate(&self) -> Result<()> {
        if self.title.chars().count() > 100 {
            return Err(Fault::new("INVALID_WINDOW", "title too long"));
        }
        if !self.width.is_finite()
            || !self.height.is_finite()
            || !(160.0..=2400.0).contains(&self.width)
            || !(50.0..=1800.0).contains(&self.height)
        {
            return Err(Fault::new(
                "INVALID_WINDOW",
                "size outside 160..2400 × 50..1800 logical pixels",
            ));
        }
        if !self.surface_opacity.is_finite() || !(0.15..=1.0).contains(&self.surface_opacity) {
            return Err(Fault::new(
                "INVALID_WINDOW",
                "surface_opacity must be 0.15..1",
            ));
        }
        if let Some(p) = &self.position {
            if p.x.abs_diff(0) > 100_000 || p.y.abs_diff(0) > 100_000 {
                return Err(Fault::new(
                    "INVALID_WINDOW",
                    "position outside prototype bounds",
                ));
            }
        }
        if let Some(anchor) = self.anchor {
            anchor.validate()?;
        }
        Ok(())
    }
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct WindowPatch {
    pub title: Option<String>,
    pub width: Option<f64>,
    pub height: Option<f64>,
    pub position: Option<Position>,
    pub anchor: Option<WorkAreaAnchor>,
    pub always_on_top: Option<bool>,
    pub visible: Option<bool>,
    pub resizable: Option<bool>,
    pub title_bar_visible: Option<bool>,
    pub background_drag_enabled: Option<bool>,
    pub text_selectable: Option<bool>,
    pub decorations: Option<bool>,
    pub skip_taskbar: Option<bool>,
    pub click_through: Option<bool>,
    pub geometry_control: Option<GeometryControl>,
    pub position_control: Option<GeometryControl>,
    pub surface_opacity: Option<f64>,
}
impl WindowPatch {
    pub fn apply(&self, old: &WindowSpec) -> Result<WindowSpec> {
        let size_control = self.geometry_control.unwrap_or(old.geometry_control);
        let position_control = self
            .position_control
            .or(old.position_control)
            .unwrap_or(size_control);
        let human_size_write = size_control == GeometryControl::Human
            && (self.width.is_some() || self.height.is_some());
        let human_position_write = position_control == GeometryControl::Human
            && (self.position.is_some() || self.anchor.is_some());
        if human_size_write || human_position_write {
            return Err(Fault::new(
                "HUMAN_GEOMETRY",
                "set geometry_control=provider for size or position_control=provider for placement",
            ));
        }
        let mut next = old.clone();
        macro_rules! copy { ($($field:ident),*) => { $(if let Some(v) = &self.$field { next.$field = v.clone(); })* }; }
        copy!(
            title,
            width,
            height,
            always_on_top,
            visible,
            resizable,
            title_bar_visible,
            background_drag_enabled,
            text_selectable,
            decorations,
            skip_taskbar,
            click_through,
            geometry_control,
            surface_opacity
        );
        if let Some(position_control) = self.position_control {
            next.position_control = Some(position_control);
        }
        if let Some(p) = &self.position {
            next.position = Some(p.clone());
        }
        if let Some(anchor) = self.anchor {
            anchor.validate()?;
            next.anchor = Some(anchor);
        }
        next.validate()?;
        Ok(next)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LeaseKey {
    pub id: Uuid,
    pub epoch: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ScopedLeaseKey {
    pub scope_id: Uuid,
    pub lease_id: Uuid,
    pub epoch: u64,
    pub generation: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ScopeDefinition {
    pub root_node_id: String,
    pub data_namespace: String,
}
#[derive(Clone, Debug, Serialize)]
pub struct ScopeGrant {
    pub scope_id: Uuid,
    pub root_node_id: String,
    pub data_namespace: String,
    pub generation: u64,
    pub join_key: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScopeJoinRequest {
    pub world_id: Uuid,
    pub scope_id: Uuid,
    pub generation: u64,
    pub join_key: String,
    pub mode: JoinMode,
}
impl ScopeJoinRequest {
    pub fn from_grant(world_id: Uuid, grant: &ScopeGrant, mode: JoinMode) -> Self {
        Self {
            world_id,
            scope_id: grant.scope_id,
            generation: grant.generation,
            join_key: grant.join_key.clone(),
            mode,
        }
    }
}
#[derive(Clone, Debug, Serialize)]
pub struct ScopePartitionResult {
    pub world_id: Uuid,
    pub world_epoch: u64,
    pub world_revision: u64,
    pub authority_lease: LeaseKey,
    pub scopes: Vec<ScopeGrant>,
}
#[derive(Clone, Debug, Serialize)]
pub struct ScopeSnapshot {
    pub world_id: Uuid,
    pub scope_id: Uuid,
    pub root_node_id: String,
    pub generation: u64,
    pub revision: u64,
    pub sequence: u64,
    pub writer: Option<Uuid>,
    pub status: String,
    pub root: crate::scene::Node,
    pub data: Value,
}
#[derive(Clone, Debug, Serialize)]
pub struct ScopeJoinResult {
    pub snapshot: ScopeSnapshot,
    pub lease: Option<ScopedLeaseKey>,
}
#[derive(Clone, Debug)]
pub struct WriteLease {
    pub key: LeaseKey,
    pub session: Uuid,
    pub expires_at: u64,
}
#[derive(Clone, Debug)]
pub struct Session {
    pub id: Uuid,
    pub name: String,
    pub operator: bool,
    pub protocol: ProtocolVersion,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct NativeReport {
    pub state: String,
    pub applied_window_revision: Option<u64>,
    pub error: Option<String>,
}
impl Default for NativeReport {
    fn default() -> Self {
        Self {
            state: "pending".into(),
            applied_window_revision: None,
            error: None,
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ActionState {
    pub id: Uuid,
    pub component_id: String,
    pub action: String,
    pub status: String,
    pub message: Option<String>,
    #[serde(skip)]
    pub writer: Option<Uuid>,
    #[serde(skip)]
    pub lease_epoch: u64,
    #[serde(skip)]
    pub deadline: u64,
}
#[derive(Clone, Debug)]
pub struct ActionAcknowledgement {
    pub event_id: Uuid,
    pub ok: bool,
    pub message: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UiEvent {
    pub id: Uuid,
    pub world_id: Uuid,
    pub component_id: String,
    pub action: String,
    pub value: Value,
    pub lease_epoch: u64,
    pub revision: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct WorldSummary {
    pub id: Uuid,
    pub title: String,
    pub system: bool,
    pub join_policy: JoinPolicy,
    pub write_blocked: bool,
    pub writer: Option<Uuid>,
    pub writer_name: Option<String>,
    pub status: String,
    pub revision: u64,
    pub visible: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Snapshot {
    pub id: Uuid,
    pub revision: u64,
    pub sequence: u64,
    pub window_revision: u64,
    pub epoch: u64,
    pub system: bool,
    pub write_blocked: bool,
    pub writer: Option<Uuid>,
    pub status: String,
    pub window: WindowSpec,
    pub scene: Scene,
    pub native: NativeReport,
    pub actions: Vec<ActionState>,
}
#[derive(Clone, Debug)]
pub struct World {
    pub id: Uuid,
    pub revision: u64,
    pub sequence: u64,
    pub window_revision: u64,
    pub epoch: u64,
    pub system: bool,
    pub write_blocked: bool,
    pub join_policy: JoinPolicy,
    pub join_key: String,
    pub writer: Option<WriteLease>,
    pub ownership_mode: OwnershipMode,
    pub authority: Option<WorldAuthorityLease>,
    pub scopes: BTreeMap<Uuid, ComponentScope>,
    pub state_slots: BTreeMap<Uuid, crate::state_slots::StateSlot>,
    pub readers: BTreeMap<Uuid, JoinMode>,
    pub ever_claimed: bool,
    pub window: WindowSpec,
    pub scene: Scene,
    pub native: NativeReport,
    pub actions: Vec<ActionState>,
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum OwnershipMode {
    #[default]
    ExclusiveWorld,
    ScopedSubtrees,
}
#[derive(Clone, Debug)]
pub struct WorldAuthorityLease {
    pub key: LeaseKey,
    pub session: Uuid,
    pub expires_at: u64,
}
#[derive(Clone, Debug)]
pub struct ScopedWriteLease {
    pub key: ScopedLeaseKey,
    pub session: Uuid,
    pub expires_at: u64,
}
#[derive(Clone, Debug)]
pub struct ComponentScope {
    pub id: Uuid,
    pub root_node_id: String,
    pub data_namespace: String,
    pub generation: u64,
    pub epoch: u64,
    pub revision: u64,
    pub join_key: String,
    pub writer: Option<ScopedWriteLease>,
    pub readers: BTreeMap<Uuid, JoinMode>,
    pub ever_claimed: bool,
}
impl World {
    pub fn status(&self) -> &str {
        if self.writer.is_some()
            || self.authority.is_some()
            || self.scopes.values().any(|scope| scope.writer.is_some())
        {
            "online"
        } else if self.ever_claimed {
            "stale"
        } else {
            "vacant"
        }
    }
    pub fn touch(&mut self) {
        self.revision += 1;
        self.sequence += 1;
    }
    pub fn snapshot(&self) -> Snapshot {
        Snapshot {
            id: self.id,
            revision: self.revision,
            sequence: self.sequence,
            window_revision: self.window_revision,
            epoch: self.epoch,
            system: self.system,
            write_blocked: self.write_blocked,
            writer: self.writer.as_ref().map(|x| x.session),
            status: self.status().into(),
            window: self.window.clone(),
            scene: self.scene.clone(),
            native: self.native.clone(),
            actions: self.actions.clone(),
        }
    }
}
#[derive(Clone, Debug, Serialize)]
pub struct JoinResult {
    pub world: Snapshot,
    pub lease: Option<LeaseKey>,
}
#[derive(Clone, Debug, Serialize)]
pub struct Created {
    pub world: Snapshot,
    pub lease: Option<LeaseKey>,
    pub join_key: String,
}
