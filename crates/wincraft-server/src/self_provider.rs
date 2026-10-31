//! A local provider that builds the manager/settings world using the SAME scene
//! vocabulary and exclusive-writer engine as external providers. Only explicit
//! operator actions (rescue/destroy) have extra authority.
use crate::{
    pack_import::{ImportReceipt, PackPreview, PlanStatus, RollbackReceipt},
    provider_package::{
        install_provider_bundle_file, preview_provider_bundle_file, InstalledProviderBundle,
        ProviderBundlePreview,
    },
};
use crate::{Hub, Notice};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    sync::{Arc, OnceLock},
    time::Duration,
};
use uuid::Uuid;
use wincraft_core::*;

#[derive(Clone)]
pub struct ManagerProvider {
    pub session: Uuid,
    pub world_id: Uuid,
    pub lease: LeaseKey,
}

/// The manager supplies the local user-confirmation boundary; the desktop host
/// performs the OS registration through this narrow adapter.
pub trait ShortcutHost: Send + Sync {
    fn register(&self, spec: &ShortcutSpec) -> std::result::Result<(), String>;
    fn unregister(&self, chord: &str) -> std::result::Result<(), String>;
}

/// The desktop host is the only component allowed to launch installed Provider
/// code. The manager calls this only after the user confirms the launch dialog.
pub trait ProviderBundleLauncher: Send + Sync {
    fn launch(
        &self,
        bundle: &InstalledProviderBundle,
        runtime_descriptor: &Path,
    ) -> std::result::Result<(), String>;
}

