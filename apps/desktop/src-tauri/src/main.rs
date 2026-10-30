#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod windows;
use serde_json::Value;
use std::{
    collections::BTreeSet,
    fs,
    net::SocketAddr,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
};
use tauri::{Emitter, LogicalSize, Manager, PhysicalPosition, WebviewWindow};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use uuid::Uuid;
use wincraft_core::{
    EventSource, Fault, GeometryControl, InteractionSource, ShortcutSpec, Snapshot,
};
use wincraft_server::{
    self_provider::{ManagerProvider, ShortcutHost},
    Hub, RunningServer,
};

pub struct DesktopState {
    pub hub: Hub,
    pub manager: ManagerProvider,
    pub tray_visibility: windows::TrayVisibilityState,
    locale_path: PathBuf,
    // Keeps the descriptor guard alive. It removes only this host's credential file on normal exit.
    pub server: Mutex<Option<RunningServer>>,
}

struct TauriShortcutHost {
    app: tauri::AppHandle,
    registered: Mutex<BTreeSet<String>>,
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
        .invoke_handler(tauri::generate_handler![
            surface_snapshot,
            surface_locale_get,
            surface_locale_set,
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
            let locale_path = app_local_data.join("ui-locale.txt");
            let bind: SocketAddr = std::env::var("WINCRAFT_BIND")
                .unwrap_or_else(|_| "127.0.0.1:0".into())
                .parse()?;
            let hub = Hub::new(cfg!(target_os = "windows"));
            hub.set_locale(&load_locale(&locale_path))
                .map_err(std::io::Error::other)?;
            let (server, manager) = tauri::async_runtime::block_on(async {
                let server = wincraft_server::start(hub.clone(), bind, &runtime_dir).await?;
                let manager = ManagerProvider::install(&hub).map_err(std::io::Error::other)?;
                Ok::<_, std::io::Error>((server, manager))
            })?;
            let descriptor_path = server.file.to_string_lossy().into_owned();
            app.manage(DesktopState {
                hub: hub.clone(),
                manager: manager.clone(),
                tray_visibility: windows::TrayVisibilityState::default(),
                locale_path,
                server: Mutex::new(Some(server)),
            });
            app.handle()
                .plugin(tauri_plugin_global_shortcut::Builder::new().build())?;
            let shortcut_manager = manager.clone();
            let shortcut_hub = hub.clone();
            let shortcut_host = Arc::new(TauriShortcutHost {
                app: app.handle().clone(),
                registered: Mutex::new(BTreeSet::new()),
            });
            tauri::async_runtime::spawn(async move {
                shortcut_manager.spawn_with_shortcut_host(
                    shortcut_hub,
                    descriptor_path,
                    shortcut_host,
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
            }
            tauri::RunEvent::ExitRequested { api, code, .. } if code.is_none() => {
                // Last world closing must not terminate the tray host. Explicit tray Exit has Some(code).
                api.prevent_exit();
            }
            _ => {}
        }
    });
}
