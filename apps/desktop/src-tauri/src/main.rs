#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod windows;
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    net::SocketAddr,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
};
use tauri::{Emitter, LogicalSize, Manager, PhysicalPosition, WebviewWindow};
use tauri_plugin_clipboard_manager::ClipboardExt;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use uuid::Uuid;
use wincraft_core::{
    EventSource, Fault, GeometryControl, InteractionSource, ShortcutSpec, Snapshot,
};
use wincraft_server::{
    provider_package::{
        verify_installed_provider_entrypoint, InstalledProviderBundle, ProviderRuntime,
    },
    self_provider::{ManagerProvider, ProviderBundleLauncher, ShortcutHost},
    Hub, RunningServer,
};

pub struct DesktopState {
    pub hub: Hub,
    pub manager: ManagerProvider,
    pub tray_visibility: windows::TrayVisibilityState,
    locale_path: PathBuf,
    provider_launcher: Arc<TauriProviderBundleLauncher>,
    // Keeps the descriptor guard alive. It removes only this host's credential file on normal exit.
    pub server: Mutex<Option<RunningServer>>,
}

const EXTERNAL_WINDOW_ACTIONS_AVAILABLE: bool = cfg!(target_os = "windows");

struct TauriShortcutHost {
    app: tauri::AppHandle,
    registered: Mutex<BTreeSet<String>>,
}

struct TauriProviderBundleLauncher {
    provider_store: PathBuf,
    processes: Mutex<BTreeMap<String, Child>>,
}

impl TauriProviderBundleLauncher {
    fn new(provider_store: PathBuf) -> Self {
        Self {
            provider_store,
            processes: Mutex::new(BTreeMap::new()),
        }
    }

