use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::{Read, Seek},
    path::Path,
};
use time::{format_description::well_known::Rfc3339, Duration, OffsetDateTime};
use uuid::Uuid;
use wincraft_core::{Fault, Kind, Node, Scene, ThemeTokens, WindowSpec};
use zip::ZipArchive;

pub(crate) const DRAFT_SCHEMA_VERSION: &str = "draft-2026-10-26";
const MAX_JSON_BYTES: usize = 1_048_576;
const MAX_ARCHIVE_BYTES: u64 = 2 * MAX_JSON_BYTES as u64 + 65_536;
const MAX_PLANS: usize = 16;
const MAX_BATCHES: usize = 32;
const PLAN_LIFETIME_SECONDS: i64 = 60;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ConfigurationPack {
    kind: String,
    schema_version: String,
    pub(crate) id: String,
    pub(crate) version: String,
    title: BTreeMap<String, String>,
    bindings: Vec<Binding>,
    blueprint: String,
    #[serde(default)]
    theme_id: Option<String>,
    fallback_policy: FallbackPolicy,
    #[serde(default)]
    adapter: Option<AdapterReference>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Binding {
    id: String,
    required: bool,
    provider_types: Vec<String>,
    capabilities: Vec<String>,
    permissions: Vec<String>,
    min_adapter_contract: u32,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum FallbackPolicy {
    ExplainMissing,
    HideOptional,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct AdapterReference {
    kind: String,
    id: String,
    reference: String,
    sha256: String,
    execution: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Blueprint {
    kind: String,
    schema_version: String,
    pub(crate) id: String,
    pub(crate) worlds: Vec<BlueprintWorld>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct BlueprintWorld {
    pub(crate) id: String,
    title: BTreeMap<String, String>,
    pub(crate) binding_slots: Vec<String>,
    layout_hint: LayoutHint,
    #[serde(default)]
    window: Option<BlueprintWindow>,
    scene: BlueprintScene,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum LayoutHint {
    Stack,
    Row,
    Compact,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
struct BlueprintWindow {
    width: Option<f64>,
    height: Option<f64>,
    always_on_top: Option<bool>,
    visible: Option<bool>,
    resizable: Option<bool>,
    title_bar_visible: Option<bool>,
    background_drag_enabled: Option<bool>,
    text_selectable: Option<bool>,
    decorations: Option<bool>,
    skip_taskbar: Option<bool>,
    click_through: Option<bool>,
    surface_opacity: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct BlueprintScene {
    root: Node,
    #[serde(default)]
    theme: Option<ThemeTokens>,
}

#[derive(Clone, Debug)]
pub(crate) struct LoadedPack {
    pub(crate) pack: ConfigurationPack,
    pub(crate) blueprint: Blueprint,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum PlanStatus {
    Ready,
    Degraded,
    Blocked,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PlannedBinding {
    pub(crate) binding_id: String,
    pub(crate) required: bool,
    pub(crate) requested_permissions: Vec<String>,
    pub(crate) provider_instance_id: Option<String>,
    pub(crate) provider_name: Option<String>,
    pub(crate) status: String,
    pub(crate) reason: String,
    pub(crate) candidates: Vec<ProviderCandidate>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ProviderCandidate {
    pub(crate) source_id: String,
    pub(crate) instance_id: String,
    pub(crate) display_name: String,
    pub(crate) provider_type: String,
    pub(crate) missing_permissions: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) struct PackPreview {
    pub(crate) kind: &'static str,
    pub(crate) schema_version: &'static str,
    pub(crate) preview_id: Uuid,
    pub(crate) pack_id: String,
    pub(crate) pack_version: String,
    pub(crate) pack_title: String,
    pub(crate) blueprint_id: String,
    pub(crate) inventory_generation: u64,
    pub(crate) input_digest: String,
    pub(crate) created_at: String,
    pub(crate) expires_at: String,
    pub(crate) status: PlanStatus,
    pub(crate) mutates_host: bool,
    pub(crate) requires_confirmation: bool,
    pub(crate) world_count: usize,
    pub(crate) worlds: Vec<BlueprintWorldPreview>,
    pub(crate) bindings: Vec<PlannedBinding>,
    pub(crate) blockers: Vec<String>,
    pub(crate) warnings: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) struct BlueprintWorldPreview {
    pub(crate) blueprint_world_id: String,
    pub(crate) title: String,
    pub(crate) width: f64,
    pub(crate) height: f64,
    pub(crate) always_on_top: bool,
    pub(crate) visible: bool,
    pub(crate) resizable: bool,
    pub(crate) title_bar_visible: bool,
    pub(crate) background_drag_enabled: bool,
    pub(crate) text_selectable: bool,
    pub(crate) click_through: bool,
    pub(crate) surface_opacity: f64,
    pub(crate) binding_slots: Vec<String>,
}

#[derive(Clone, Debug)]
pub(crate) struct PendingPackPlan {
    pub(crate) loaded: LoadedPack,
    pub(crate) preview: PackPreview,
    pub(crate) selections: BTreeMap<String, String>,
    pub(crate) expires_at_mono_ms: u64,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) struct ImportedWorld {
    pub(crate) blueprint_world_id: String,
    pub(crate) world_id: Uuid,
    pub(crate) title: String,
    pub(crate) scene: Scene,
    pub(crate) window: WindowSpec,
    pub(crate) expected_revision: u64,
    pub(crate) expected_epoch: u64,
    pub(crate) expected_writer: Option<Uuid>,
    pub(crate) expected_readers: BTreeSet<Uuid>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) struct ImportReceipt {
    pub(crate) batch_id: Uuid,
    pub(crate) preview_id: Uuid,
    pub(crate) pack_id: String,
    pub(crate) pack_version: String,
    pub(crate) status: String,
    pub(crate) idempotent_replay: bool,
    pub(crate) failure_code: Option<String>,
    pub(crate) cleanup_removed: Vec<Uuid>,
    pub(crate) retained_worlds: Vec<Uuid>,
    pub(crate) bindings: Vec<PlannedBinding>,
    pub(crate) worlds: Vec<ImportedWorldSummary>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) struct ImportedWorldSummary {
    pub(crate) blueprint_world_id: String,
    pub(crate) world_id: Uuid,
    pub(crate) title: String,
}

#[derive(Clone, Debug)]
pub(crate) struct ImportBatch {
    pub(crate) receipt: ImportReceipt,
    pub(crate) expected_worlds: Vec<ImportedWorld>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) struct RollbackReceipt {
    pub(crate) batch_id: Uuid,
    pub(crate) status: String,
    pub(crate) removed: Vec<Uuid>,
    pub(crate) already_missing: Vec<Uuid>,
    pub(crate) retained: Vec<Uuid>,
}

#[derive(Default)]
pub(crate) struct PackImportRegistry {
    pub(crate) plans: BTreeMap<Uuid, PendingPackPlan>,
    pub(crate) batches: BTreeMap<Uuid, ImportBatch>,
    order: Vec<Uuid>,
}

impl PackImportRegistry {
    pub(crate) fn insert_plan(&mut self, plan: PendingPackPlan, now_ms: u64) {
        self.plans
            .retain(|_, current| current.expires_at_mono_ms > now_ms);
        if self.plans.len() >= MAX_PLANS {
            if let Some(oldest) = self
                .plans
                .iter()
                .min_by_key(|(_, plan)| plan.expires_at_mono_ms)
                .map(|(id, _)| *id)
            {
                self.plans.remove(&oldest);
            }
        }
        self.plans.insert(plan.preview.preview_id, plan);
    }

    pub(crate) fn cancel(&mut self, id: Uuid) -> bool {
        self.plans.remove(&id).is_some()
    }

    pub(crate) fn plan(&self, id: Uuid) -> Option<PendingPackPlan> {
        self.plans.get(&id).cloned()
    }

    pub(crate) fn batch(&self, id: Uuid) -> Option<ImportBatch> {
        self.batches.get(&id).cloned()
    }

    pub(crate) fn batch_for_preview(&self, preview_id: Uuid) -> Option<ImportBatch> {
        self.batches
            .values()
            .find(|batch| batch.receipt.preview_id == preview_id)
            .cloned()
    }

    pub(crate) fn record_batch(&mut self, batch: ImportBatch) {
        let id = batch.receipt.batch_id;
        self.order.retain(|existing| *existing != id);
        self.order.push(id);
        self.batches.insert(id, batch);
        while self.order.len() > MAX_BATCHES {
            if let Some(expired) = self.order.first().copied() {
                self.order.remove(0);
                self.batches.remove(&expired);
            }
        }
    }

    pub(crate) fn update_batch(&mut self, batch: ImportBatch) {
        self.batches.insert(batch.receipt.batch_id, batch);
    }

    pub(crate) fn recent_batches(&self) -> Vec<ImportReceipt> {
        self.order
            .iter()
            .rev()
            .filter_map(|id| self.batches.get(id).map(|batch| batch.receipt.clone()))
            .collect()
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InventorySnapshot {
    kind: String,
    schema_version: String,
    endpoint_id: Uuid,
    generation: u64,
    observed_at: String,
    valid_for_seconds: u32,
    providers: Vec<InventoryProvider>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InventoryProvider {
    id: String,
    instance_id: String,
    provider_type: String,
    display_name: String,
    adapter_contract: u32,
    state: String,
    capabilities: Vec<String>,
    grants: Vec<String>,
    source_updated_at: String,
    fresh_for_seconds: u32,
}

pub(crate) fn load_pack_file(path: &Path) -> Result<LoadedPack, Fault> {
    let metadata = fs::symlink_metadata(path).map_err(|_| {
        Fault::new(
            "PACK_FILE_INVALID",
            "configuration pack file is unavailable",
        )
    })?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || path
            .extension()
            .and_then(|value| value.to_str())
            .map(str::to_ascii_lowercase)
            != Some("wcp".into())
        || metadata.len() > MAX_ARCHIVE_BYTES
    {
        return Err(Fault::new(
            "PACK_FILE_INVALID",
            "choose a regular .wcp file within the size limit",
        ));
    }
    let file = File::open(path).map_err(|_| {
        Fault::new(
            "PACK_FILE_INVALID",
            "configuration pack file is unavailable",
        )
    })?;
    load_pack_archive(file)
}

pub(crate) fn load_pack_archive<R: Read + Seek>(reader: R) -> Result<LoadedPack, Fault> {
    let mut archive = ZipArchive::new(reader).map_err(|_| {
        Fault::new(
            "PACK_ARCHIVE_INVALID",
            "configuration pack archive is invalid",
        )
    })?;
    if archive.len() != 2 {
        return Err(Fault::new(
            "PACK_ARCHIVE_INVALID",
            "configuration pack must contain exactly pack.json and its blueprint",
        ));
    }
    let mut entries = BTreeMap::<String, Vec<u8>>::new();
    let mut total = 0usize;
    for index in 0..archive.len() {
        let mut entry = archive.by_index(index).map_err(|_| {
            Fault::new(
                "PACK_ARCHIVE_INVALID",
                "configuration pack entry is invalid",
            )
        })?;
        let name = entry
            .name()
            .map_err(|_| {
                Fault::new(
                    "PACK_ARCHIVE_INVALID",
                    "configuration pack entry name is invalid",
                )
            })?
            .into_owned();
        if entry.is_dir() || !safe_archive_path(&name) || entry.size() > MAX_JSON_BYTES as u64 {
            return Err(Fault::new(
                "PACK_ARCHIVE_INVALID",
                "configuration pack contains an unsafe or oversized entry",
            ));
        }
        if entry
            .unix_mode()
            .is_some_and(|mode| mode & 0o170000 != 0o100000)
        {
            return Err(Fault::new(
                "PACK_ARCHIVE_INVALID",
                "configuration pack entries must be regular files",
            ));
        }
        let declared_size = entry.size() as usize;
        let limit = MAX_JSON_BYTES as u64 + 1;
        let mut bounded = (&mut entry).take(limit);
        let mut bytes = Vec::with_capacity(declared_size);
        bounded.read_to_end(&mut bytes).map_err(|_| {
            Fault::new(
                "PACK_ARCHIVE_INVALID",
                "configuration pack entry could not be read",
            )
        })?;
        if bytes.len() > MAX_JSON_BYTES {
            return Err(Fault::new(
                "PACK_ARCHIVE_INVALID",
                "configuration pack entry is oversized",
            ));
        }
        total = total.saturating_add(bytes.len());
        if total > 2 * MAX_JSON_BYTES {
            return Err(Fault::new(
                "PACK_ARCHIVE_INVALID",
                "configuration pack expands beyond the size limit",
            ));
        }
        if entries.insert(name, bytes).is_some() {
            return Err(Fault::new(
                "PACK_ARCHIVE_INVALID",
                "configuration pack contains duplicate entries",
            ));
        }
    }
    let pack_bytes = entries.remove("pack.json").ok_or_else(|| {
        Fault::new(
            "PACK_ARCHIVE_INVALID",
            "configuration pack manifest is missing",
        )
    })?;
    let pack: ConfigurationPack = serde_json::from_slice(&pack_bytes).map_err(|_| {
        Fault::new(
            "PACK_MANIFEST_INVALID",
            "configuration pack manifest is invalid",
        )
    })?;
    validate_pack(&pack)?;
    let blueprint_path = safe_blueprint_reference(&pack.blueprint)?;
    if entries.len() != 1 || !entries.contains_key(&blueprint_path) {
        return Err(Fault::new(
            "PACK_ARCHIVE_INVALID",
            "configuration pack must contain the single referenced blueprint",
        ));
    }
    let blueprint_bytes = entries
        .remove(&blueprint_path)
        .expect("referenced entry checked above");
    let blueprint: Blueprint = serde_json::from_slice(&blueprint_bytes)
        .map_err(|_| Fault::new("BLUEPRINT_INVALID", "configuration blueprint is invalid"))?;
    validate_blueprint(&pack, &blueprint)?;
    Ok(LoadedPack { pack, blueprint })
}

fn safe_archive_path(value: &str) -> bool {
    !value.is_empty()
        && !value.starts_with('/')
        && !value.contains('\\')
        && !value.contains('\0')
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b'/' | b'-'))
        && !value.starts_with("//")
        && !value
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
        && value.as_bytes().get(1).is_none_or(|byte| *byte != b':')
}

fn safe_blueprint_reference(value: &str) -> Result<String, Fault> {
    if !safe_archive_path(value) || !value.ends_with(".json") || value == "pack.json" {
        return Err(Fault::new(
            "PACK_MANIFEST_INVALID",
            "blueprint path must be a safe relative JSON path",
        ));
    }
    Ok(value.to_owned())
}

pub(crate) fn validate_pack(pack: &ConfigurationPack) -> Result<(), Fault> {
    if pack.kind != "wincraft.pack.draft"
        || pack.schema_version != DRAFT_SCHEMA_VERSION
        || !valid_id(&pack.id)
        || pack.version.trim().is_empty()
        || pack.version.chars().count() > 256
        || pack.title.is_empty()
        || pack.title.len() > 16
        || pack.bindings.is_empty()
        || pack.bindings.len() > 32
    {
        return Err(Fault::new(
            "PACK_MANIFEST_INVALID",
            "configuration pack header is invalid",
        ));
    }
    safe_blueprint_reference(&pack.blueprint)?;
    for (locale, value) in &pack.title {
        if !valid_locale(locale) || value.trim().is_empty() || value.chars().count() > 4096 {
            return Err(Fault::new(
                "PACK_MANIFEST_INVALID",
                "configuration pack title is invalid",
            ));
        }
    }
    if pack
        .theme_id
        .as_deref()
        .is_some_and(|value| !valid_id(value))
    {
        return Err(Fault::new(
            "PACK_MANIFEST_INVALID",
            "configuration pack theme is invalid",
        ));
    }
    let mut ids = BTreeSet::new();
    for binding in &pack.bindings {
        if !valid_id(&binding.id)
            || !ids.insert(binding.id.clone())
            || binding.provider_types.len() > 64
            || binding.capabilities.len() > 64
            || binding.permissions.len() > 64
            || binding.min_adapter_contract == 0
            || binding.min_adapter_contract > 1000
            || !binding
                .capabilities
                .iter()
                .any(|capability| capability == "world.import.accept")
            || !binding
                .capabilities
                .iter()
                .any(|capability| capability == "world.import.accept")
        {
            return Err(Fault::new(
                "PACK_MANIFEST_INVALID",
                "configuration pack binding is invalid",
            ));
        }
        for values in [
            &binding.provider_types,
            &binding.capabilities,
            &binding.permissions,
        ] {
            let mut unique = BTreeSet::new();
            if values
                .iter()
                .any(|value| !valid_id(value) || !unique.insert(value))
            {
                return Err(Fault::new(
                    "PACK_MANIFEST_INVALID",
                    "configuration pack binding values are invalid",
                ));
            }
        }
    }
    if let Some(adapter) = &pack.adapter {
        if adapter.kind != "external-program-reference"
            || !valid_id(&adapter.id)
            || adapter.reference.trim().is_empty()
            || adapter.reference.chars().count() > 256
            || adapter.sha256.len() != 64
            || !adapter
                .sha256
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
            || adapter.execution != "separate-user-approval"
        {
            return Err(Fault::new(
                "PACK_MANIFEST_INVALID",
                "external adapter reference is invalid",
            ));
        }
    }
    Ok(())
}

pub(crate) fn validate_blueprint(
    pack: &ConfigurationPack,
    blueprint: &Blueprint,
) -> Result<(), Fault> {
    if blueprint.kind != "wincraft.blueprint.draft"
        || blueprint.schema_version != DRAFT_SCHEMA_VERSION
        || !valid_id(&blueprint.id)
        || blueprint.worlds.is_empty()
        || blueprint.worlds.len() > 16
    {
        return Err(Fault::new(
            "BLUEPRINT_INVALID",
            "configuration blueprint header is invalid",
        ));
    }
    let binding_ids: BTreeSet<&str> = pack
        .bindings
        .iter()
        .map(|binding| binding.id.as_str())
        .collect();
    let mut world_ids = BTreeSet::new();
    for world in &blueprint.worlds {
        if !valid_id(&world.id)
            || !world_ids.insert(world.id.clone())
            || world.title.is_empty()
            || world.title.len() > 16
            || world.binding_slots.len() > 64
        {
            return Err(Fault::new(
                "BLUEPRINT_INVALID",
                "blueprint world is invalid",
            ));
        }
        for (locale, value) in &world.title {
            if !valid_locale(locale) || value.trim().is_empty() || value.chars().count() > 4096 {
                return Err(Fault::new(
                    "BLUEPRINT_INVALID",
                    "blueprint title is invalid",
                ));
            }
        }
        let mut slots = BTreeSet::new();
        if world
            .binding_slots
            .iter()
            .any(|slot| !binding_ids.contains(slot.as_str()) || !slots.insert(slot))
        {
            return Err(Fault::new(
                "BLUEPRINT_INVALID",
                "blueprint references an unknown or duplicate binding",
            ));
        }
        if matches!(pack.fallback_policy, FallbackPolicy::HideOptional)
            && world.binding_slots.len() > 1
        {
            return Err(Fault::new(
                "BLUEPRINT_INVALID",
                "hide_optional requires one binding slot per world until component-level fallback is declared",
            ));
        }
        for locale in ["zh-CN", "en-US"] {
            world.window_spec(locale)?;
        }
        let scene = world.scene.to_scene()?;
        let required_root = match world.layout_hint {
            LayoutHint::Stack => Some(Kind::Stack),
            LayoutHint::Row => Some(Kind::Row),
            LayoutHint::Compact => None,
        };
        if required_root.is_some_and(|kind| scene.root.kind != kind) {
            return Err(Fault::new(
                "BLUEPRINT_INVALID",
                "blueprint layout hint does not match its declared scene root",
            ));
        }
        scene.validate()?;
    }
    Ok(())
}

impl BlueprintWindow {
    pub(crate) fn to_window(&self, title: String) -> Result<WindowSpec, Fault> {
        let mut window = WindowSpec {
            title,
            ..WindowSpec::default()
        };
        macro_rules! copy { ($($field:ident),* $(,)?) => { $(if let Some(value) = self.$field { window.$field = value; })* }; }
        copy!(
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
            surface_opacity,
        );
        // Positions and ownership modes are device-local and are never imported.
        window.position = None;
        window.anchor = None;
        window.geometry_control = wincraft_core::GeometryControl::Human;
        window.position_control = None;
        window.validate()?;
        Ok(window)
    }
}

impl BlueprintScene {
    fn to_scene(&self) -> Result<Scene, Fault> {
        let scene = Scene {
            root: self.root.clone(),
            data: Value::Null,
            theme: self.theme.clone(),
        };
        scene.validate()?;
        Ok(scene)
    }
}

impl BlueprintWorld {
    pub(crate) fn window_spec(&self, locale: &str) -> Result<WindowSpec, Fault> {
        match &self.window {
            Some(window) => window.to_window(title_for(&self.title, locale)),
            None => Ok(WindowSpec {
                title: title_for(&self.title, locale),
                ..WindowSpec::default()
            }),
        }
    }

    pub(crate) fn scene_spec(&self) -> Result<Scene, Fault> {
        self.scene.to_scene()
    }
}

pub(crate) fn materialize_world(
    loaded: &LoadedPack,
    world: &BlueprintWorld,
    bindings: &[PlannedBinding],
    locale: &str,
) -> Result<(WindowSpec, Scene), Fault> {
    let mut window = world.window_spec(locale)?;
    let mut scene = world.scene_spec()?;
    let unavailable = world
        .binding_slots
        .iter()
        .filter_map(|slot| bindings.iter().find(|binding| binding.binding_id == *slot))
        .filter(|binding| binding.status != "selected")
        .collect::<Vec<_>>();

    if unavailable.is_empty() {
        return Ok((window, scene));
    }
    if matches!(loaded.pack.fallback_policy, FallbackPolicy::HideOptional)
        && unavailable.len() == world.binding_slots.len()
        && unavailable.iter().all(|binding| !binding.required)
    {
        window.visible = false;
        window.validate()?;
        return Ok((window, scene));
    }

    // Draft blueprints describe whole worlds per binding slot. Until they map
    // slots to subtrees, explain missing sources instead of hiding unrelated content.
    if !scene.root.kind.container() {
        return Err(Fault::new(
            "BLUEPRINT_INVALID",
            "fallback explanation requires a stack or row root",
        ));
    }
    for (index, binding) in unavailable.iter().enumerate() {
        let mut suffix = index;
        let id = loop {
            let candidate = format!("wincraft-fallback-{suffix}");
            if scene.root.find(&candidate).is_none() {
                break candidate;
            }
            suffix += 1;
        };
        let label = if locale == "en-US" {
            format!("Optional provider is not connected: {}", binding.binding_id)
        } else {
            format!("可选提供者尚未连接：{}", binding.binding_id)
        };
        scene.root.children.push(Node::new(
            &id,
            Kind::Text,
            json!({"text":label,"tone":"muted","size":"small"}),
            vec![],
        ));
    }
    scene.validate()?;
    Ok((window, scene))
}

pub(crate) fn build_preview(
    loaded: LoadedPack,
    inventory_value: Value,
    selections: BTreeMap<String, String>,
    now: OffsetDateTime,
    now_mono_ms: u64,
) -> Result<PendingPackPlan, Fault> {
    validate_pack(&loaded.pack)?;
    validate_blueprint(&loaded.pack, &loaded.blueprint)?;
    let inventory: InventorySnapshot =
        serde_json::from_value(inventory_value.clone()).map_err(|_| {
            Fault::new(
                "INVENTORY_INVALID",
                "provider inventory snapshot is invalid",
            )
        })?;
    if inventory.kind != "wincraft.inventory.draft"
        || inventory.schema_version != "draft-2026-10-29"
        || inventory.generation == 0
        || inventory.valid_for_seconds == 0
        || inventory.valid_for_seconds > 3600
        || inventory.providers.len() > 128
    {
        return Err(Fault::new(
            "INVENTORY_INVALID",
            "provider inventory header is invalid",
        ));
    }
    let observed = parse_timestamp(&inventory.observed_at)?;
    if observed > now {
        return Err(Fault::new(
            "INVENTORY_INVALID",
            "provider inventory timestamp is in the future",
        ));
    }
    let inventory_expires = observed + Duration::seconds(i64::from(inventory.valid_for_seconds));
    let mut instance_ids = BTreeSet::new();
    for provider in &inventory.providers {
        if !valid_id(&provider.id)
            || !valid_id(&provider.instance_id)
            || !valid_id(&provider.provider_type)
            || provider.display_name.trim().is_empty()
            || provider.display_name.chars().count() > 256
            || provider.adapter_contract == 0
            || !instance_ids.insert(provider.instance_id.clone())
            || !matches!(provider.state.as_str(), "online" | "offline" | "degraded")
        {
            return Err(Fault::new(
                "INVENTORY_INVALID",
                "provider metadata is invalid",
            ));
        }
        let source_updated = parse_timestamp(&provider.source_updated_at)?;
        if source_updated > observed {
            return Err(Fault::new(
                "INVENTORY_INVALID",
                "provider timestamp exceeds inventory timestamp",
            ));
        }
        let mut capabilities = BTreeSet::new();
        let mut grants = BTreeSet::new();
        if provider
            .capabilities
            .iter()
            .any(|item| !valid_id(item) || !capabilities.insert(item))
            || provider
                .grants
                .iter()
                .any(|item| !valid_id(item) || !grants.insert(item))
            || provider
                .grants
                .iter()
                .any(|item| !provider.capabilities.contains(item))
        {
            return Err(Fault::new(
                "INVENTORY_INVALID",
                "provider capability metadata is invalid",
            ));
        }
    }
    let mut expiration = (now + Duration::seconds(PLAN_LIFETIME_SECONDS)).min(inventory_expires);
    let known_bindings: BTreeSet<&str> = loaded
        .pack
        .bindings
        .iter()
        .map(|binding| binding.id.as_str())
        .collect();
    if selections
        .keys()
        .any(|key| !known_bindings.contains(key.as_str()))
    {
        return Err(Fault::new(
            "INVALID_PLAN",
            "provider selection references an unknown binding",
        ));
    }
    let mut blockers = Vec::new();
    let mut warnings = Vec::new();
    if now >= inventory_expires {
        blockers.push("inventory_expired".to_owned());
    }
    if loaded.pack.adapter.is_some() {
        warnings.push("external_adapter_not_executed".to_owned());
    }
    if loaded.pack.theme_id.is_some() {
        warnings.push("theme_reference_not_resolved".to_owned());
    }
    let mut bindings = Vec::with_capacity(loaded.pack.bindings.len());
    for binding in &loaded.pack.bindings {
        let mut eligible = Vec::new();
        let mut permission_candidates = Vec::new();
        for provider in &inventory.providers {
            let source_updated = parse_timestamp(&provider.source_updated_at)?;
            if source_updated > now
                || provider.fresh_for_seconds == 0
                || provider.fresh_for_seconds > 86_400
            {
                return Err(Fault::new(
                    "INVENTORY_INVALID",
                    "provider freshness metadata is invalid",
                ));
            }
            let source_expires =
                source_updated + Duration::seconds(i64::from(provider.fresh_for_seconds));
            if now >= source_expires {
                continue;
            }
            if provider.state != "online"
                || !binding.provider_types.contains(&provider.provider_type)
                || provider.adapter_contract < binding.min_adapter_contract
                || !binding
                    .capabilities
                    .iter()
                    .all(|capability| provider.capabilities.contains(capability))
            {
                continue;
            }
            expiration = expiration.min(source_expires);
            let missing_permissions = binding
                .permissions
                .iter()
                .filter(|permission| !provider.grants.contains(permission))
                .cloned()
                .collect::<Vec<_>>();
            let candidate = ProviderCandidate {
                source_id: provider.id.clone(),
                instance_id: provider.instance_id.clone(),
                display_name: provider.display_name.clone(),
                provider_type: provider.provider_type.clone(),
                missing_permissions: missing_permissions.clone(),
            };
            if missing_permissions.is_empty() {
                eligible.push(candidate);
            } else {
                permission_candidates.push(candidate);
            }
        }
        let explicit = selections.get(&binding.id);
        let mut candidates = eligible.clone();
        candidates.extend(permission_candidates.clone());
        candidates.sort_by(|a, b| {
            (&a.display_name, &a.instance_id).cmp(&(&b.display_name, &b.instance_id))
        });
        let (provider_instance_id, provider_name, status, reason) =
            if let Some(instance_id) = explicit {
                if let Some(provider) = eligible
                    .iter()
                    .find(|provider| &provider.instance_id == instance_id)
                {
                    (
                        Some(provider.instance_id.clone()),
                        Some(provider.display_name.clone()),
                        "selected",
                        "explicit_authorized_selection",
                    )
                } else if permission_candidates
                    .iter()
                    .any(|provider| &provider.instance_id == instance_id)
                {
                    (
                        None,
                        None,
                        if binding.required {
                            "blocked"
                        } else {
                            "missing"
                        },
                        "explicit_selection_requires_permission",
                    )
                } else {
                    (None, None, "blocked", "explicit_selection_not_eligible")
                }
            } else if eligible.len() == 1 {
                (
                    Some(eligible[0].instance_id.clone()),
                    Some(eligible[0].display_name.clone()),
                    "selected",
                    "unique_eligible_provider",
                )
            } else if eligible.len() > 1 {
                (
                    None,
                    None,
                    "ambiguous",
                    "multiple_eligible_providers_need_user_choice",
                )
            } else if !permission_candidates.is_empty() {
                (
                    None,
                    None,
                    if binding.required {
                        "blocked"
                    } else {
                        "missing"
                    },
                    "host_permission_required",
                )
            } else {
                (None, None, "missing", "no_online_fresh_compatible_provider")
            };
        if status == "selected" {
            if let Some(instance_id) = provider_instance_id.as_deref() {
                if let Some(source) = inventory
                    .providers
                    .iter()
                    .find(|source| source.instance_id == instance_id)
                {
                    let source_updated = parse_timestamp(&source.source_updated_at)?;
                    expiration = expiration.min(
                        source_updated + Duration::seconds(i64::from(source.fresh_for_seconds)),
                    );
                }
            }
        } else if binding.required {
            blockers.push(format!("{}:{reason}", binding.id));
        } else {
            warnings.push(format!("{}:{reason}", binding.id));
        }
        bindings.push(PlannedBinding {
            binding_id: binding.id.clone(),
            required: binding.required,
            requested_permissions: binding.permissions.clone(),
            provider_instance_id,
            provider_name,
            status: status.to_owned(),
            reason: reason.to_owned(),
            candidates,
        });
    }
    for world in &loaded.blueprint.worlds {
        let source_ids: BTreeSet<&str> = world
            .binding_slots
            .iter()
            .filter_map(|binding_id| {
                bindings
                    .iter()
                    .find(|binding| binding.binding_id == *binding_id)
            })
            .filter_map(|binding| binding.provider_instance_id.as_deref())
            .collect();
        if source_ids.len() > 1 {
            blockers.push(format!("{}:exclusive_world_writer_conflict", world.id));
        }
    }
    let status = if !blockers.is_empty() {
        PlanStatus::Blocked
    } else if !warnings.is_empty() {
        PlanStatus::Degraded
    } else {
        PlanStatus::Ready
    };
    let created_at = format_timestamp(now)?;
    let expires_at = format_timestamp(expiration.max(now))?;
    let worlds = loaded
        .blueprint
        .worlds
        .iter()
        .map(|world| {
            let (window, _) = materialize_world(&loaded, world, &bindings, "zh-CN")?;
            Ok(BlueprintWorldPreview {
                blueprint_world_id: world.id.clone(),
                title: window.title,
                width: window.width,
                height: window.height,
                always_on_top: window.always_on_top,
                visible: window.visible,
                resizable: window.resizable,
                title_bar_visible: window.title_bar_visible,
                background_drag_enabled: window.background_drag_enabled,
                text_selectable: window.text_selectable,
                click_through: window.click_through,
                surface_opacity: window.surface_opacity,
                binding_slots: world.binding_slots.clone(),
            })
        })
        .collect::<Result<Vec<_>, Fault>>()?;
    let digest_input = json!({
        "pack": &loaded.pack,
        "blueprint": &loaded.blueprint,
        "inventory": &inventory_value,
        "selections": &selections,
        "endpoint_id": inventory.endpoint_id,
    });
    let digest = Sha256::digest(
        serde_json::to_vec(&digest_input)
            .map_err(|_| Fault::new("INTERNAL", "plan serialization failed"))?,
    );
    let preview = PackPreview {
        kind: "wincraft.plan.draft",
        schema_version: DRAFT_SCHEMA_VERSION,
        preview_id: Uuid::new_v4(),
        pack_id: loaded.pack.id.clone(),
        pack_version: loaded.pack.version.clone(),
        pack_title: title_for(&loaded.pack.title, "zh-CN"),
        blueprint_id: loaded.blueprint.id.clone(),
        inventory_generation: inventory.generation,
        input_digest: format!("{digest:x}"),
        created_at,
        expires_at,
        status,
        mutates_host: false,
        requires_confirmation: true,
        world_count: loaded.blueprint.worlds.len(),
        worlds,
        bindings,
        blockers,
        warnings,
    };
    let remaining_ms = (expiration - now).whole_milliseconds().max(0) as u64;
    Ok(PendingPackPlan {
        loaded,
        preview,
        selections,
        expires_at_mono_ms: now_mono_ms.saturating_add(remaining_ms),
    })
}

#[cfg(test)]
pub(crate) fn parse_loaded_json(pack: Value, blueprint: Value) -> Result<LoadedPack, Fault> {
    let pack: ConfigurationPack = serde_json::from_value(pack).map_err(|_| {
        Fault::new(
            "PACK_MANIFEST_INVALID",
            "configuration pack manifest is invalid",
        )
    })?;
    let blueprint: Blueprint = serde_json::from_value(blueprint)
        .map_err(|_| Fault::new("BLUEPRINT_INVALID", "configuration blueprint is invalid"))?;
    validate_pack(&pack)?;
    validate_blueprint(&pack, &blueprint)?;
    let total = serde_json::to_vec(&pack)
        .map_err(|_| {
            Fault::new(
                "PACK_MANIFEST_INVALID",
                "configuration pack manifest is invalid",
            )
        })?
        .len()
        + serde_json::to_vec(&blueprint)
            .map_err(|_| Fault::new("BLUEPRINT_INVALID", "configuration blueprint is invalid"))?
            .len();
    if total > 2 * MAX_JSON_BYTES {
        return Err(Fault::new(
            "PACK_ARCHIVE_INVALID",
            "configuration pack contents exceed the size limit",
        ));
    }
    Ok(LoadedPack { pack, blueprint })
}

fn title_for(localized: &BTreeMap<String, String>, locale: &str) -> String {
    localized
        .get(locale)
        .or_else(|| localized.get("zh-CN"))
        .or_else(|| localized.values().next())
        .cloned()
        .unwrap_or_else(|| "WinCraft world".into())
}

fn valid_locale(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 32
        && value
            .split('-')
            .all(|part| !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_alphanumeric()))
        && value.as_bytes()[0].is_ascii_lowercase()
}

fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 96
        && value.as_bytes()[0].is_ascii_alphanumeric()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b':' | b'-'))
}

fn parse_timestamp(value: &str) -> Result<OffsetDateTime, Fault> {
    OffsetDateTime::parse(value, &Rfc3339)
        .map(|timestamp| timestamp.to_offset(time::UtcOffset::UTC))
        .map_err(|_| Fault::new("INVENTORY_INVALID", "inventory timestamp is invalid"))
}

fn format_timestamp(value: OffsetDateTime) -> Result<String, Fault> {
    value
        .to_offset(time::UtcOffset::UTC)
        .format(&Rfc3339)
        .map_err(|_| Fault::new("INTERNAL", "could not format configuration plan timestamp"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Cursor, Write};
    use zip::write::SimpleFileOptions;

    fn pack_json() -> Value {
        json!({
            "kind":"wincraft.pack.draft",
            "schema_version":DRAFT_SCHEMA_VERSION,
            "id":"fixture.pack",
            "version":"1.0.0",
            "title":{"zh-CN":"配置包","en-US":"Configuration pack"},
            "bindings":[{
                "id":"agents",
                "required":true,
                "provider_types":["agent-board"],
                "capabilities":["activity.read","world.import.accept"],
                "permissions":[],
                "min_adapter_contract":1
            }],
            "blueprint":"blueprint.json",
            "theme_id":null,
            "fallback_policy":"explain_missing",
            "adapter":null
        })
    }

    fn blueprint_json() -> Value {
        json!({
            "kind":"wincraft.blueprint.draft",
            "schema_version":DRAFT_SCHEMA_VERSION,
            "id":"fixture.blueprint",
            "worlds":[{
                "id":"agents",
                "title":{"zh-CN":"Agent 活动","en-US":"Agent activity"},
                "binding_slots":["agents"],
                "layout_hint":"stack",
                "window":{"width":480,"height":360,"click_through":false},
                "scene":{"root":{"id":"root","kind":"stack","props":{"gap":12},"children":[
                    {"id":"title","kind":"text","props":{"text":"Agent activity","size":"title"}}
                ]}}
            }]
        })
    }

    fn inventory(providers: Value) -> Value {
        json!({
            "kind":"wincraft.inventory.draft",
            "schema_version":"draft-2026-10-29",
            "endpoint_id":"00000000-0000-4000-8000-000000000001",
            "generation":4,
            "observed_at":"2026-10-30T12:00:00Z",
            "valid_for_seconds":60,
            "providers":providers
        })
    }

    fn provider(instance: &str, grants: &[&str], state: &str, display_name: &str) -> Value {
        json!({
            "id":"source.agents",
            "instance_id":instance,
            "provider_type":"agent-board",
            "display_name":display_name,
            "adapter_contract":1,
            "state":state,
            "capabilities":["activity.read","world.import.accept"],
            "grants":grants,
            "source_updated_at":"2026-10-30T12:00:00Z",
            "fresh_for_seconds":45
        })
    }

    fn archive(entries: &[(&str, Vec<u8>)]) -> Vec<u8> {
        let cursor = Cursor::new(Vec::new());
        let mut writer = zip::ZipWriter::new(cursor);
        let options =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, bytes) in entries {
            writer.start_file(*name, options).expect("zip entry starts");
            writer.write_all(bytes).expect("zip entry writes");
        }
        writer.finish().expect("zip archive finishes").into_inner()
    }

    fn valid_archive() -> Vec<u8> {
        let pack = serde_json::to_vec(&pack_json()).expect("pack serializes");
        let blueprint = serde_json::to_vec(&blueprint_json()).expect("blueprint serializes");
        archive(&[("pack.json", pack), ("blueprint.json", blueprint)])
    }

    #[test]
    fn package_archive_loads_only_manifest_and_declared_blueprint() {
        let bytes = valid_archive();
        let loaded = load_pack_archive(Cursor::new(bytes)).expect("valid package loads");
        assert_eq!(loaded.pack.id, "fixture.pack");
        assert_eq!(loaded.blueprint.worlds.len(), 1);
        let window = loaded.blueprint.worlds[0]
            .window_spec("en-US")
            .expect("window is materialized");
        assert_eq!(window.title, "Agent activity");
        assert_eq!(window.position, None);
        assert_eq!(window.anchor, None);
        assert_eq!(
            window.geometry_control,
            wincraft_core::GeometryControl::Human
        );
    }

    #[test]
    fn archive_rejects_extra_files_and_unsafe_blueprint_paths() {
        let pack = serde_json::to_vec(&pack_json()).expect("pack serializes");
        let blueprint = serde_json::to_vec(&blueprint_json()).expect("blueprint serializes");
        let extra = archive(&[
            ("pack.json", pack.clone()),
            ("blueprint.json", blueprint.clone()),
            ("adapter.exe", vec![0, 1, 2]),
        ]);
        assert_eq!(
            load_pack_archive(Cursor::new(extra)).unwrap_err().code,
            "PACK_ARCHIVE_INVALID"
        );

        let mut unsafe_pack = pack_json();
        unsafe_pack["blueprint"] = json!("../outside.json");
        let invalid = archive(&[
            ("pack.json", serde_json::to_vec(&unsafe_pack).unwrap()),
            ("../outside.json", blueprint),
        ]);
        assert_eq!(
            load_pack_archive(Cursor::new(invalid)).unwrap_err().code,
            "PACK_ARCHIVE_INVALID"
        );
    }

    #[test]
    fn blueprint_cannot_import_business_data_or_device_geometry() {
        let mut blueprint = blueprint_json();
        blueprint["worlds"][0]["scene"]["data"] = json!({"private_note":"fixture"});
        assert_eq!(
            parse_loaded_json(pack_json(), blueprint).unwrap_err().code,
            "BLUEPRINT_INVALID"
        );

        let mut blueprint = blueprint_json();
        blueprint["worlds"][0]["window"]["position"] = json!({"x":100,"y":200});
        assert_eq!(
            parse_loaded_json(pack_json(), blueprint).unwrap_err().code,
            "BLUEPRINT_INVALID"
        );
    }

    #[test]
    fn pack_binding_requires_the_provider_import_capability() {
        let mut pack = pack_json();
        pack["bindings"][0]["capabilities"] = json!(["activity.read"]);
        assert_eq!(
            parse_loaded_json(pack, blueprint_json()).unwrap_err().code,
            "PACK_MANIFEST_INVALID"
        );
    }

    #[test]
    fn optional_missing_provider_degrades_but_required_missing_blocks() {
        let loaded = parse_loaded_json(pack_json(), blueprint_json()).unwrap();
        let now = OffsetDateTime::parse("2026-10-30T12:00:10Z", &Rfc3339).unwrap();
        let optional_missing = {
            let mut loaded = loaded.clone();
            loaded.pack.bindings[0].required = false;
            loaded
        };
        let preview = build_preview(
            optional_missing,
            inventory(json!([])),
            BTreeMap::new(),
            now,
            1000,
        )
        .unwrap();
        assert_eq!(preview.preview.status, PlanStatus::Degraded);
        assert!(preview.preview.blockers.is_empty());
        let (window, scene) = materialize_world(
            &preview.loaded,
            &preview.loaded.blueprint.worlds[0],
            &preview.preview.bindings,
            "zh-CN",
        )
        .unwrap();
        assert!(window.visible);
        assert!(scene.root.find("wincraft-fallback-0").is_some());

        let required =
            build_preview(loaded, inventory(json!([])), BTreeMap::new(), now, 1000).unwrap();
        assert_eq!(required.preview.status, PlanStatus::Blocked);
        assert!(!required.preview.blockers.is_empty());
    }

    #[test]
    fn missing_host_grant_is_shown_and_never_auto_applied() {
        let loaded = parse_loaded_json(pack_json(), blueprint_json()).unwrap();
        let now = OffsetDateTime::parse("2026-10-30T12:00:10Z", &Rfc3339).unwrap();
        let mut pack = loaded.pack.clone();
        pack.bindings[0].permissions = vec!["activity.read".into()];
        let loaded = LoadedPack {
            pack,
            blueprint: loaded.blueprint,
        };
        let preview = build_preview(
            loaded,
            inventory(json!([provider(
                "instance-a",
                &[],
                "online",
                "Agent board"
            )])),
            BTreeMap::new(),
            now,
            1000,
        )
        .unwrap();
        assert_eq!(preview.preview.status, PlanStatus::Blocked);
        assert_eq!(
            preview.preview.bindings[0].candidates[0].missing_permissions,
            vec!["activity.read"]
        );
    }

    #[test]
    fn provider_without_import_event_claim_is_not_a_candidate() {
        let loaded = parse_loaded_json(pack_json(), blueprint_json()).unwrap();
        let now = OffsetDateTime::parse("2026-10-30T12:00:10Z", &Rfc3339).unwrap();
        let mut source = provider("instance-a", &[], "online", "Agent board");
        source["capabilities"] = json!(["activity.read"]);
        let plan = build_preview(
            loaded,
            inventory(json!([source])),
            BTreeMap::new(),
            now,
            1000,
        )
        .unwrap();
        assert_eq!(plan.preview.status, PlanStatus::Blocked);
        assert!(plan.preview.bindings[0].candidates.is_empty());
    }

    #[test]
    fn hide_optional_hides_only_a_world_whose_single_optional_slot_is_missing() {
        let mut pack = pack_json();
        pack["fallback_policy"] = json!("hide_optional");
        let mut loaded = parse_loaded_json(pack, blueprint_json()).unwrap();
        loaded.pack.bindings[0].required = false;
        let now = OffsetDateTime::parse("2026-10-30T12:00:10Z", &Rfc3339).unwrap();
        let plan = build_preview(loaded, inventory(json!([])), BTreeMap::new(), now, 1000).unwrap();
        let world_preview = &plan.preview.worlds[0];
        assert!(!world_preview.visible);
        let (window, scene) = materialize_world(
            &plan.loaded,
            &plan.loaded.blueprint.worlds[0],
            &plan.preview.bindings,
            "zh-CN",
        )
        .unwrap();
        assert!(!window.visible);
        assert!(scene.root.find("wincraft-fallback-0").is_none());
    }

    #[test]
    fn ambiguous_sources_require_selection_and_multiple_writers_in_one_world_block() {
        let loaded = parse_loaded_json(pack_json(), blueprint_json()).unwrap();
        let now = OffsetDateTime::parse("2026-10-30T12:00:10Z", &Rfc3339).unwrap();
        let ambiguous = build_preview(
            loaded.clone(),
            inventory(json!([
                provider("instance-a", &[], "online", "Agent board"),
                provider("instance-b", &[], "online", "Agent board")
            ])),
            BTreeMap::new(),
            now,
            1000,
        )
        .unwrap();
        assert_eq!(ambiguous.preview.status, PlanStatus::Blocked);
        assert_eq!(ambiguous.preview.bindings[0].status, "ambiguous");

        let mut pack = loaded.pack.clone();
        pack.bindings[0].id = "agents-2".into();
        pack.bindings.push(Binding {
            id: "metrics".into(),
            required: true,
            provider_types: vec!["agent-board".into()],
            capabilities: vec!["activity.read".into(), "world.import.accept".into()],
            permissions: vec![],
            min_adapter_contract: 1,
        });
        let mut blueprint = loaded.blueprint.clone();
        blueprint.worlds[0].binding_slots = vec!["agents-2".into(), "metrics".into()];
        let conflict = build_preview(
            LoadedPack { pack, blueprint },
            inventory(json!([
                provider("instance-a", &[], "online", "Agent board"),
                provider("instance-b", &[], "online", "Agent board")
            ])),
            BTreeMap::from([
                ("agents-2".into(), "instance-a".into()),
                ("metrics".into(), "instance-b".into()),
            ]),
            now,
            1000,
        )
        .unwrap();
        assert!(conflict
            .preview
            .blockers
            .iter()
            .any(|item| item.contains("exclusive_world_writer_conflict")));
    }
}
