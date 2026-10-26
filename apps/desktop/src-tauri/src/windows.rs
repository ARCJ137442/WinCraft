//! Window adapter derived from ExoMind's overlay lifecycle/placement approach.
//! See reference/exomind/PROVENANCE.md and the retained CCOPL-1.0 license.
use crate::DesktopState;
use std::{
    collections::BTreeMap,
    io::Write,
    path::PathBuf,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tauri::{
    AppHandle, Emitter, LogicalSize, Manager, PhysicalPosition, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder,
};
use uuid::Uuid;
use wincraft_core::{
    geometry::{self, Rect},
    GeometryControl, NativeReport, Position, Snapshot,
};
use wincraft_server::{self_provider::ManagerProvider, Hub};

#[derive(Clone, Default)]
pub struct ContentFitState {
    inner: Arc<Mutex<BTreeMap<Uuid, FitEntry>>>,
}

#[derive(Default)]
struct FitEntry {
    allowed: bool,
    user_resized: bool,
    last_fitted_height: Option<f64>,
    expected_heights: Vec<(f64, Instant)>,
}

impl ContentFitState {
    fn with_entries<T>(&self, f: impl FnOnce(&mut BTreeMap<Uuid, FitEntry>) -> T) -> T {
        let mut entries = self.inner.lock().unwrap_or_else(|error| error.into_inner());
        f(&mut entries)
    }

    pub fn register(&self, id: Uuid, geometry: GeometryControl, initial_height: f64) {
        self.with_entries(|entries| {
            let entry = entries.entry(id).or_insert_with(|| FitEntry {
                allowed: geometry == GeometryControl::Human,
                last_fitted_height: Some(initial_height),
                ..FitEntry::default()
            });
            entry.allowed = geometry == GeometryControl::Human;
        });
    }

    pub fn set_geometry(&self, id: Uuid, geometry: GeometryControl) {
        self.with_entries(|entries| {
            if let Some(entry) = entries.get_mut(&id) {
                entry.allowed = geometry == GeometryControl::Human;
            }
        });
    }

    pub fn enabled(&self, id: Uuid) -> bool {
        self.with_entries(|entries| {
            entries
                .get(&id)
                .map(|entry| entry.allowed && !entry.user_resized)
                .unwrap_or(false)
        })
    }

    pub fn expect_height(&self, id: Uuid, height: f64) {
        self.with_entries(|entries| {
            if let Some(entry) = entries.get_mut(&id) {
                let now = Instant::now();
                entry.expected_heights.retain(|(_, expires)| *expires > now);
                entry
                    .expected_heights
                    .push((height, now + Duration::from_secs(2)));
                if entry.expected_heights.len() > 8 {
                    entry
                        .expected_heights
                        .drain(..entry.expected_heights.len() - 8);
                }
            }
        });
    }

    fn expect_scale_resize(&self, id: Uuid, physical_height: u32, scale_factor: f64) {
        if scale_factor.is_finite() && scale_factor > 0.0 {
            // Tauri reports the OS-suggested physical size before the matching Resized event.
            self.expect_height(id, f64::from(physical_height) / scale_factor);
        }
    }

    /// Returns true when an unanticipated native resize should stop content fitting.
    pub fn observe_resize(&self, id: Uuid, height: f64) -> bool {
        self.with_entries(|entries| {
            let Some(entry) = entries.get_mut(&id) else {
                return false;
            };
            let now = Instant::now();
            entry.expected_heights.retain(|(_, expires)| *expires > now);
            if let Some(index) = entry
                .expected_heights
                .iter()
                .position(|(expected, _)| (expected - height).abs() <= 2.0)
            {
                entry.expected_heights.remove(index);
                entry.last_fitted_height = Some(height);
                return false;
            }
            if entry
                .last_fitted_height
                .is_some_and(|fitted| (fitted - height).abs() <= 2.0)
            {
                // A horizontal-only resize still emits Resized on Windows. Keep
                // content fitting active when the viewport height did not change.
                return false;
            }
            entry.user_resized = true;
            entry.expected_heights.clear();
            true
        })
    }

    pub fn unregister(&self, id: Uuid) {
        self.with_entries(|entries| {
            entries.remove(&id);
        });
    }
}

pub fn bounded_content_height(requested: f64, screen_height: f64) -> f64 {
    let maximum = screen_height.clamp(80.0, 1800.0);
    requested.clamp(80.0, maximum)
}

fn tray_tooltip() -> String {
    format!(
        "WinCraft v{} · {}",
        env!("CARGO_PKG_VERSION"),
        env!("WINCRAFT_BUILD_ID")
    )
}

pub fn install_tray(app: &AppHandle) -> tauri::Result<()> {
    use tauri::{
        menu::{Menu, MenuItem},
        tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    };
    let open = MenuItem::with_id(app, "manager", "打开世界管理器", true, None::<&str>)?;
    let new = MenuItem::with_id(app, "new", "新建空白世界", true, None::<&str>)?;
    let rescue = MenuItem::with_id(
        app,
        "rescue",
        "找回全部窗口（撤销外部写入权）",
        true,
        None::<&str>,
    )?;
    let exit = MenuItem::with_id(app, "exit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &new, &rescue, &exit])?;
    TrayIconBuilder::with_id("wincraft-tray")
        .icon(tauri::image::Image::from_bytes(include_bytes!(
            "../icons/32x32.png"
        ))?)
        .tooltip(tray_tooltip())
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| {
            let state = app.state::<DesktopState>();
            match event.id.as_ref() {
                "manager" => {
                    let _ = state.manager.show(&state.hub);
                }
                "new" => {
                    let _ = state.manager.blank(&state.hub);
                }
                "rescue" => state.manager.rescue_all(&state.hub),
                "exit" => {
                    // Drop current credential file before asking the process to exit.
                    let _ = state.server.lock().map(|mut guard| guard.take());
                    app.exit(0);
                }
                _ => {}
            }
        })
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            ) {
                let app = tray.app_handle();
                let state = app.state::<DesktopState>();
                let _ = state.manager.show(&state.hub);
            }
        })
        .build(app)?;
    Ok(())
}
fn make_window(
    app: &AppHandle,
    s: &Snapshot,
    hub: Hub,
    manager: ManagerProvider,
    content_fit: ContentFitState,
) -> Result<WebviewWindow, String> {
    let label = format!("world-{}", s.id);
    if let Some(w) = app.get_webview_window(&label) {
        content_fit.register(s.id, s.window.geometry_control, s.window.height);
        return Ok(w);
    }
    let builder = WebviewWindowBuilder::new(app, &label, WebviewUrl::App("index.html".into()))
        .title(&s.window.title)
        .inner_size(s.window.width, s.window.height)
        .always_on_top(s.window.always_on_top)
        .decorations(s.window.decorations)
        .shadow(false)
        .skip_taskbar(s.window.skip_taskbar)
        .resizable(s.window.resizable && s.window.geometry_control == GeometryControl::Human)
        .focused(false)
        .visible(false)
        .on_navigation(|url| {
            url.scheme() == "tauri"
                || url.host_str() == Some("tauri.localhost")
                || (url.host_str() == Some("127.0.0.1") && url.port() == Some(1420))
        });
    #[cfg(not(target_os = "macos"))]
    let builder = builder.transparent(true);
    let window = builder.build().map_err(|e| e.to_string())?;
    content_fit.register(s.id, s.window.geometry_control, s.window.height);
    let handle = window.clone();
    let id = s.id;
    let fit_for_event = content_fit.clone();
    window.on_window_event(move |event| match event {
        tauri::WindowEvent::CloseRequested { api, .. } => {
            api.prevent_close();
            if id == manager.world_id {
                let _ = hub.lock().operator_visibility(manager.session, id, false);
                hub.changed(id);
            } else if let Ok(members) = hub.lock().operator_destroy(manager.session, id) {
                hub.deleted(id, members);
            }
        }
        tauri::WindowEvent::Moved(_)
        | tauri::WindowEvent::Resized(_)
        | tauri::WindowEvent::ScaleFactorChanged { .. } => {
            if let tauri::WindowEvent::Resized(size) = event {
                if let Ok(scale) = handle.scale_factor() {
                    fit_for_event.observe_resize(id, f64::from(size.height) / scale);
                }
            }
            if let tauri::WindowEvent::ScaleFactorChanged {
                scale_factor,
                new_inner_size,
                ..
            } = event
            {
                fit_for_event.expect_scale_resize(id, new_inner_size.height, *scale_factor);
            }
            if let (Ok(p), Ok(size), Ok(scale)) = (
                handle.outer_position(),
                handle.inner_size(),
                handle.scale_factor(),
            ) {
                let changed = hub.lock().observe_geometry(
                    id,
                    Position { x: p.x, y: p.y },
                    f64::from(size.width) / scale,
                    f64::from(size.height) / scale,
                );
                if changed {
                    hub.changed(id);
                }
            }
        }
        _ => {}
    });
    Ok(window)
}
fn place_visible(app: &AppHandle, w: &WebviewWindow, s: &Snapshot) -> Result<(), String> {
    let size = w.inner_size().map_err(|e| e.to_string())?;
    let monitors = app.available_monitors().map_err(|e| e.to_string())?;
    if let Some(p) = &s.window.position {
        let rect = Rect {
            x: p.x,
            y: p.y,
            width: size.width,
            height: size.height,
        };
        let visible = !geometry::hidden_sentinel(p.x, p.y)
            && monitors.iter().any(|m| {
                let a = m.work_area();
                geometry::intersects(
                    rect,
                    Rect {
                        x: a.position.x,
                        y: a.position.y,
                        width: a.size.width,
                        height: a.size.height,
                    },
                )
            });
        if visible || monitors.is_empty() {
            return w
                .set_position(PhysicalPosition::new(p.x, p.y))
                .map_err(|e| e.to_string());
        }
    }
    let monitor = app
        .primary_monitor()
        .map_err(|e| e.to_string())?
        .or_else(|| monitors.first().cloned());
    if let Some(m) = monitor {
        let a = m.work_area();
        let (x, y) = geometry::bottom_right(
            Rect {
                x: a.position.x,
                y: a.position.y,
                width: a.size.width,
                height: a.size.height,
            },
            size.width,
            size.height,
        );
        w.set_position(PhysicalPosition::new(x, y))
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}
fn apply(
    app: &AppHandle,
    w: &WebviewWindow,
    s: &Snapshot,
    content_fit: &ContentFitState,
) -> Result<(), String> {
    macro_rules! native {
        ($e:expr) => {
            $e.map_err(|e| e.to_string())?
        };
    }
    native!(w.set_title(&s.window.title));
    native!(w.set_always_on_top(s.window.always_on_top));
    native!(w.set_decorations(s.window.decorations));
    native!(w.set_skip_taskbar(s.window.skip_taskbar));
    native!(
        w.set_resizable(s.window.resizable && s.window.geometry_control == GeometryControl::Human)
    );
    content_fit.expect_height(s.id, s.window.height);
    native!(w.set_size(LogicalSize::new(s.window.width, s.window.height)));
    place_visible(app, w, s)?;
    native!(w.set_ignore_cursor_events(s.window.click_through));
    if s.window.visible {
        native!(w.show());
    } else {
        native!(w.hide());
    }
    Ok(())
}
struct Entry {
    window: WebviewWindow,
    applied: u64,
    last_sequence: u64,
    last_attempt: Instant,
    attempted: u64,
}
pub fn supervise(
    app: AppHandle,
    hub: Hub,
    manager: ManagerProvider,
    log: PathBuf,
    content_fit: ContentFitState,
) {
    tauri::async_runtime::spawn(async move {
        let mut entries: BTreeMap<Uuid, Entry> = BTreeMap::new();
        let mut failed_create: BTreeMap<Uuid, Instant> = BTreeMap::new();
        let mut timer = tokio::time::interval(Duration::from_millis(50));
        loop {
            timer.tick().await;
            let snapshots = hub.snapshots();
            let remove: Vec<_> = entries
                .keys()
                .filter(|id| !snapshots.iter().any(|s| s.id == **id))
                .copied()
                .collect();
            for id in remove {
                if let Some(entry) = entries.remove(&id) {
                    let _ = entry.window.destroy();
                }
                content_fit.unregister(id);
                failed_create.remove(&id);
            }
            for s in snapshots {
                content_fit.set_geometry(s.id, s.window.geometry_control);
                if let std::collections::btree_map::Entry::Vacant(vacant) = entries.entry(s.id) {
                    if !s.window.visible {
                        continue;
                    }
                    if failed_create
                        .get(&s.id)
                        .map(|t| t.elapsed() < Duration::from_secs(2))
                        .unwrap_or(false)
                    {
                        continue;
                    }
                    match make_window(&app, &s, hub.clone(), manager.clone(), content_fit.clone()) {
                        Ok(window) => {
                            vacant.insert(Entry {
                                window,
                                applied: 0,
                                last_sequence: 0,
                                last_attempt: Instant::now() - Duration::from_secs(3),
                                attempted: 0,
                            });
                            failed_create.remove(&s.id);
                        }
                        Err(error) => {
                            record_failure(&hub, &s, &log, &error);
                            failed_create.insert(s.id, Instant::now());
                            continue;
                        }
                    }
                }
                let entry = entries.get_mut(&s.id).unwrap();
                // Native-origin human geometry is already applied: do not echo it back while dragging.
                if s.native.applied_window_revision == Some(s.window_revision) {
                    entry.applied = s.window_revision;
                }
                if entry.applied != s.window_revision
                    && (entry.attempted != s.window_revision
                        || entry.last_attempt.elapsed() > Duration::from_secs(2))
                {
                    entry.last_attempt = Instant::now();
                    entry.attempted = s.window_revision;
                    match apply(&app, &entry.window, &s, &content_fit) {
                        Ok(()) => {
                            entry.applied = s.window_revision;
                            let report = NativeReport {
                                state: "applied".into(),
                                applied_window_revision: Some(s.window_revision),
                                error: None,
                            };
                            let changed = hub.lock().native_report(s.id, s.window_revision, report);
                            if changed {
                                hub.changed(s.id);
                            }
                        }
                        Err(error) => record_failure(&hub, &s, &log, &error),
                    }
                }
                if s.sequence > entry.last_sequence {
                    // Target one world label; never broadcast private scenes to every WebView.
                    if app
                        .emit_to(format!("world-{}", s.id), "world/snapshot", s.clone())
                        .is_ok()
                    {
                        entry.last_sequence = s.sequence;
                    }
                }
            }
        }
    });
}
fn record_failure(hub: &Hub, s: &Snapshot, log: &PathBuf, error: &str) {
    let report = NativeReport {
        state: "error".into(),
        applied_window_revision: None,
        error: Some(error.into()),
    };
    let changed = hub.lock().native_report(s.id, s.window_revision, report);
    if changed {
        hub.changed(s.id);
    }
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log)
    {
        let _ = writeln!(
            f,
            "{} world={} window_revision={} error={}",
            hub.now(),
            s.id,
            s.window_revision,
            error
        );
    }
}

