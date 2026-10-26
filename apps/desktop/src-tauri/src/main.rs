#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod windows;
use serde_json::Value;
use std::{net::SocketAddr, sync::Mutex};
use tauri::{LogicalSize, Manager, PhysicalPosition, WebviewWindow};
use uuid::Uuid;
use wincraft_core::{Fault, GeometryControl, Snapshot};
use wincraft_server::{self_provider::ManagerProvider, Hub, RunningServer};

pub struct DesktopState {
    pub hub: Hub,
    pub manager: ManagerProvider,
    // Keeps the descriptor guard alive. It removes only this host's credential file on normal exit.
    pub server: Mutex<Option<RunningServer>>,
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
fn surface_interact(
    window: WebviewWindow,
    state: tauri::State<'_, DesktopState>,
    node_id: String,
    value: Value,
    context_action: bool,
    expected_revision: u64,
) -> Result<Uuid, Fault> {
    state.hub.interact(
        caller_world(&window)?,
        &node_id,
        value,
        context_action,
        expected_revision,
    )
}
#[tauri::command]
fn surface_drag(window: WebviewWindow, state: tauri::State<'_, DesktopState>) -> Result<(), Fault> {
    let s = state.hub.renderer_snapshot(caller_world(&window)?)?;
    if s.window.geometry_control != GeometryControl::Human || s.window.click_through {
        return Err(Fault::new("FORBIDDEN", "human drag is not enabled"));
    }
    window
        .start_dragging()
        .map_err(|e| Fault::new("NATIVE_ERROR", e.to_string()))
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
            .lock()
            .operator_visibility(state.manager.session, id, false)?;
        state.hub.changed(id);
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
        .lock()
        .operator_visibility(state.manager.session, id, false)?;
    state.hub.changed(id);
    Ok(())
}

#[tauri::command]
fn surface_content_height(
    window: WebviewWindow,
    state: tauri::State<'_, DesktopState>,
    content_fit: tauri::State<'_, windows::ContentFitState>,
    height: f64,
) -> Result<(), Fault> {
    let id = caller_world(&window)?;
    if !height.is_finite() || !(80.0..=10_000.0).contains(&height) {
        return Err(Fault::new(
            "INVALID_CONTENT_SIZE",
            "content height outside safe bounds",
        ));
    }
    let snapshot = state.hub.renderer_snapshot(id)?;
    if snapshot.window.geometry_control != GeometryControl::Human || !content_fit.enabled(id) {
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
            surface_interact,
            surface_drag,
            surface_close,
            surface_minimize,
            surface_content_height
        ])
        .setup(move |app| {
            let runtime_dir = app.path().app_local_data_dir()?.join("runtime");
            let bind: SocketAddr = std::env::var("WINCRAFT_BIND")
                .unwrap_or_else(|_| "127.0.0.1:0".into())
                .parse()?;
            let hub = Hub::new(true);
            let (server, manager) = tauri::async_runtime::block_on(async {
                let server = wincraft_server::start(hub.clone(), bind, &runtime_dir).await?;
                let manager = ManagerProvider::install(&hub).map_err(std::io::Error::other)?;
                manager.spawn(hub.clone(), server.file.to_string_lossy().into_owned());
                Ok::<_, std::io::Error>((server, manager))
            })?;
            app.manage(DesktopState {
                hub: hub.clone(),
                manager: manager.clone(),
                server: Mutex::new(Some(server)),
            });
            let content_fit = windows::ContentFitState::default();
            app.manage(content_fit.clone());
            windows::install_tray(app.handle())?;
            if open_manager_on_start {
                let _ = manager.show(&hub);
            }
            windows::supervise(
                app.handle().clone(),
                hub,
                manager,
                runtime_dir.join("native.log"),
                content_fit,
            );
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("WinCraft startup failed");
    app.run(|_handle, event| {
        if let tauri::RunEvent::ExitRequested { api, code, .. } = event {
            // Last world closing must not terminate the tray host. Explicit tray Exit has Some(code).
            if code.is_none() {
                api.prevent_exit();
            }
        }
    });
}