    fn shutdown(&self) {
        let mut processes = self
            .processes
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        for (_, mut child) in std::mem::take(&mut *processes) {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl ProviderBundleLauncher for TauriProviderBundleLauncher {
    fn launch(
        &self,
        bundle: &InstalledProviderBundle,
        runtime_descriptor: &Path,
    ) -> std::result::Result<(), String> {
        let descriptor_metadata = fs::symlink_metadata(runtime_descriptor)
            .map_err(|error| format!("runtime descriptor is unavailable: {error}"))?;
        if descriptor_metadata.file_type().is_symlink() || !descriptor_metadata.is_file() {
            return Err("runtime descriptor is not a regular local file".into());
        }
        let descriptor = runtime_descriptor
            .canonicalize()
            .map_err(|error| format!("runtime descriptor could not be resolved: {error}"))?;
        let store = self
            .provider_store
            .canonicalize()
            .map_err(|error| format!("Provider store is unavailable: {error}"))?;
        let package_id_dir = store.join(&bundle.id);
        let id_metadata = fs::symlink_metadata(&package_id_dir)
            .map_err(|error| format!("Provider package folder is unavailable: {error}"))?;
        if id_metadata.file_type().is_symlink() || !id_metadata.is_dir() {
            return Err("Provider package folder is not a regular directory".into());
        }
        let version_dir = package_id_dir.join(&bundle.version);
        let version_metadata = fs::symlink_metadata(&version_dir)
            .map_err(|error| format!("installed Provider version is unavailable: {error}"))?;
        if version_metadata.file_type().is_symlink() || !version_metadata.is_dir() {
            return Err("installed Provider version is not a regular directory".into());
        }
        let package_root = bundle
            .install_dir
            .canonicalize()
            .map_err(|error| format!("installed Provider folder is unavailable: {error}"))?;
        if package_root
            != version_dir
                .canonicalize()
                .map_err(|error| error.to_string())?
        {
            return Err(
                "installed Provider folder does not match its validated package identity".into(),
            );
        }
        let relative = Path::new(&bundle.entrypoint);
        if relative.as_os_str().is_empty()
            || relative
                .components()
                .any(|component| !matches!(component, std::path::Component::Normal(_)))
        {
            return Err("Provider entrypoint path is invalid".into());
        }
        let entrypoint = package_root.join(relative);
        let entry_metadata = fs::symlink_metadata(&entrypoint)
            .map_err(|error| format!("Provider entrypoint is unavailable: {error}"))?;
        if entry_metadata.file_type().is_symlink() || !entry_metadata.is_file() {
            return Err("Provider entrypoint is not a regular file".into());
        }
        let entrypoint = entrypoint
            .canonicalize()
            .map_err(|error| format!("Provider entrypoint could not be resolved: {error}"))?;
        if !entrypoint.starts_with(&package_root) {
            return Err("Provider entrypoint is outside its installed folder".into());
        }
        verify_installed_provider_entrypoint(bundle).map_err(|error| error.message)?;

        let program = match &bundle.runtime {
            ProviderRuntime::Python => resolve_runtime_executable("python.exe")?,
            ProviderRuntime::Node => resolve_runtime_executable("node.exe")?,
            ProviderRuntime::Native => entrypoint.clone(),
        };
        let key = format!("{}@{}", bundle.id, bundle.version);
        let mut processes = self
            .processes
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if let Some(child) = processes.get_mut(&key) {
            if child
                .try_wait()
                .map_err(|error| error.to_string())?
                .is_none()
            {
                return Err("this Provider version is already running".into());
            }
            processes.remove(&key);
        }

        let mut command = Command::new(program);
        if bundle.runtime != ProviderRuntime::Native {
            command.arg(&entrypoint);
        }
        command
            .arg("--runtime")
            .arg(&descriptor)
            .current_dir(&package_root)
            .env_clear()
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        for name in [
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "TEMP",
            "TMP",
        ] {
            if let Some(value) = std::env::var_os(name) {
                command.env(name, value);
            }
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let child = command
            .spawn()
            .map_err(|error| format!("Provider runtime could not start: {error}"))?;
        processes.insert(key, child);
        Ok(())
    }
}

impl Drop for TauriProviderBundleLauncher {
    fn drop(&mut self) {
        self.shutdown();
    }
}

fn resolve_runtime_executable(name: &str) -> std::result::Result<PathBuf, String> {
    let path =
        std::env::var_os("PATH").ok_or_else(|| "runtime PATH is not configured".to_owned())?;
    for directory in std::env::split_paths(&path) {
        let candidate = directory.join(name);
        if candidate.is_file() {
            return candidate
                .canonicalize()
                .map_err(|error| format!("runtime executable could not be resolved: {error}"));
        }
    }
    Err(format!("{name} is not installed or is not on PATH"))
}

impl ShortcutHost for TauriShortcutHost {
    fn register(&self, spec: &ShortcutSpec) -> std::result::Result<(), String> {
        if spec.action != "manager.show" {
            return Err("this host shortcut adapter only supports manager.show".into());
        }
        self.app
            .global_shortcut()
            .on_shortcut(spec.chord.as_str(), |app, _shortcut, event| {
                if event.state() != ShortcutState::Pressed {
                    return;
                }
                let state = app.state::<DesktopState>();
                windows::activate_manager(
                    app.clone(),
                    state.hub.clone(),
                    state.manager.clone(),
                    state.tray_visibility.clone(),
                );
            })
            .map_err(|error| error.to_string())?;
        self.registered
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .insert(spec.chord.clone());
        Ok(())
    }

    fn unregister(&self, chord: &str) -> std::result::Result<(), String> {
        self.app
            .global_shortcut()
            .unregister(chord)
            .map_err(|error| error.to_string())?;
        self.registered
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .remove(chord);
        Ok(())
    }
}

impl Drop for TauriShortcutHost {
    fn drop(&mut self) {
        let chords: Vec<String> = self
            .registered
            .get_mut()
            .unwrap_or_else(|error| error.into_inner())
            .iter()
            .cloned()
            .collect();
        let shortcuts = self.app.global_shortcut();
        for chord in chords {
            if shortcuts.is_registered(chord.as_str()) {
                let _ = shortcuts.unregister(chord.as_str());
            }
        }
    }
}

fn load_locale(path: &Path) -> String {
    match fs::read_to_string(path)
        .map(|value| value.trim().to_owned())
        .as_deref()
    {
        Ok("en-US") => "en-US".into(),
        _ => "zh-CN".into(),
    }
}
fn save_locale(path: &Path, locale: &str) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, format!("{locale}\n"))
}
fn caller_world(window: &WebviewWindow) -> Result<Uuid, Fault> {
    window
        .label()
        .strip_prefix("world-")
        .and_then(|s| s.parse().ok())
        .ok_or_else(|| Fault::new("FORBIDDEN", "not a world renderer"))
}
#[tauri::command]
fn surface_snapshot(
    window: WebviewWindow,
    state: tauri::State<'_, DesktopState>,
) -> Result<Snapshot, Fault> {
    state.hub.renderer_snapshot(caller_world(&window)?)
}
#[tauri::command]
fn surface_locale_get(state: tauri::State<'_, DesktopState>) -> String {
    state.hub.locale()
}
#[tauri::command]
fn surface_locale_set(
    window: WebviewWindow,
    app: tauri::AppHandle,
    state: tauri::State<'_, DesktopState>,
    locale: String,
) -> Result<(), Fault> {
    let world_id = caller_world(&window)?;
    if !state.hub.renderer_snapshot(world_id)?.system {
        return Err(Fault::new(
            "FORBIDDEN",
            "only the internal manager can change host display language",
        ));
    }
    state.hub.set_locale(&locale)?;
    save_locale(&state.locale_path, &locale)
        .map_err(|error| Fault::new("PREFERENCE_WRITE_FAILED", error.to_string()))?;
    app.emit("host/locale", locale)
        .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;
    Ok(())
}

#[tauri::command]
fn surface_copy_descriptor(
    window: WebviewWindow,
    app: tauri::AppHandle,
    state: tauri::State<'_, DesktopState>,
) -> Result<(), Fault> {
    let world_id = caller_world(&window)?;
    if !manager_descriptor_copy_allowed(
        world_id,
        state.manager.world_id,
        state.hub.renderer_snapshot(world_id)?.system,
    ) {
        return Err(Fault::new(
            "FORBIDDEN",
            "only the local World Manager can copy the runtime descriptor path",
        ));
    }
    let descriptor_path = state
        .server
        .lock()
        .map_err(|_| {
            Fault::new(
                "HOST_UNAVAILABLE",
                "runtime descriptor state is unavailable",
            )
        })?
        .as_ref()
        .map(|server| server.file.to_string_lossy().into_owned())
        .ok_or_else(|| Fault::new("HOST_UNAVAILABLE", "runtime descriptor is unavailable"))?;
    app.clipboard()
        .write_text(descriptor_path)
        .map_err(|error| Fault::new("CLIPBOARD_FAILED", error.to_string()))
}

fn manager_descriptor_copy_allowed(world_id: Uuid, manager_world_id: Uuid, system: bool) -> bool {
    system && world_id == manager_world_id
}

#[cfg(test)]
mod descriptor_copy_tests {
    use super::manager_descriptor_copy_allowed;
    use uuid::Uuid;

    #[test]
    fn only_the_internal_manager_world_can_request_descriptor_copy() {
        let manager = Uuid::new_v4();
        assert!(manager_descriptor_copy_allowed(manager, manager, true));
        assert!(!manager_descriptor_copy_allowed(
            Uuid::new_v4(),
            manager,
            true
        ));
        assert!(!manager_descriptor_copy_allowed(manager, manager, false));
    }
}

#[cfg(test)]
mod locale_tests {
    use super::{load_locale, save_locale};
    use uuid::Uuid;

    #[test]
    fn local_locale_preference_is_validated_and_rebuildable() {
        let path = std::env::temp_dir()
            .join(format!("wincraft-locale-{}", Uuid::new_v4()))
            .join("ui-locale.txt");
        assert_eq!(load_locale(&path), "zh-CN");
        save_locale(&path, "en-US").expect("locale preference saves");
        assert_eq!(load_locale(&path), "en-US");
        save_locale(&path, "fr-FR").expect("malformed preference fixture writes");
        assert_eq!(load_locale(&path), "zh-CN");
        let _ = std::fs::remove_file(&path);
        if let Some(parent) = path.parent() {
            let _ = std::fs::remove_dir(parent);
        }
    }
}
#[tauri::command]
fn surface_interact(
    window: WebviewWindow,
    state: tauri::State<'_, DesktopState>,
    node_id: String,
    value: Value,
    source: InteractionSource,
    expected_revision: u64,
) -> Result<Uuid, Fault> {
    state.hub.interact_with_source_with_native_window_action(
        caller_world(&window)?,
        &node_id,
        value,
        source,
        expected_revision,
        |target| {
            windows::perform_external_window_action(target)
                .map_err(|message| Fault::new("NATIVE_ERROR", message))
        },
    )
}
#[tauri::command]
fn surface_drag(
    window: WebviewWindow,
    state: tauri::State<'_, DesktopState>,
    drag_source: String,
) -> Result<(), Fault> {
    let s = state.hub.renderer_snapshot(caller_world(&window)?)?;
    validate_drag_request(
        &drag_source,
        s.window.effective_position_control(),
        s.window.click_through,
        s.window.background_drag_enabled,
    )?;
    window
        .start_dragging()
        .map_err(|e| Fault::new("NATIVE_ERROR", e.to_string()))
}

fn validate_drag_request(
    drag_source: &str,
    position_control: GeometryControl,
    click_through: bool,
    background_drag_enabled: bool,
) -> Result<(), Fault> {
    let source_allowed = match drag_source {
        "titlebar" => true,
        "background" => background_drag_enabled,
        _ => return Err(Fault::new("INVALID_PARAMS", "unknown window drag source")),
    };
    if !source_allowed || position_control != GeometryControl::Human || click_through {
        return Err(Fault::new(
            "FORBIDDEN",
            "window dragging is disabled by the current configuration",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod drag_permission_tests {
    use super::validate_drag_request;
    use wincraft_core::GeometryControl;

    #[test]
    fn titlebar_and_background_drag_use_their_own_permissions() {
        assert!(validate_drag_request("titlebar", GeometryControl::Human, false, false).is_ok());
        assert!(validate_drag_request("background", GeometryControl::Human, false, true).is_ok());
        assert_eq!(
            validate_drag_request("background", GeometryControl::Human, false, false)
                .unwrap_err()
                .code,
            "FORBIDDEN"
        );
        assert_eq!(
            validate_drag_request("background", GeometryControl::Provider, false, true)
                .unwrap_err()
                .code,
            "FORBIDDEN"
        );
        assert_eq!(
            validate_drag_request("titlebar", GeometryControl::Human, true, true)
                .unwrap_err()
                .code,
            "FORBIDDEN"
        );
        assert_eq!(
            validate_drag_request("unknown", GeometryControl::Human, false, true)
                .unwrap_err()
                .code,
            "INVALID_PARAMS"
        );
    }
}
#[tauri::command]
fn surface_close(
    window: WebviewWindow,
    state: tauri::State<'_, DesktopState>,
) -> Result<(), Fault> {
    let id = caller_world(&window)?;
    if id == state.manager.world_id {
        state
            .hub
            .apply_state_change(id, EventSource::Human, None, |core| {
                core.operator_visibility(state.manager.session, id, false)?;
                Ok(true)
            })?;
    } else {
        let members = state
            .hub
            .lock()
            .operator_destroy(state.manager.session, id)?;
        state.hub.deleted(id, members);
    }
    Ok(())
}

#[tauri::command]
fn surface_minimize(
    window: WebviewWindow,
    state: tauri::State<'_, DesktopState>,
) -> Result<(), Fault> {
    let id = caller_world(&window)?;
    state
        .hub
        .apply_state_change(id, EventSource::Human, None, |core| {
            core.operator_visibility(state.manager.session, id, false)?;
            Ok(true)
        })?;
    Ok(())
}

#[tauri::command]
fn surface_content_size(
    window: WebviewWindow,
    content_fit: tauri::State<'_, windows::ContentFitState>,
    collapsed: bool,
    width: Option<f64>,
    height: Option<f64>,
) -> Result<(), Fault> {
    let id = caller_world(&window)?;
    let current_size = window
        .inner_size()
        .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;
    let scale = window
        .scale_factor()
        .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;

    let target_size = if collapsed {
        let width = width.ok_or_else(|| {
            Fault::new(
                "INVALID_CONTENT_SIZE",
                "collapsed titlebar width is required",
            )
        })?;
        let height = height.ok_or_else(|| {
            Fault::new(
                "INVALID_CONTENT_SIZE",
                "collapsed titlebar height is required",
            )
        })?;
        if !width.is_finite()
            || !(0.0..=10_000.0).contains(&width)
            || !height.is_finite()
            || !(0.0..=10_000.0).contains(&height)
        {
            return Err(Fault::new(
                "INVALID_CONTENT_SIZE",
                "collapsed content size must be finite and bounded",
            ));
        }

        let monitor = window
            .current_monitor()
            .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;
        let work_area = monitor.as_ref().map(|value| value.work_area());
        let work_width = work_area
            .as_ref()
            .map(|area| f64::from(area.size.width) / scale)
            .unwrap_or(2_400.0);
        let work_height = work_area
            .as_ref()
            .map(|area| f64::from(area.size.height) / scale)
            .unwrap_or(1_800.0);
        let target = (
            windows::bounded_content_width(width, work_width),
            windows::bounded_content_height(height, work_height),
        );
        content_fit.set_collapsed_size(
            id,
            (
                f64::from(current_size.width) / scale,
                f64::from(current_size.height) / scale,
            ),
            target,
        );
        target
    } else {
        let Some(expanded) = content_fit.restore_expanded_size(id) else {
            return Ok(());
        };
        expanded
    };

    content_fit.expect_height(id, target_size.1);
    window
        .set_size(LogicalSize::new(target_size.0, target_size.1))
        .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;

    let monitor = window
        .current_monitor()
        .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;
    let work_area = monitor.as_ref().map(|monitor| monitor.work_area());
    if let (Some(area), Ok(position)) = (work_area, window.outer_position()) {
        let target_width = (target_size.0 * scale).ceil() as i32;
        let target_height = (target_size.1 * scale).ceil() as i32;
        let work_right = area.position.x.saturating_add(area.size.width as i32);
        let work_bottom = area.position.y.saturating_add(area.size.height as i32);
        let x = if position.x.saturating_add(target_width) > work_right {
            work_right.saturating_sub(target_width).max(area.position.x)
        } else {
            position.x
        };
        let y = if position.y.saturating_add(target_height) > work_bottom {
            work_bottom
                .saturating_sub(target_height)
                .max(area.position.y)
        } else {
            position.y
        };
        if (x, y) != (position.x, position.y) {
            window
                .set_position(PhysicalPosition::new(x, y))
                .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;
        }
    }
    Ok(())
}

#[tauri::command]
fn surface_content_height(
    window: WebviewWindow,
    state: tauri::State<'_, DesktopState>,
    content_fit: tauri::State<'_, windows::ContentFitState>,
    height: f64,
    force: bool,
) -> Result<(), Fault> {
    let id = caller_world(&window)?;
    if !height.is_finite() || !(50.0..=10_000.0).contains(&height) {
        return Err(Fault::new(
            "INVALID_CONTENT_SIZE",
            "content height outside safe bounds",
        ));
    }
    let snapshot = state.hub.renderer_snapshot(id)?;
    if snapshot.window.geometry_control != GeometryControl::Human
        || (!force && !content_fit.enabled(id))
    {
        return Ok(());
    }

    let scale = window
        .scale_factor()
        .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;
    let monitor = window
        .current_monitor()
        .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;
    let work_area = monitor.as_ref().map(|value| value.work_area());
    let screen_height = work_area
        .as_ref()
        .map(|area| f64::from(area.size.height) / scale)
        .unwrap_or(1800.0);
    let target_height = windows::bounded_content_height(height, screen_height);
    let current_size = window
        .inner_size()
        .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;
    let current_width = f64::from(current_size.width) / scale;
    let current_height = f64::from(current_size.height) / scale;
    if (current_height - target_height).abs() <= 1.0 {
        return Ok(());
    }

    content_fit.expect_height(id, target_height);
    window
        // Preserve the native width even if its resize event has not yet synchronized
        // the new human geometry into the Engine snapshot.
        .set_size(LogicalSize::new(current_width, target_height))
        .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;

    // Preserve the user's horizontal placement and keep an auto-grown window within
    // the work area when it was previously near the bottom edge.
    if let (Some(area), Ok(position)) = (work_area, window.outer_position()) {
        let target_physical_height = (target_height * scale).ceil() as i32;
        let work_bottom = area.position.y.saturating_add(area.size.height as i32);
        let bottom = position.y.saturating_add(target_physical_height);
        if bottom > work_bottom {
            let y = work_bottom
                .saturating_sub(target_physical_height)
                .max(area.position.y);
            window
                .set_position(PhysicalPosition::new(position.x, y))
                .map_err(|error| Fault::new("NATIVE_ERROR", error.to_string()))?;
        }
    }
    Ok(())
}

fn main() {
    // Keep the tray-only default, but let local integration runs open the built-in
    // manager without needing to synthesize a notification-area click.
    let open_manager_on_start = std::env::args().any(|argument| argument == "--open-manager");
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_clipboard_manager::init())
        .invoke_handler(tauri::generate_handler![
            surface_snapshot,
            surface_locale_get,
            surface_locale_set,
            surface_copy_descriptor,
            surface_interact,
            surface_drag,
            surface_close,
            surface_minimize,
            surface_content_size,
            surface_content_height
        ])
        .setup(move |app| {
            let app_local_data = app.path().app_local_data_dir()?;
            let runtime_dir = app_local_data.join("runtime");
            let provider_store = app_local_data.join("providers");
            let locale_path = app_local_data.join("ui-locale.txt");
            let bind: SocketAddr = std::env::var("WINCRAFT_BIND")
                .unwrap_or_else(|_| "127.0.0.1:0".into())
                .parse()?;
            let hub = Hub::new(EXTERNAL_WINDOW_ACTIONS_AVAILABLE);
            hub.set_locale(&load_locale(&locale_path))
                .map_err(std::io::Error::other)?;
            let (server, manager) = tauri::async_runtime::block_on(async {
                let server = wincraft_server::start(hub.clone(), bind, &runtime_dir).await?;
                let manager = ManagerProvider::install(&hub).map_err(std::io::Error::other)?;
                Ok::<_, std::io::Error>((server, manager))
            })?;
            let descriptor_path = server.file.to_string_lossy().into_owned();
            let provider_launcher =
                Arc::new(TauriProviderBundleLauncher::new(provider_store.clone()));
            app.manage(DesktopState {
                hub: hub.clone(),
                manager: manager.clone(),
                tray_visibility: windows::TrayVisibilityState::default(),
                locale_path,
                provider_launcher: provider_launcher.clone(),
                server: Mutex::new(Some(server)),
            });
            app.handle()
                .plugin(tauri_plugin_global_shortcut::Builder::new().build())?;
            let shortcut_manager = manager.clone();
            let shortcut_hub = hub.clone();
            let manager_provider_launcher: Arc<dyn ProviderBundleLauncher> =
                provider_launcher.clone();
            let shortcut_host = Arc::new(TauriShortcutHost {
                app: app.handle().clone(),
                registered: Mutex::new(BTreeSet::new()),
            });
            tauri::async_runtime::spawn(async move {
                shortcut_manager.spawn_with_desktop_hosts(
                    shortcut_hub,
                    descriptor_path,
                    shortcut_host,
                    manager_provider_launcher,
                    provider_store,
                );
            });
            let content_fit = windows::ContentFitState::default();
            app.manage(content_fit.clone());
            let tray_visibility = app.state::<DesktopState>().tray_visibility.clone();
            windows::install_tray(app.handle())?;
            windows::supervise(
                app.handle().clone(),
                hub.clone(),
                manager.clone(),
                runtime_dir.join("native.log"),
                content_fit,
                tray_visibility.clone(),
            );
            if open_manager_on_start {
                windows::activate_manager(app.handle().clone(), hub, manager, tray_visibility);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("WinCraft startup failed");
    app.run(|handle, event| {
        match event {
            tauri::RunEvent::Exit => {
                let _ = handle.global_shortcut().unregister_all();
                handle.state::<DesktopState>().provider_launcher.shutdown();
            }
            tauri::RunEvent::ExitRequested { api, code, .. } if code.is_none() => {
                // Last world closing must not terminate the tray host. Explicit tray Exit has Some(code).
                api.prevent_exit();
            }
            _ => {}
        }
    });
}

#[cfg(test)]
mod platform_capability_tests {
    use super::EXTERNAL_WINDOW_ACTIONS_AVAILABLE;
    use wincraft_server::Hub;

    #[test]
    fn external_window_action_capabilities_match_the_compiled_host() {
        let capabilities = Hub::new(EXTERNAL_WINDOW_ACTIONS_AVAILABLE).capabilities();
        let button_features = capabilities["button_features"]
            .as_array()
            .expect("button feature capabilities are an array");
        assert_eq!(
            capabilities["native_windows"].as_bool(),
            Some(EXTERNAL_WINDOW_ACTIONS_AVAILABLE)
        );
        assert_eq!(
            button_features
                .iter()
                .any(|feature| feature == "external_window_actions"),
            EXTERNAL_WINDOW_ACTIONS_AVAILABLE
        );
        assert_eq!(
            button_features
                .iter()
                .any(|feature| feature == "codex_thread_navigation"),
            cfg!(windows)
        );
    }
}