#[cfg(test)]
mod content_fit_tests {
    use super::*;

    #[test]
    fn expected_native_resize_keeps_content_fit_enabled() {
        let fit = ContentFitState::default();
        let id = Uuid::new_v4();
        fit.register(id, GeometryControl::Human, 640.0);
        fit.expect_height(id, 720.0);

        assert!(!fit.observe_resize(id, 720.5));
        assert!(fit.enabled(id));
    }

    #[test]
    fn human_resize_disables_future_content_fit() {
        let fit = ContentFitState::default();
        let id = Uuid::new_v4();
        fit.register(id, GeometryControl::Human, 600.0);

        assert!(fit.observe_resize(id, 640.0));
        assert!(!fit.enabled(id));
        fit.set_geometry(id, GeometryControl::Provider);
        fit.set_geometry(id, GeometryControl::Human);
        assert!(!fit.enabled(id));
    }

    #[test]
    fn dpi_rescale_keeps_fit_enabled_and_later_human_resize_disables_it() {
        let fit = ContentFitState::default();
        let id = Uuid::new_v4();
        fit.register(id, GeometryControl::Human, 600.0);
        fit.expect_scale_resize(id, 900, 1.5);

        assert!(!fit.observe_resize(id, 600.0));
        assert!(fit.enabled(id));
        assert!(fit.observe_resize(id, 560.0));
        assert!(!fit.enabled(id));
    }