#[derive(Clone)]
struct Settings {
    title: String,
    always_on_top: bool,
    shortcut_draft: String,
    shortcut_active: Option<String>,
    shortcut_notice: Option<String>,
    shortcut_available: bool,
    pending_close: Option<Uuid>,
    pack_path: String,
    pack_selections: BTreeMap<String, String>,
    pack_preview: Option<PackPreview>,
    pack_notice: Option<String>,
    pending_rollback: Option<Uuid>,
    provider_bundle_preview: Option<ProviderBundlePreview>,
    installed_provider_bundle: Option<InstalledProviderBundle>,
    provider_bundle_notice: Option<String>,
    pending_provider_launch: bool,
    provider_store: PathBuf,
    provider_launcher_available: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            title: "空白世界".into(),
            always_on_top: true,
            shortcut_draft: String::new(),
            shortcut_active: None,
            shortcut_notice: None,
            shortcut_available: false,
            pending_close: None,
            pack_path: String::new(),
            pack_selections: BTreeMap::new(),
            pack_preview: None,
            pack_notice: None,
            pending_rollback: None,
            provider_bundle_preview: None,
            installed_provider_bundle: None,
            provider_bundle_notice: None,
            pending_provider_launch: false,
            provider_store: PathBuf::new(),
            provider_launcher_available: false,
        }
    }
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
        self.spawn_inner(hub, descriptor_path, None, None, PathBuf::new());
    }
    pub fn spawn_with_shortcut_host(
        &self,
        hub: Hub,
        descriptor_path: String,
        shortcut_host: Arc<dyn ShortcutHost>,
    ) {
        self.spawn_inner(
            hub,
            descriptor_path,
            Some(shortcut_host),
            None,
            PathBuf::new(),
        );
    }
    pub fn spawn_with_desktop_hosts(
        &self,
        hub: Hub,
        descriptor_path: String,
        shortcut_host: Arc<dyn ShortcutHost>,
        provider_launcher: Arc<dyn ProviderBundleLauncher>,
        provider_store: PathBuf,
    ) {
        self.spawn_inner(
            hub,
            descriptor_path,
            Some(shortcut_host),
            Some(provider_launcher),
            provider_store,
        );
    }
    fn spawn_inner(
        &self,
        hub: Hub,
        descriptor_path: String,
        shortcut_host: Option<Arc<dyn ShortcutHost>>,
        provider_launcher: Option<Arc<dyn ProviderBundleLauncher>>,
        provider_store: PathBuf,
    ) {
        let manager = self.clone();
        tokio::spawn(async move {
            let mut settings = Settings {
                title: manager_text(&hub.locale(), "manager.default_world"),
                shortcut_available: shortcut_host.is_some(),
                provider_launcher_available: provider_launcher.is_some(),
                provider_store,
                ..Settings::default()
            };
            let mut events = hub.subscribe();
            let mut timer = tokio::time::interval(Duration::from_millis(750));
            loop {
                tokio::select! {
                    _=timer.tick()=>{
                        let _=hub.dispatch(manager.session,"session.ping",json!({}));
                        if let Some(chord)=settings.shortcut_active.clone().filter(|chord|!hub.shortcut_registered(chord)){
                            match shortcut_host.as_deref().map(|host|host.unregister(&chord)){
                                Some(Err(error))=>{
                                    eprintln!("manager shortcut revocation cleanup failed: {error}");
                                    settings.shortcut_notice=Some(manager_text(&hub.locale(),"manager.shortcut.revocation_failed"));
                                }
                                Some(Ok(()))|None=>{
                                    settings.shortcut_active=None;
                                    settings.shortcut_notice=Some(manager_text(&hub.locale(),"manager.shortcut.revoked"));
                                }
                            }
                        }
                        if let Err(e)=manager.refresh(&hub,&settings,&descriptor_path){eprintln!("manager refresh: {e}");}
                    },
                    event=events.recv()=>{
                        match event{
                            Ok(Notice::Directed(sid,value)) if sid==manager.session=>{
                                if let Some(data)=value.get("data"){
                                    if let Ok(event)=serde_json::from_value::<UiEvent>(data.clone()){
                                        let result=manager.handle_with_hosts(&hub,&mut settings,&event,shortcut_host.as_deref(),provider_launcher.as_deref(),Path::new(&descriptor_path));
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
            if let Some(chord) = settings.shortcut_active.take() {
                if let Some(host) = shortcut_host.as_deref() {
                    if let Err(error) = host.unregister(&chord) {
                        eprintln!("manager shortcut shutdown cleanup failed: {error}");
                    }
                }
                if let Err(error) = hub.unregister_shortcut(manager.session, &chord) {
                    eprintln!("manager shortcut intent cleanup failed: {}", error.code);
                }
            }
        });
    }
    #[cfg(test)]
    fn handle(&self, hub: &Hub, s: &mut Settings, event: &UiEvent) -> Result<()> {
        self.handle_with_shortcut_host(hub, s, event, None)
    }
    #[cfg(test)]
    fn handle_with_shortcut_host(
        &self,
        hub: &Hub,
        s: &mut Settings,
        event: &UiEvent,
        shortcut_host: Option<&dyn ShortcutHost>,
    ) -> Result<()> {
        self.handle_with_hosts(hub, s, event, shortcut_host, None, Path::new(""))
    }
    fn handle_with_hosts(
        &self,
        hub: &Hub,
        s: &mut Settings,
        event: &UiEvent,
        shortcut_host: Option<&dyn ShortcutHost>,
        provider_launcher: Option<&dyn ProviderBundleLauncher>,
        runtime_descriptor: &Path,
    ) -> Result<()> {
        match event.action.as_str() {
            "new_world" => {
                hub.dispatch(self.session,"world.create",json!({"window":{"title":s.title,"always_on_top":s.always_on_top},"join_policy":"open_authenticated","claim":false}))?;
            }
            "refresh" => {}
            "manager.descriptor.copy" => {}
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
            "shortcut.draft" => {
                s.shortcut_draft = event
                    .value
                    .as_str()
                    .unwrap_or_default()
                    .trim()
                    .chars()
                    .take(64)
                    .collect();
                s.shortcut_notice = None;
            }
            "shortcut.enable" => {
                if s.shortcut_active.is_some() {
                    return Err(Fault::new(
                        "SHORTCUT_ALREADY_ENABLED",
                        "disable the current shortcut before changing it",
                    ));
                }
                let host = shortcut_host.ok_or_else(|| {
                    Fault::new(
                        "NATIVE_UNAVAILABLE",
                        "global shortcuts require the local desktop host",
                    )
                })?;
                let requested = ShortcutSpec {
                    chord: s.shortcut_draft.clone(),
                    action: "manager.show".into(),
                };
                let chord = hub.register_shortcut(self.session, requested.clone())?;
                let normalized = ShortcutSpec {
                    chord: chord.clone(),
                    action: requested.action,
                };
                if let Err(error) = host.register(&normalized) {
                    let _ = hub.unregister_shortcut(self.session, &chord);
                    return Err(Fault::new("SHORTCUT_REGISTRATION_FAILED", error));
                }
                s.shortcut_draft = chord.clone();
                s.shortcut_active = Some(chord);
                s.shortcut_notice = Some(manager_text(&hub.locale(), "manager.shortcut.enabled"));
            }
            "shortcut.disable" => {
                let Some(chord) = s.shortcut_active.clone() else {
                    s.shortcut_notice =
                        Some(manager_text(&hub.locale(), "manager.shortcut.disabled"));
                    return Ok(());
                };
                let host = shortcut_host.ok_or_else(|| {
                    Fault::new(
                        "NATIVE_UNAVAILABLE",
                        "global shortcuts require the local desktop host",
                    )
                })?;
                host.unregister(&chord)
                    .map_err(|error| Fault::new("SHORTCUT_UNREGISTER_FAILED", error))?;
                hub.unregister_shortcut(self.session, &chord)?;
                s.shortcut_active = None;
                s.shortcut_notice = Some(manager_text(&hub.locale(), "manager.shortcut.disabled"));
            }
            "pack.path" => {
                s.pack_path = event
                    .value
                    .as_str()
                    .unwrap_or_default()
                    .trim()
                    .chars()
                    .take(1024)
                    .collect();
                s.pack_notice = None;
                s.provider_bundle_preview = None;
                s.installed_provider_bundle = None;
                s.provider_bundle_notice = None;
                s.pending_provider_launch = false;
            }
            "pack.preview" => {
                let path = PathBuf::from(s.pack_path.trim());
                match preview_provider_bundle_file(&path) {
                    Ok(preview) => {
                        s.pack_preview = None;
                        s.provider_bundle_preview = Some(preview);
                        s.installed_provider_bundle = None;
                        s.provider_bundle_notice = None;
                        s.pending_provider_launch = false;
                    }
                    Err(provider_error) => {
                        match hub.preview_pack_file(self.session, &path, s.pack_selections.clone())
                        {
                            Ok(preview) => {
                                s.pack_preview = Some(preview);
                                s.provider_bundle_preview = None;
                                s.installed_provider_bundle = None;
                                s.provider_bundle_notice = None;
                                s.pending_provider_launch = false;
                            }
                            Err(_) => return Err(provider_error),
                        }
                    }
                }
                s.pack_notice = None;
                s.pending_rollback = None;
            }
            "pack.cancel" => {
                if let Some(preview) = &s.pack_preview {
                    hub.cancel_pack_preview(self.session, preview.preview_id)?;
                }
                s.pack_preview = None;
                s.provider_bundle_preview = None;
                s.installed_provider_bundle = None;
                s.pending_provider_launch = false;
                s.pack_notice = Some(manager_text(&hub.locale(), "manager.import.cancelled"));
            }
            "provider.bundle.install" => {
                let preview = s.provider_bundle_preview.as_ref().ok_or_else(|| {
                    Fault::new(
                        "PROVIDER_PACKAGE_NOT_PREVIEWED",
                        "preview the Provider package first",
                    )
                })?;
                if s.provider_store.as_os_str().is_empty() {
                    return Err(Fault::new(
                        "PROVIDER_PACKAGE_STORE_UNAVAILABLE",
                        "the local Provider package store is unavailable",
                    ));
                }
                let installed = install_provider_bundle_file(
                    Path::new(s.pack_path.trim()),
                    &s.provider_store,
                    &preview.sha256,
                )?;
                s.installed_provider_bundle = Some(installed);
                s.pending_provider_launch = false;
                s.provider_bundle_notice = Some(manager_text(
                    &hub.locale(),
                    "manager.provider_bundle.installed",
                ));
            }
            "provider.bundle.launch.request" => {
                if s.installed_provider_bundle.is_none() || !s.provider_launcher_available {
                    return Err(Fault::new(
                        "PROVIDER_LAUNCH_UNAVAILABLE",
                        "install a reviewed Provider package in the desktop host first",
                    ));
                }
                s.pending_provider_launch = true;
                s.provider_bundle_notice = None;
            }
            "provider.bundle.launch.cancel" => {
                s.pending_provider_launch = false;
            }
            "provider.bundle.launch.confirm" => {
                if !s.pending_provider_launch {
                    return Err(Fault::new(
                        "PROVIDER_LAUNCH_CONFIRMATION_REQUIRED",
                        "review and confirm Provider code execution first",
                    ));
                }
                let bundle = s.installed_provider_bundle.as_ref().ok_or_else(|| {
                    Fault::new(
                        "PROVIDER_PACKAGE_NOT_INSTALLED",
                        "install the Provider package first",
                    )
                })?;
                let launcher = provider_launcher.ok_or_else(|| {
                    Fault::new(
                        "PROVIDER_LAUNCH_UNAVAILABLE",
                        "desktop Provider launcher is unavailable",
                    )
                })?;
                launcher
                    .launch(bundle, runtime_descriptor)
                    .map_err(|error| Fault::new("PROVIDER_LAUNCH_FAILED", error))?;
                s.pending_provider_launch = false;
                s.provider_bundle_notice = Some(manager_text(
                    &hub.locale(),
                    "manager.provider_bundle.started",
                ));
            }
            a if a.starts_with("pack.select:") => {
                let (preview_id, binding_id, instance_id) = parse_pack_choice(a, "pack.select:")?;
                if s.pack_preview.as_ref().map(|preview| preview.preview_id) != Some(preview_id) {
                    return Err(Fault::new(
                        "STALE_PLAN",
                        "review the current provider inventory again",
                    ));
                }
                s.pack_selections.insert(binding_id, instance_id);
                let preview = hub.preview_pack_file(
                    self.session,
                    PathBuf::from(s.pack_path.trim()).as_path(),
                    s.pack_selections.clone(),
                )?;
                s.pack_preview = Some(preview);
                s.pack_notice = Some(manager_text(&hub.locale(), "manager.import.replanned"));
            }
            a if a.starts_with("pack.grant:") => {
                let (preview_id, binding_id, instance_id) = parse_pack_choice(a, "pack.grant:")?;
                if s.pack_preview.as_ref().map(|preview| preview.preview_id) != Some(preview_id) {
                    return Err(Fault::new(
                        "STALE_PLAN",
                        "review the current provider inventory again",
                    ));
                }
                if let Err(error) =
                    hub.authorize_pack_binding(self.session, preview_id, &binding_id, &instance_id)
                {
                    if matches!(error.code.as_str(), "STALE_PLAN" | "PLAN_NOT_FOUND") {
                        s.pack_preview = None;
                        s.pack_notice = Some(manager_text(&hub.locale(), "manager.import.stale"));
                    }
                    return Err(error);
                }
                // Permission approval changes the inventory generation. Generate a new preview
                // immediately so no stale plan can be submitted.
                let preview = hub.preview_pack_file(
                    self.session,
                    PathBuf::from(s.pack_path.trim()).as_path(),
                    s.pack_selections.clone(),
                )?;
                s.pack_preview = Some(preview);
                s.pack_notice = Some(manager_text(
                    &hub.locale(),
                    "manager.import.permission_granted",
                ));
            }
            a if a.starts_with("pack.apply:") => {
                let preview_id = parse_id(a, "pack.apply:")?;
                if s.pack_preview.as_ref().map(|preview| preview.preview_id) != Some(preview_id) {
                    return Err(Fault::new(
                        "STALE_PLAN",
                        "review the current provider inventory again",
                    ));
                }
                match hub.apply_pack_preview(self.session, preview_id, true) {
                    Ok(receipt) => {
                        s.pack_preview = None;
                        s.pack_notice = Some(import_receipt_text(hub, &receipt));
                    }
                    Err(error) if error.code == "STALE_PLAN" => {
                        s.pack_preview = None;
                        s.pack_notice = Some(manager_text(&hub.locale(), "manager.import.stale"));
                    }
                    Err(error) => return Err(error),
                }
            }
            a if a.starts_with("pack.rollback.request:") => {
                s.pending_rollback = Some(parse_id(a, "pack.rollback.request:")?);
            }
            a if a.starts_with("pack.rollback.cancel:") => {
                let id = parse_id(a, "pack.rollback.cancel:")?;
                if s.pending_rollback == Some(id) {
                    s.pending_rollback = None;
                }
            }
            a if a.starts_with("pack.rollback.confirm:") => {
                let id = parse_id(a, "pack.rollback.confirm:")?;
                if s.pending_rollback != Some(id) {
                    return Err(Fault::new(
                        "FORBIDDEN",
                        "confirm the selected configuration rollback first",
                    ));
                }
                let result = hub.rollback_pack_import(self.session, id)?;
                s.pending_rollback = None;
                s.pack_notice = Some(rollback_receipt_text(hub, &result));
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
    fn pack_controls(&self, hub: &Hub, settings: &Settings, locale: &str) -> Result<Node> {
        let mut controls = vec![
            node(
                "pack-title",
                Kind::Text,
                json!({"text":manager_text(locale,"manager.import.title"),"size":"heading"}),
                vec![],
            ),
            node(
                "pack-explainer",
                Kind::Text,
                json!({"text":manager_text(locale,"manager.import.explainer"),"tone":"muted"}),
                vec![],
            ),
            node(
                "pack-path",
                Kind::Input,
                json!({"label":manager_text(locale,"manager.import.path"),"value":settings.pack_path,
                    "placeholder":manager_text(locale,"manager.import.path_placeholder"),"action":"pack.path"}),
                vec![],
            ),
            node(
                "pack-preview-action",
                Kind::Button,
                json!({"label":manager_text(locale,"manager.import.preview"),"action":"pack.preview","tone":"accent"}),
                vec![],
            ),
        ];

        if let Some(preview) = &settings.provider_bundle_preview {
            controls.push(node(
                "provider-bundle-heading",
                Kind::Text,
                json!({"text":format!("{} · {} · {}",preview.title,preview.id,preview.version),"size":"heading"}),
                vec![],
            ));
            controls.push(node(
                "provider-bundle-warning",
                Kind::Text,
                json!({"text":manager_text(locale,"manager.provider_bundle.warning"),"tone":"danger"}),
                vec![],
            ));
            controls.push(node(
                "provider-bundle-details",
                Kind::KeyValue,
                json!({"items":[
                    {"key":manager_text(locale,"manager.provider_bundle.runtime"),"value":format!("{:?}",preview.runtime)},
                    {"key":manager_text(locale,"manager.provider_bundle.entrypoint"),"value":preview.entrypoint},
                    {"key":manager_text(locale,"manager.provider_bundle.files"),"value":preview.file_count},
                    {"key":manager_text(locale,"manager.provider_bundle.size"),"value":format!("{} KiB",preview.expanded_bytes.div_ceil(1024))},
                    {"key":"Package SHA-256","value":preview.sha256},
                    {"key":"Entrypoint SHA-256","value":preview.entrypoint_sha256}
                ]}),
                vec![],
            ));
            match &settings.installed_provider_bundle {
                None => controls.push(node(
                    "provider-bundle-install",
                    Kind::Button,
                    json!({"label":manager_text(locale,"manager.provider_bundle.install"),"action":"provider.bundle.install","tone":"accent"}),
                    vec![],
                )),
                Some(installed) if settings.pending_provider_launch => {
                    controls.push(node(
                        "provider-bundle-confirm-warning",
                        Kind::Text,
                        json!({"text":format!("{} · {}",manager_text(locale,"manager.provider_bundle.confirm_warning"),installed.entrypoint),"tone":"danger"}),
                        vec![],
                    ));
                    controls.push(node(
                        "provider-bundle-confirm-launch",
                        Kind::Button,
                        json!({"label":manager_text(locale,"manager.provider_bundle.confirm_launch"),"action":"provider.bundle.launch.confirm","tone":"danger","disabled":!settings.provider_launcher_available}),
                        vec![],
                    ));
                    controls.push(node(
                        "provider-bundle-cancel-launch",
                        Kind::Button,
                        json!({"label":manager_text(locale,"manager.provider_bundle.cancel_launch"),"action":"provider.bundle.launch.cancel"}),
                        vec![],
                    ));
                }
                Some(_) => controls.push(node(
                    "provider-bundle-launch-request",
                    Kind::Button,
                    json!({"label":manager_text(locale,"manager.provider_bundle.launch_request"),"action":"provider.bundle.launch.request","disabled":!settings.provider_launcher_available}),
                    vec![],
                )),
            }
            if let Some(message) = &settings.provider_bundle_notice {
                controls.push(node(
                    "provider-bundle-notice",
                    Kind::Text,
                    json!({"text":message,"tone":"success"}),
                    vec![],
                ));
            }
        }

        if let Some(preview) = &settings.pack_preview {
            controls.push(node(
                "pack-preview-heading",
                Kind::Text,
                json!({"text":format!("{} · {} · {}",preview.pack_title,preview.pack_version,
                    manager_text(locale,plan_status_key(preview.status))),"size":"heading"}),
                vec![],
            ));
            controls.push(node(
                "pack-preview-safety",
                Kind::Text,
                json!({"text":manager_text(locale,"manager.import.preview_safety"),"tone":"muted"}),
                vec![],
            ));
            controls.push(node(
                "pack-preview-summary",
                Kind::KeyValue,
                json!({"items":[
                    {"key":manager_text(locale,"manager.import.world_count"),"value":preview.world_count},
                    {"key":manager_text(locale,"manager.import.inventory_generation"),"value":preview.inventory_generation},
                    {"key":manager_text(locale,"manager.import.expires"),"value":preview.expires_at},
                    {"key":manager_text(locale,"manager.import.preview_id"),"value":preview.preview_id}
                ]}),
                vec![],
            ));
            for (index, world) in preview.worlds.iter().enumerate() {
                controls.push(node(
                    format!("pack-world-{index}"),
                    Kind::KeyValue,
                    json!({"items":[
                        {"key":world.title,"value":format!("{} × {} {}",world.width,world.height,manager_text(locale,"manager.import.logical_pixels"))},
                        {"key":manager_text(locale,"manager.import.visible"),"value":manager_text(locale,if world.visible{"manager.import.on"}else{"manager.import.off"})},
                        {"key":manager_text(locale,"manager.import.topmost"),"value":manager_text(locale,if world.always_on_top{"manager.import.on"}else{"manager.import.off"})},
                        {"key":manager_text(locale,"manager.import.resizable"),"value":manager_text(locale,if world.resizable{"manager.import.on"}else{"manager.import.off"})},
                        {"key":manager_text(locale,"manager.import.titlebar"),"value":manager_text(locale,if world.title_bar_visible{"manager.import.on"}else{"manager.import.off"})},
                        {"key":manager_text(locale,"manager.import.background_drag"),"value":manager_text(locale,if world.background_drag_enabled{"manager.import.on"}else{"manager.import.off"})},
                        {"key":manager_text(locale,"manager.import.text_selectable"),"value":manager_text(locale,if world.text_selectable{"manager.import.on"}else{"manager.import.off"})},
                        {"key":manager_text(locale,"manager.import.click_through"),"value":manager_text(locale,if world.click_through{"manager.import.on"}else{"manager.import.off"})},
                        {"key":manager_text(locale,"manager.import.opacity"),"value":format!("{:.0}%",world.surface_opacity*100.0)},
                        {"key":manager_text(locale,"manager.import.bindings"),"value":world.binding_slots.join(", ")}
                    ]}),
                    vec![],
                ));
            }
            for (binding_index, binding) in preview.bindings.iter().enumerate() {
                let resolved = binding
                    .provider_name
                    .clone()
                    .or_else(|| binding.provider_instance_id.clone())
                    .unwrap_or_else(|| manager_text(locale, "manager.import.no_provider"));
                controls.push(node(
                    format!("pack-binding-{binding_index}"),
                    Kind::Text,
                    json!({"text":format!("{} · {} · {} · {} · {}",binding.binding_id,
                        manager_text(locale,binding_status_key(&binding.status)),resolved,
                        manager_text(locale,binding_reason_key(&binding.reason)),
                        binding.requested_permissions.join(", ")),"tone":"muted"}),
                    vec![],
                ));
                for (candidate_index, candidate) in binding.candidates.iter().enumerate() {
                    let candidate_label =
                        format!("{} · {}", candidate.display_name, candidate.instance_id);
                    let can_select = binding.status == "ambiguous"
                        || binding
                            .provider_instance_id
                            .as_deref()
                            .is_some_and(|selected| selected != candidate.instance_id);
                    if candidate.missing_permissions.is_empty() {
                        if can_select {
                            let action = format!(
                                "pack.select:{}:{}:{}",
                                preview.preview_id,
                                encode_action_segment(&binding.binding_id),
                                encode_action_segment(&candidate.instance_id)
                            );
                            controls.push(node(
                                format!("pack-select-{binding_index}-{candidate_index}"),
                                Kind::Button,
                                json!({"label":format!("{}: {}",manager_text(locale,"manager.import.select_provider"),candidate_label),"action":action}),
                                vec![],
                            ));
                        }
                    } else {
                        let action = format!(
                            "pack.grant:{}:{}:{}",
                            preview.preview_id,
                            encode_action_segment(&binding.binding_id),
                            encode_action_segment(&candidate.instance_id)
                        );
                        controls.push(node(
                            format!("pack-grant-{binding_index}-{candidate_index}"),
                            Kind::Button,
                            json!({"label":format!("{}: {} · {}",manager_text(locale,"manager.import.grant_permissions"),
                                candidate_label,candidate.missing_permissions.join(", ")),"action":action,"tone":"accent"}),
                            vec![],
                        ));
                    }
                }
            }
            for (index, blocker) in preview.blockers.iter().enumerate() {
                controls.push(node(
                    format!("pack-blocker-{index}"),
                    Kind::Text,
                    json!({"text":format!("{}: {blocker}",manager_text(locale,"manager.import.blocked")),"tone":"danger"}),
                    vec![],
                ));
            }
            for (index, warning) in preview.warnings.iter().enumerate() {
                controls.push(node(
                    format!("pack-warning-{index}"),
                    Kind::Text,
                    json!({"text":format!("{}: {warning}",manager_text(locale,"manager.import.warning")),"tone":"muted"}),
                    vec![],
                ));
            }
            if matches!(preview.status, PlanStatus::Ready | PlanStatus::Degraded) {
                controls.push(node(
                    "pack-apply-action",
                    Kind::Button,
                    json!({"label":format!("{} · {}",manager_text(locale,"manager.import.apply"),preview.world_count),
                        "action":format!("pack.apply:{}",preview.preview_id),"tone":"accent"}),
                    vec![],
                ));
            } else {
                controls.push(node(
                    "pack-apply-blocked",
                    Kind::Text,
                    json!({"text":manager_text(locale,"manager.import.apply_blocked"),"tone":"muted"}),
                    vec![],
                ));
            }
            controls.push(node(
                "pack-cancel-action",
                Kind::Button,
                json!({"label":manager_text(locale,"manager.import.cancel"),"action":"pack.cancel"}),
                vec![],
            ));
        }

        if let Some(message) = &settings.pack_notice {
            controls.push(node(
                "pack-notice",
                Kind::Text,
                json!({"text":message,"tone":"muted"}),
                vec![],
            ));
        }

        for receipt in hub.recent_pack_imports(self.session)?.into_iter().take(4) {
            controls.push(node(
                format!("pack-batch-{}", receipt.batch_id),
                Kind::Text,
                json!({"text":format!("{} · {} · {}",receipt.pack_id,receipt.pack_version,
                    manager_text(locale,import_status_key(&receipt.status))),"tone":"muted"}),
                vec![],
            ));
            if !receipt.worlds.is_empty() {
                controls.push(node(
                    format!("pack-batch-worlds-{}",receipt.batch_id),
                    Kind::Text,
                    json!({"text":receipt.worlds.iter().map(|world|format!("{} ({})",world.title,world.world_id)).collect::<Vec<_>>().join(" · "),"tone":"muted"}),
                    vec![],
                ));
            }
            if let Some(code) = &receipt.failure_code {
                controls.push(node(
                    format!("pack-failure-{}",receipt.batch_id),
                    Kind::Text,
                    json!({"text":format!("{}: {} · {}: {} · {}: {}",manager_text(locale,"manager.import.failed"),code,
                        manager_text(locale,"manager.import.cleanup_removed"),receipt.cleanup_removed.len(),
                        manager_text(locale,"manager.import.retained"),receipt.retained_worlds.len()),"tone":"danger"}),
                    vec![],
                ));
            }
            if receipt.status == "applied" || receipt.status == "partial_rollback" {
                if settings.pending_rollback == Some(receipt.batch_id) {
                    controls.push(node(
                        format!("pack-rollback-note-{}",receipt.batch_id),
                        Kind::Text,
                        json!({"text":manager_text(locale,"manager.import.rollback_note"),"tone":"muted"}),
                        vec![],
                    ));
                    controls.push(node(
                        format!("pack-rollback-confirm-{}",receipt.batch_id),
                        Kind::Button,
                        json!({"label":manager_text(locale,"manager.import.rollback_confirm"),"action":format!("pack.rollback.confirm:{}",receipt.batch_id),"tone":"danger"}),
                        vec![],
                    ));
                    controls.push(node(
                        format!("pack-rollback-cancel-{}",receipt.batch_id),
                        Kind::Button,
                        json!({"label":manager_text(locale,"manager.import.cancel"),"action":format!("pack.rollback.cancel:{}",receipt.batch_id)}),
                        vec![],
                    ));
                } else {
                    controls.push(node(
                        format!("pack-rollback-request-{}",receipt.batch_id),
                        Kind::Button,
                        json!({"label":manager_text(locale,"manager.import.rollback"),"action":format!("pack.rollback.request:{}",receipt.batch_id)}),
                        vec![],
                    ));
                }
            }
        }

        Ok(node("pack-import", Kind::Stack, json!({"gap":8}), controls))
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
                "shortcut-heading",
                Kind::Text,
                json!({"text":manager_text(&locale,"manager.shortcut.section"),"size":"heading"}),
                vec![],
            ),
            node(
                "shortcut-draft",
                Kind::Input,
                json!({
                    "label":manager_text(&locale,"manager.shortcut.chord"),
                    "value":settings.shortcut_draft,
                    "action":"shortcut.draft",
                    "placeholder":manager_text(&locale,"manager.shortcut.placeholder")
                }),
                vec![],
            ),
            node(
                "shortcut-controls",
                Kind::Row,
                json!({"gap":8}),
                vec![
                    node(
                        "shortcut-enable",
                        Kind::Button,
                        json!({
                            "label":manager_text(&locale,"manager.shortcut.enable"),
                            "action":"shortcut.enable",
                            "tone":"accent",
                            "disabled":!settings.shortcut_available || settings.shortcut_active.is_some()
                        }),
                        vec![],
                    ),
                    node(
                        "shortcut-disable",
                        Kind::Button,
                        json!({
                            "label":manager_text(&locale,"manager.shortcut.disable"),
                            "action":"shortcut.disable",
                            "disabled":settings.shortcut_active.is_none()
                        }),
                        vec![],
                    ),
                ],
            ),
            node(
                "shortcut-status",
                Kind::Text,
                json!({
                    "text":settings.shortcut_notice.as_deref().map(str::to_owned).unwrap_or_else(|| {
                        settings.shortcut_active.as_ref().map(|chord| {
                            format!("{}: {chord}", manager_text(&locale,"manager.shortcut.active"))
                        }).unwrap_or_else(|| manager_text(&locale,if settings.shortcut_available {
                            "manager.shortcut.not_enabled"
                        } else {
                            "manager.shortcut.not_supported"
                        }))
                    }),
                    "tone":"muted"
                }),
                vec![],
            ),
            node(
                "shortcut-privacy",
                Kind::Text,
                json!({"text":manager_text(&locale,"manager.shortcut.privacy"),"tone":"muted"}),
                vec![],
            ),
            node(
                "descriptor-controls",
                Kind::Row,
                json!({"gap":8,"align":"center"}),
                vec![
                    node(
                        "descriptor",
                        Kind::KeyValue,
                        json!({"items":[{"key":manager_text(&locale,"manager.descriptor"),"value":descriptor},{"key":manager_text(&locale,"manager.save_policy_key"),"value":manager_text(&locale,"manager.save_policy")}]}),
                        vec![],
                    ),
                    node(
                        "descriptor-copy",
                        Kind::Button,
                        json!({"label":manager_text(&locale,"manager.descriptor_copy"),"action":"manager.descriptor.copy"}),
                        vec![],
                    ),
                ],
            ),
            node("worlds-line", Kind::Divider, json!({}), vec![]),
        ];
        rows.insert(3, self.pack_controls(hub, settings, &locale)?);
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

fn encode_action_segment(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn decode_action_segment(value: &str) -> Result<String> {
    let (pairs, remainder) = value.as_bytes().as_chunks::<2>();
    if !remainder.is_empty() || value.len() > 192 {
        return Err(Fault::new(
            "INVALID_ACTION",
            "invalid configuration action identity",
        ));
    }
    let mut bytes = Vec::with_capacity(pairs.len());
    for pair in pairs {
        let pair = std::str::from_utf8(pair)
            .map_err(|_| Fault::new("INVALID_ACTION", "invalid configuration action identity"))?;
        bytes.push(
            u8::from_str_radix(pair, 16).map_err(|_| {
                Fault::new("INVALID_ACTION", "invalid configuration action identity")
            })?,
        );
    }
    String::from_utf8(bytes).map_err(|_| {
        Fault::new(
            "INVALID_ACTION",
            "configuration action identity is not UTF-8",
        )
    })
}

fn parse_pack_choice(action: &str, prefix: &str) -> Result<(Uuid, String, String)> {
    let mut parts = action
        .strip_prefix(prefix)
        .ok_or_else(|| Fault::new("INVALID_ACTION", "invalid configuration action"))?
        .split(':');
    let preview_id = parts
        .next()
        .and_then(|value| value.parse().ok())
        .ok_or_else(|| Fault::new("INVALID_ACTION", "invalid configuration preview id"))?;
    let binding = parts
        .next()
        .ok_or_else(|| Fault::new("INVALID_ACTION", "configuration binding is missing"))?;
    let instance = parts
        .next()
        .ok_or_else(|| Fault::new("INVALID_ACTION", "provider instance is missing"))?;
    if parts.next().is_some() {
        return Err(Fault::new(
            "INVALID_ACTION",
            "configuration action has extra fields",
        ));
    }
    Ok((
        preview_id,
        decode_action_segment(binding)?,
        decode_action_segment(instance)?,
    ))
}

fn plan_status_key(status: PlanStatus) -> &'static str {
    match status {
        PlanStatus::Ready => "manager.import.status.ready",
        PlanStatus::Degraded => "manager.import.status.degraded",
        PlanStatus::Blocked => "manager.import.status.blocked",
    }
}

fn binding_status_key(status: &str) -> &'static str {
    match status {
        "selected" => "manager.import.binding.selected",
        "missing" => "manager.import.binding.missing",
        "ambiguous" => "manager.import.binding.ambiguous",
        "blocked" => "manager.import.binding.blocked",
        _ => "manager.import.binding.unknown",
    }
}

fn binding_reason_key(reason: &str) -> &'static str {
    match reason {
        "explicit_authorized_selection" => "manager.import.reason.explicit_selection",
        "unique_eligible_provider" => "manager.import.reason.unique_provider",
        "multiple_eligible_providers_need_user_choice" => "manager.import.reason.ambiguous",
        "no_online_fresh_compatible_provider" => "manager.import.reason.missing",
        "host_permission_required" | "explicit_selection_requires_permission" => {
            "manager.import.reason.permission"
        }
        "explicit_selection_not_eligible" => "manager.import.reason.selection_ineligible",
        _ => "manager.import.reason.other",
    }
}

fn import_status_key(status: &str) -> &'static str {
    match status {
        "applied" => "manager.import.status.applied",
        "failed_rolled_back" => "manager.import.status.failed_rolled_back",
        "partial" => "manager.import.status.partial",
        "rolled_back" => "manager.import.status.rolled_back",
        "partial_rollback" => "manager.import.status.partial_rollback",
        _ => "manager.import.status.unknown",
    }
}

fn import_receipt_text(hub: &Hub, receipt: &ImportReceipt) -> String {
    format!(
        "{} · {} · {}",
        manager_text(&hub.locale(), import_status_key(&receipt.status)),
        receipt.pack_id,
        receipt.worlds.len()
    )
}

fn rollback_receipt_text(hub: &Hub, receipt: &RollbackReceipt) -> String {
    format!(
        "{} · {}: {} · {}: {}",
        manager_text(&hub.locale(), import_status_key(&receipt.status)),
        manager_text(&hub.locale(), "manager.import.cleanup_removed"),
        receipt.removed.len() + receipt.already_missing.len(),
        manager_text(&hub.locale(), "manager.import.retained"),
        receipt.retained.len()
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        collections::BTreeSet,
        io::Write,
        sync::{
            atomic::{AtomicUsize, Ordering},
            Mutex,
        },
    };
    use zip::{write::SimpleFileOptions, CompressionMethod, ZipWriter};

    #[derive(Default)]
    struct FakeShortcutHost {
        registered: Mutex<BTreeSet<String>>,
        reject_registration: bool,
        reject_unregistration: bool,
    }

    impl ShortcutHost for FakeShortcutHost {
        fn register(&self, spec: &ShortcutSpec) -> std::result::Result<(), String> {
            if self.reject_registration {
                return Err("synthetic native shortcut conflict".into());
            }
            self.registered
                .lock()
                .expect("shortcut fake mutex poisoned")
                .insert(spec.chord.clone());
            Ok(())
        }

        fn unregister(&self, chord: &str) -> std::result::Result<(), String> {
            if self.reject_unregistration {
                return Err("synthetic native shortcut cleanup failure".into());
            }
            self.registered
                .lock()
                .expect("shortcut fake mutex poisoned")
                .remove(chord);
            Ok(())
        }
    }

    #[derive(Default)]
    struct FakeProviderBundleLauncher {
        launches: AtomicUsize,
    }

    impl ProviderBundleLauncher for FakeProviderBundleLauncher {
        fn launch(
            &self,
            _bundle: &InstalledProviderBundle,
            _runtime_descriptor: &Path,
        ) -> std::result::Result<(), String> {
            self.launches.fetch_add(1, Ordering::SeqCst);
            Ok(())
        }
    }

    #[test]
    fn provider_bundle_launch_requires_an_explicit_second_confirmation() {
        let hub = Hub::new(true);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let launcher = FakeProviderBundleLauncher::default();
        let installed = InstalledProviderBundle {
            id: "sample-provider".into(),
            version: "1.0.0".into(),
            title: "Synthetic Provider".into(),
            runtime: crate::provider_package::ProviderRuntime::Python,
            entrypoint: "main.py".into(),
            install_dir: PathBuf::from("C:/synthetic/providers/sample-provider/1.0.0"),
            sha256: "a".repeat(64),
            entrypoint_sha256: "b".repeat(64),
        };
        let mut settings = Settings {
            installed_provider_bundle: Some(installed),
            provider_launcher_available: true,
            ..Settings::default()
        };
        let descriptor = Path::new("C:/synthetic/runtime.json");

        let early = manager.handle_with_hosts(
            &hub,
            &mut settings,
            &action(
                &manager,
                "provider.bundle.launch.confirm".into(),
                Value::Null,
            ),
            None,
            Some(&launcher),
            descriptor,
        );
        assert_eq!(
            early.unwrap_err().code,
            "PROVIDER_LAUNCH_CONFIRMATION_REQUIRED"
        );
        assert_eq!(launcher.launches.load(Ordering::SeqCst), 0);

        manager
            .handle_with_hosts(
                &hub,
                &mut settings,
                &action(
                    &manager,
                    "provider.bundle.launch.request".into(),
                    Value::Null,
                ),
                None,
                Some(&launcher),
                descriptor,
            )
            .expect("first action only opens the confirmation state");
        assert!(settings.pending_provider_launch);
        assert_eq!(launcher.launches.load(Ordering::SeqCst), 0);

        manager
            .handle_with_hosts(
                &hub,
                &mut settings,
                &action(
                    &manager,
                    "provider.bundle.launch.confirm".into(),
                    Value::Null,
                ),
                None,
                Some(&launcher),
                descriptor,
            )
            .expect("the final explicit action launches the installed package");
        assert!(!settings.pending_provider_launch);
        assert_eq!(launcher.launches.load(Ordering::SeqCst), 1);
    }

    fn write_import_fixture(permissions: &[&str]) -> PathBuf {
        let path = std::env::temp_dir().join(format!("wincraft-pack-{}.wcp", Uuid::new_v4()));
        let pack = json!({
            "kind":"wincraft.pack.draft","schema_version":"draft-2026-10-26",
            "id":"fixture.manager-import","version":"1.0.0",
            "title":{"zh-CN":"管理器导入测试","en-US":"Manager import test"},
            "bindings":[{"id":"optional-metrics","required":!permissions.is_empty(),"provider_types":["metrics"],
                "capabilities":["metrics.read","world.import.accept"],"permissions":permissions,"min_adapter_contract":1}],
            "blueprint":"blueprints/fixture.json","fallback_policy":"explain_missing","adapter":null
        });
        let blueprint = json!({
            "kind":"wincraft.blueprint.draft","schema_version":"draft-2026-10-26","id":"fixture.blueprint",
            "worlds":[{"id":"metrics","title":{"zh-CN":"测试指标","en-US":"Test metrics"},
                "binding_slots":["optional-metrics"],"layout_hint":"stack",
                "scene":{"root":{"id":"root","kind":"stack","children":[
                    {"id":"title","kind":"text","props":{"text":"测试指标","size":"title"}}
                ]}}}]
        });
        let file = std::fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&path)
            .unwrap();
        let mut archive = ZipWriter::new(file);
        let options = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
        archive.start_file("pack.json", options).unwrap();
        archive
            .write_all(&serde_json::to_vec(&pack).unwrap())
            .unwrap();
        archive
            .start_file("blueprints/fixture.json", options)
            .unwrap();
        archive
            .write_all(&serde_json::to_vec(&blueprint).unwrap())
            .unwrap();
        drop(archive.finish().unwrap());
        path
    }

    fn register_metrics_inventory(hub: &Hub, session: Uuid, generation: u64) {
        let observed_at = time::OffsetDateTime::now_utc()
            .format(&time::format_description::well_known::Rfc3339)
            .expect("inventory timestamp formats");
        hub.dispatch(
            session,
            "provider.inventory.register",
            json!({
                "kind":"wincraft.inventory.registration",
                "schema_version":"draft-2026-10-29",
                "generation":generation,
                "observed_at":observed_at.clone(),
                "valid_for_seconds":300,
                "providers":[{
                    "source_id":"source.metrics",
                    "source_instance_id":"instance-a",
                    "provider_type":"metrics",
                    "display_name":"Metrics provider",
                    "adapter_contract":1,
                    "state":"online",
                    "capabilities":["metrics.read","world.import.accept"],
                    "source_updated_at":observed_at,
                    "fresh_for_seconds":300
                }]
            }),
        )
        .expect("provider inventory registers");
    }

    fn register_metrics_provider(hub: &Hub) -> Uuid {
        let session = hub
            .lock()
            .register_with_protocol(
                "metrics-provider".into(),
                false,
                ProtocolVersion::ComponentLeasesPreview01,
            )
            .expect("preview provider registers");
        register_metrics_inventory(hub, session, 1);
        session
    }

    fn action(manager: &ManagerProvider, action: String, value: Value) -> UiEvent {
        UiEvent {
            id: Uuid::new_v4(),
            world_id: manager.world_id,
            component_id: "fixture-action".into(),
            action,
            value,
            lease_epoch: 0,
            revision: 0,
        }
    }

    #[test]
    fn local_manager_shortcut_requires_click_and_can_be_disabled() {
        let hub = Hub::new(true);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let native = FakeShortcutHost::default();
        let mut settings = Settings {
            shortcut_available: true,
            shortcut_draft: "Ctrl + Shift + M".into(),
            ..Settings::default()
        };

        manager
            .handle_with_shortcut_host(
                &hub,
                &mut settings,
                &action(&manager, "shortcut.enable".into(), Value::Null),
                Some(&native),
            )
            .expect("local enable action registers the shortcut");
        assert_eq!(settings.shortcut_active.as_deref(), Some("ctrl+shift+m"));
        assert!(hub.shortcut_registered("Control+Shift+M"));
        assert!(native
            .registered
            .lock()
            .expect("shortcut fake mutex is available")
            .contains("ctrl+shift+m"));

        manager
            .handle_with_shortcut_host(
                &hub,
                &mut settings,
                &action(&manager, "shortcut.disable".into(), Value::Null),
                Some(&native),
            )
            .expect("local disable action releases the shortcut");
        assert!(settings.shortcut_active.is_none());
        assert!(!hub.shortcut_registered("ctrl+shift+m"));
        assert!(native
            .registered
            .lock()
            .expect("shortcut fake mutex is available")
            .is_empty());
    }

    #[test]
    fn failed_native_registration_rolls_back_the_core_intent() {
        let hub = Hub::new(true);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let native = FakeShortcutHost {
            reject_registration: true,
            ..FakeShortcutHost::default()
        };
        let mut settings = Settings {
            shortcut_available: true,
            shortcut_draft: "Ctrl+Shift+M".into(),
            ..Settings::default()
        };

        let error = manager
            .handle_with_shortcut_host(
                &hub,
                &mut settings,
                &action(&manager, "shortcut.enable".into(), Value::Null),
                Some(&native),
            )
            .unwrap_err();

        assert_eq!(error.code, "SHORTCUT_REGISTRATION_FAILED");
        assert!(!hub.shortcut_registered("Ctrl+Shift+M"));
        assert!(settings.shortcut_active.is_none());
    }

    #[test]
    fn failed_native_unregistration_keeps_intent_for_retry() {
        let hub = Hub::new(true);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let mut native = FakeShortcutHost::default();
        let mut settings = Settings {
            shortcut_available: true,
            shortcut_draft: "Ctrl+Shift+M".into(),
            ..Settings::default()
        };
        manager
            .handle_with_shortcut_host(
                &hub,
                &mut settings,
                &action(&manager, "shortcut.enable".into(), Value::Null),
                Some(&native),
            )
            .expect("local enable action registers the shortcut");
        native.reject_unregistration = true;

        let error = manager
            .handle_with_shortcut_host(
                &hub,
                &mut settings,
                &action(&manager, "shortcut.disable".into(), Value::Null),
                Some(&native),
            )
            .expect_err("failed native cleanup must stay visible");

        assert_eq!(error.code, "SHORTCUT_UNREGISTER_FAILED");
        assert_eq!(settings.shortcut_active.as_deref(), Some("ctrl+shift+m"));
        assert!(hub.shortcut_registered("ctrl+shift+m"));

        native.reject_unregistration = false;
        manager
            .handle_with_shortcut_host(
                &hub,
                &mut settings,
                &action(&manager, "shortcut.disable".into(), Value::Null),
                Some(&native),
            )
            .expect("the user can retry native cleanup");
        assert!(settings.shortcut_active.is_none());
        assert!(!hub.shortcut_registered("ctrl+shift+m"));
    }

    #[test]
    fn manager_shortcut_is_not_registered_by_default() {
        let hub = Hub::new(true);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let settings = Settings {
            shortcut_available: true,
            ..Settings::default()
        };

        manager
            .refresh(&hub, &settings, "<synthetic descriptor>")
            .expect("manager scene renders without enabling a shortcut");

        let snapshot = hub
            .renderer_snapshot(manager.world_id)
            .expect("manager snapshot exists");
        let scene = serde_json::to_string(&snapshot.scene).expect("scene serializes");
        assert!(scene.contains("未启用任何全局快捷键"));
        assert!(!hub.shortcut_registered("Ctrl+Alt+M"));
    }

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
            ..Settings::default()
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
            ..Settings::default()
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
            ..Settings::default()
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

    #[test]
    fn configuration_action_segment_decoder_rejects_invalid_hex_and_utf8() {
        assert_eq!(decode_action_segment("6f6b").unwrap(), "ok");
        assert_eq!(
            decode_action_segment("0").unwrap_err().code,
            "INVALID_ACTION"
        );
        assert_eq!(
            decode_action_segment("zz").unwrap_err().code,
            "INVALID_ACTION"
        );
        assert_eq!(
            decode_action_segment("ff").unwrap_err().code,
            "INVALID_ACTION"
        );
    }

    #[test]
    fn manager_import_preview_apply_and_confirmed_rollback_use_the_generic_world_ui() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let pack_path = write_import_fixture(&[]);
        let mut settings = Settings {
            pack_path: pack_path.to_string_lossy().into_owned(),
            ..Settings::default()
        };

        manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, "pack.preview".into(), Value::Null),
            )
            .expect("manager previews a validated package");
        let preview = settings
            .pack_preview
            .clone()
            .expect("preview is stored for this session");
        assert_eq!(preview.status, PlanStatus::Degraded);
        assert!(!preview.worlds[0].click_through);
        manager.refresh(&hub, &settings, "<descriptor>").unwrap();
        let preview_scene = hub.renderer_snapshot(manager.world_id).unwrap().scene;
        assert!(preview_scene.root.find("pack-preview-heading").is_some());
        assert!(preview_scene.root.find("pack-apply-action").is_some());
        manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, "pack.cancel".into(), Value::Null),
            )
            .expect("cancelled preview does not mutate existing worlds");
        assert!(settings.pack_preview.is_none());
        assert_eq!(hub.lock().worlds.len(), 1);

        manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, "pack.preview".into(), Value::Null),
            )
            .expect("a fresh preview can be prepared after cancellation");
        let preview = settings
            .pack_preview
            .clone()
            .expect("fresh preview is stored for this session");

        manager
            .handle(
                &hub,
                &mut settings,
                &action(
                    &manager,
                    format!("pack.apply:{}", preview.preview_id),
                    Value::Null,
                ),
            )
            .expect("explicit apply creates only the blueprint world");
        let imports = hub.recent_pack_imports(manager.session).unwrap();
        assert_eq!(imports.len(), 1);
        let batch_id = imports[0].batch_id;
        assert_eq!(hub.lock().worlds.len(), 2);

        manager
            .handle(
                &hub,
                &mut settings,
                &action(
                    &manager,
                    format!("pack.rollback.request:{batch_id}"),
                    Value::Null,
                ),
            )
            .expect("rollback is a separate confirmation step");
        assert!(settings.pending_rollback.is_some());
        manager
            .handle(
                &hub,
                &mut settings,
                &action(
                    &manager,
                    format!("pack.rollback.confirm:{batch_id}"),
                    Value::Null,
                ),
            )
            .expect("confirmed rollback removes only its unchanged world");
        assert_eq!(hub.lock().worlds.len(), 1);

        std::fs::remove_file(pack_path).unwrap();
    }

    #[test]
    fn manager_permission_button_grants_then_repreviews_before_apply() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let provider_session = register_metrics_provider(&hub);

        let pack_path = write_import_fixture(&["metrics.read"]);
        let mut settings = Settings {
            pack_path: pack_path.to_string_lossy().into_owned(),
            ..Settings::default()
        };
        manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, "pack.preview".into(), Value::Null),
            )
            .expect("manager prepares permission-blocked preview");
        let blocked_preview = settings
            .pack_preview
            .clone()
            .expect("blocked preview stays in manager state");
        assert_eq!(blocked_preview.status, PlanStatus::Blocked);
        assert_eq!(hub.lock().worlds.len(), 1);

        manager.refresh(&hub, &settings, "<descriptor>").unwrap();
        let preview_scene = hub.renderer_snapshot(manager.world_id).unwrap().scene;
        let grant_action = preview_scene
            .root
            .find("pack-grant-0-0")
            .and_then(|node| node.props.get("action"))
            .and_then(Value::as_str)
            .expect("blocked candidate has a visible static grant action")
            .to_owned();
        assert!(grant_action.starts_with(&format!("pack.grant:{}:", blocked_preview.preview_id)));

        manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, grant_action, Value::Null),
            )
            .expect("local operator approval grants only the declared permission");
        let authorized_preview = settings
            .pack_preview
            .clone()
            .expect("permission approval creates a fresh preview");
        assert_ne!(authorized_preview.preview_id, blocked_preview.preview_id);
        assert!(authorized_preview.inventory_generation > blocked_preview.inventory_generation);
        assert_eq!(authorized_preview.status, PlanStatus::Ready);
        assert_eq!(
            authorized_preview.bindings[0]
                .provider_instance_id
                .as_deref(),
            Some("instance-a")
        );
        assert!(authorized_preview.bindings[0].candidates[0]
            .missing_permissions
            .is_empty());
        assert_eq!(hub.lock().worlds.len(), 1);
        assert_eq!(
            hub.apply_pack_preview(manager.session, blocked_preview.preview_id, true)
                .unwrap_err()
                .code,
            "PLAN_NOT_FOUND"
        );

        manager.refresh(&hub, &settings, "<descriptor>").unwrap();
        let authorized_scene = hub.renderer_snapshot(manager.world_id).unwrap().scene;
        assert!(authorized_scene.root.find("pack-grant-0-0").is_none());
        assert!(authorized_scene.root.find("pack-apply-action").is_some());
        manager
            .handle(
                &hub,
                &mut settings,
                &action(
                    &manager,
                    format!("pack.apply:{}", authorized_preview.preview_id),
                    Value::Null,
                ),
            )
            .expect("fresh preview applies after the separate local grant");
        let receipt = hub
            .recent_pack_imports(manager.session)
            .unwrap()
            .into_iter()
            .next()
            .expect("apply receipt is visible to the manager");
        assert_eq!(receipt.status, "applied");
        assert_eq!(receipt.worlds.len(), 1);
        assert_eq!(
            hub.renderer_snapshot(receipt.worlds[0].world_id)
                .unwrap()
                .writer,
            Some(provider_session)
        );

        std::fs::remove_file(pack_path).unwrap();
    }

    #[test]
    fn stale_permission_action_clears_the_manager_preview_and_shows_replan_notice() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let provider_session = register_metrics_provider(&hub);
        let pack_path = write_import_fixture(&["metrics.read"]);
        let mut settings = Settings {
            pack_path: pack_path.to_string_lossy().into_owned(),
            ..Settings::default()
        };

        manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, "pack.preview".into(), Value::Null),
            )
            .expect("manager previews the pending permission");
        assert!(settings.pack_preview.is_some(), "initial preview is stored");
        manager.refresh(&hub, &settings, "<descriptor>").unwrap();
        let grant_action = hub
            .renderer_snapshot(manager.world_id)
            .unwrap()
            .scene
            .root
            .find("pack-grant-0-0")
            .and_then(|node| node.props.get("action"))
            .and_then(Value::as_str)
            .expect("manager renders the grant action")
            .to_owned();

        register_metrics_inventory(&hub, provider_session, 2);
        let error = manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, grant_action, Value::Null),
            )
            .expect_err("stale plan cannot grant a permission");

        assert_eq!(error.code, "STALE_PLAN");
        assert!(settings.pack_preview.is_none());
        assert_eq!(
            settings.pack_notice.as_deref(),
            Some(manager_text(&hub.locale(), "manager.import.stale").as_str())
        );
        assert_eq!(hub.lock().worlds.len(), 1);
        manager.refresh(&hub, &settings, "<descriptor>").unwrap();
        let stale_scene = hub.renderer_snapshot(manager.world_id).unwrap().scene;
        assert!(stale_scene.root.find("pack-preview-heading").is_none());
        assert!(stale_scene.root.find("pack-notice").is_some());

        std::fs::remove_file(pack_path).unwrap();
    }

    #[test]
    fn stale_rendered_grant_does_not_clear_a_newer_manager_preview() {
        let hub = Hub::new(false);
        let manager = ManagerProvider::install(&hub).expect("manager installs");
        let _provider_session = register_metrics_provider(&hub);
        let pack_path = write_import_fixture(&["metrics.read"]);
        let mut settings = Settings {
            pack_path: pack_path.to_string_lossy().into_owned(),
            ..Settings::default()
        };

        manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, "pack.preview".into(), Value::Null),
            )
            .expect("manager creates the first preview");
        let stale_preview_id = settings
            .pack_preview
            .as_ref()
            .expect("first preview is stored")
            .preview_id;
        manager.refresh(&hub, &settings, "<descriptor>").unwrap();
        let stale_action = hub
            .renderer_snapshot(manager.world_id)
            .unwrap()
            .scene
            .root
            .find("pack-grant-0-0")
            .and_then(|node| node.props.get("action"))
            .and_then(Value::as_str)
            .expect("first preview renders a grant action")
            .to_owned();

        manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, "pack.preview".into(), Value::Null),
            )
            .expect("manager replaces it with a newer preview");
        let current_preview_id = settings
            .pack_preview
            .as_ref()
            .expect("new preview is stored")
            .preview_id;
        assert_ne!(stale_preview_id, current_preview_id);

        let error = manager
            .handle(
                &hub,
                &mut settings,
                &action(&manager, stale_action, Value::Null),
            )
            .expect_err("an old action cannot target the newer preview");

        assert_eq!(error.code, "STALE_PLAN");
        assert_eq!(
            settings
                .pack_preview
                .as_ref()
                .map(|preview| preview.preview_id),
            Some(current_preview_id)
        );
        assert!(settings.pack_notice.is_none());
        manager.refresh(&hub, &settings, "<descriptor>").unwrap();
        let current_scene = hub.renderer_snapshot(manager.world_id).unwrap().scene;
        assert!(current_scene.root.find("pack-preview-heading").is_some());
        assert!(current_scene.root.find("pack-grant-0-0").is_some());

        std::fs::remove_file(pack_path).unwrap();
    }
}