    #[test]
    fn content_height_is_bounded_by_protocol_and_work_area() {
        assert_eq!(bounded_content_height(900.0, 800.0), 800.0);
        assert_eq!(bounded_content_height(500.0, 800.0), 500.0);
        assert_eq!(bounded_content_height(2_000.0, 3_000.0), 1_800.0);
        assert_eq!(bounded_content_height(100.0, 60.0), 80.0);
    }

    #[test]
    fn internal_manager_is_eligible_for_default_content_fit() {
        let hub = Hub::new(true);
        let manager = ManagerProvider::install(&hub).expect("manager world installs");
        let snapshot = hub
            .renderer_snapshot(manager.world_id)
            .expect("manager world is readable by its renderer");
        let fit = ContentFitState::default();

        fit.register(
            snapshot.id,
            snapshot.window.geometry_control,
            snapshot.window.height,
        );

        assert!(snapshot.system);
        assert_eq!(snapshot.window.title, "窗构 · 世界管理器");
        assert!(!snapshot.window.visible);
        assert_eq!(snapshot.window.geometry_control, GeometryControl::Human);
        assert!(fit.enabled(snapshot.id));
    }

    #[test]
    fn horizontal_resize_keeps_content_fit_enabled() {
        let fit = ContentFitState::default();
        let id = Uuid::new_v4();
        fit.register(id, GeometryControl::Human, 600.0);

        assert!(!fit.observe_resize(id, 600.0));
        assert!(fit.enabled(id));
        fit.expect_height(id, 720.0);
        assert!(!fit.observe_resize(id, 720.0));
        assert!(fit.enabled(id));
    }

    #[test]
    fn default_human_window_is_resizable() {
        let window = wincraft_core::WindowSpec::default();

        assert_eq!(window.geometry_control, GeometryControl::Human);
        assert!(window.resizable);
    }

    #[test]
    fn tray_tooltip_identifies_product_version_and_build() {
        let tooltip = tray_tooltip();
        assert!(tooltip.contains(env!("CARGO_PKG_VERSION")));
        assert!(tooltip.contains(env!("WINCRAFT_BUILD_ID")));
    }
}
