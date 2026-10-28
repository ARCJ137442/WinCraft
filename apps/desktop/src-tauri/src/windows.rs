//! Window adapter derived from ExoMind's overlay lifecycle/placement approach.
//! See reference/exomind/PROVENANCE.md and the retained CCOPL-1.0 license.
use crate::DesktopState;
use std::{
    collections::{BTreeMap, BTreeSet},
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
    EventSource, GeometryControl, NativeReport, NativeWindowAction, NativeWindowApplication,
    NativeWindowOperation, Position, Snapshot, WorkAreaAnchor,
};
use wincraft_server::{self_provider::ManagerProvider, Hub};

#[derive(Clone, Default)]
pub struct TrayVisibilityState {
    inner: Arc<Mutex<TrayVisibilityInner>>,
}

#[derive(Default)]
struct TrayVisibilityInner {
    hide_all_active: bool,
    restore_visible: BTreeSet<Uuid>,
    force_visible: BTreeSet<Uuid>,
}

impl TrayVisibilityState {
    fn begin_hide_all(&self, ids: impl IntoIterator<Item = Uuid>) {
        let mut inner = self.inner.lock().unwrap_or_else(|error| error.into_inner());
        inner.hide_all_active = true;
        inner.restore_visible.extend(ids);
        inner.force_visible.clear();
    }

    fn restore_ids(&self) -> BTreeSet<Uuid> {
        self.inner
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .restore_visible
            .clone()
    }

    fn finish_show_all(&self) {
        let mut inner = self.inner.lock().unwrap_or_else(|error| error.into_inner());
        inner.hide_all_active = false;
        inner.restore_visible.clear();
        inner.force_visible.clear();
    }

    pub fn hide_all(&self, app: &AppHandle, hub: &Hub) -> Result<usize, String> {
        let ids: BTreeSet<_> = hub
            .snapshots()
            .into_iter()
            .filter(|snapshot| snapshot.window.visible)
            .map(|snapshot| snapshot.id)
            .collect();
        self.begin_hide_all(ids.iter().copied());

        let mut hidden = 0;
        let mut errors = Vec::new();
        for id in ids {
            if let Some(window) = app.get_webview_window(&format!("world-{id}")) {
                match window.hide() {
                    Ok(()) => hidden += 1,
                    Err(error) => errors.push(format!("world {id}: {error}")),
                }
            }
        }
        if !errors.is_empty() {
            return Err(errors.join("; "));
        }
        Ok(hidden)
    }

    pub fn show_all(&self, app: &AppHandle, hub: &Hub) -> Result<usize, String> {
        let active = self
            .inner
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .hide_all_active;
        let restore = if active {
            self.restore_ids()
        } else {
            hub.snapshots()
                .into_iter()
                .filter(|snapshot| snapshot.window.visible)
                .map(|snapshot| snapshot.id)
                .collect()
        };
        self.finish_show_all();

        let mut shown = 0;
        let mut errors = Vec::new();
        for id in &restore {
            let Ok(snapshot) = hub.renderer_snapshot(*id) else {
                continue;
            };
            if !snapshot.window.visible {
                continue;
            }
            if let Some(window) = app.get_webview_window(&format!("world-{id}")) {
                if let Err(error) = window.unminimize() {
                    errors.push(format!("world {id} unminimize: {error}"));
                    continue;
                }
                match window.show() {
                    Ok(()) => shown += 1,
                    Err(error) => errors.push(format!("world {id} show: {error}")),
                }
            }
        }
        if !errors.is_empty() {
            return Err(errors.join("; "));
        }
        Ok(shown)
    }

    fn make_manager_visible(&self, id: Uuid) {
        let mut inner = self.inner.lock().unwrap_or_else(|error| error.into_inner());
        if inner.hide_all_active {
            inner.restore_visible.insert(id);
            inner.force_visible.insert(id);
        }
    }

    fn should_temporarily_hide(&self, id: Uuid, logical_visible: bool) -> bool {
        let mut inner = self.inner.lock().unwrap_or_else(|error| error.into_inner());
        if !inner.hide_all_active {
            return false;
        }
        if logical_visible {
            inner.restore_visible.insert(id);
        } else {
            inner.restore_visible.remove(&id);
            inner.force_visible.remove(&id);
        }
        !inner.force_visible.contains(&id)
    }

    fn forget(&self, id: Uuid) {
        let mut inner = self.inner.lock().unwrap_or_else(|error| error.into_inner());
        inner.restore_visible.remove(&id);
        inner.force_visible.remove(&id);
    }
}

#[cfg(test)]
mod tray_visibility_tests {
    use super::TrayVisibilityState;
    use uuid::Uuid;

    #[test]
    fn temporary_hide_restores_only_logically_visible_worlds_and_manager_can_override() {
        let state = TrayVisibilityState::default();
        let first = Uuid::new_v4();
        let hidden_by_provider = Uuid::new_v4();
        let manager = Uuid::new_v4();

        state.begin_hide_all([first, hidden_by_provider]);
        assert!(state.should_temporarily_hide(first, true));
        assert!(state.should_temporarily_hide(hidden_by_provider, false));
        state.make_manager_visible(manager);
        assert!(!state.should_temporarily_hide(manager, true));

        let restore = state.restore_ids();
        assert!(restore.contains(&first));
        assert!(!restore.contains(&hidden_by_provider));
        assert!(restore.contains(&manager));
    }

    #[test]
    fn provider_show_and_hide_changes_are_remembered_while_all_windows_are_hidden() {
        let state = TrayVisibilityState::default();
        let id = Uuid::new_v4();
        state.begin_hide_all([id]);
        assert!(state.should_temporarily_hide(id, false));
        assert!(!state.restore_ids().contains(&id));
        assert!(state.should_temporarily_hide(id, true));
        assert!(state.restore_ids().contains(&id));
    }
}

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
    expanded_size: Option<(f64, f64)>,
    collapsed_size: Option<(f64, f64)>,
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

    pub fn set_collapsed_size(
        &self,
        id: Uuid,
        expanded_size: (f64, f64),
        collapsed_size: (f64, f64),
    ) {
        self.with_entries(|entries| {
            let entry = entries.entry(id).or_default();
            if entry.collapsed_size.is_none() {
                entry.expanded_size = Some(expanded_size);
            }
            entry.collapsed_size = Some(collapsed_size);
        });
    }

    pub fn collapsed_size(&self, id: Uuid) -> Option<(f64, f64)> {
        self.with_entries(|entries| entries.get(&id).and_then(|entry| entry.collapsed_size))
    }

    pub fn restore_expanded_size(&self, id: Uuid) -> Option<(f64, f64)> {
        self.with_entries(|entries| {
            let entry = entries.get_mut(&id)?;
            entry.collapsed_size.take()?;
            entry.expanded_size.take()
        })
    }

    pub fn update_expanded_size(&self, id: Uuid, size: (f64, f64)) {
        self.with_entries(|entries| {
            if let Some(entry) = entries.get_mut(&id) {
                if entry.collapsed_size.is_some() {
                    entry.expanded_size = Some(size);
                }
            }
        });
    }
}

pub fn bounded_content_width(requested: f64, work_area_width: f64) -> f64 {
    let maximum = work_area_width.clamp(160.0, 2_400.0);
    requested.clamp(160.0, maximum)
}

pub fn bounded_content_height(requested: f64, screen_height: f64) -> f64 {
    let maximum = screen_height.clamp(50.0, 1800.0);
    requested.clamp(50.0, maximum)
}

fn physical_work_area_anchor(
    anchor: WorkAreaAnchor,
    work_area: Rect,
    window_size: tauri::PhysicalSize<u32>,
    scale_factor: f64,
) -> Result<Position, String> {
    geometry::resolve_work_area_anchor(
        anchor,
        work_area,
        window_size.width,
        window_size.height,
        scale_factor,
    )
    .map_err(|error| error.to_string())
}

fn tray_tooltip() -> String {
    format!(
        "WinCraft v{} · {}",
        env!("CARGO_PKG_VERSION"),
        env!("WINCRAFT_BUILD_ID")
    )
}

fn executable_name_for_application(application: NativeWindowApplication) -> &'static str {
    match application {
        NativeWindowApplication::Obsidian => "obsidian.exe",
        NativeWindowApplication::TrafficMonitor => "TrafficMonitor.exe",
    }
}

fn normalized_title_filter(value: Option<&str>) -> String {
    value.unwrap_or_default().trim().to_lowercase()
}

fn title_matches_filter(title: &str, normalized_filter: &str) -> bool {
    normalized_filter.is_empty() || title.to_lowercase().contains(normalized_filter)
}

fn select_external_window_match_index(
    match_count: usize,
    foreground_index: Option<usize>,
) -> Result<usize, String> {
    match match_count {
        0 => Err("No existing application window matched the configured title filter".into()),
        1 => Ok(0),
        _ => foreground_index
            .filter(|index| *index < match_count)
            .ok_or_else(|| {
                "Multiple existing application windows matched; provide a narrower title filter"
                    .into()
            }),
    }
}

#[cfg(test)]
mod native_window_action_tests {
    use super::{
        executable_name_for_application, normalized_title_filter,
        select_external_window_match_index, title_matches_filter,
    };
    use wincraft_core::NativeWindowApplication;

    #[test]
    fn application_ids_map_only_to_registered_process_images() {
        assert_eq!(
            executable_name_for_application(NativeWindowApplication::Obsidian),
            "obsidian.exe"
        );
        assert_eq!(
            executable_name_for_application(NativeWindowApplication::TrafficMonitor),
            "TrafficMonitor.exe"
        );
    }

    #[test]
    fn title_filter_is_case_insensitive_and_empty_filter_matches_any_title() {
        let filter = normalized_title_filter(Some("  Obsidian Workspace  "));
        assert!(title_matches_filter("Obsidian Workspace · Personal vault", &filter));
        assert!(!title_matches_filter(
            "Daily note · Personal vault",
            &filter
        ));
        assert!(title_matches_filter(
            "Any existing title",
            &normalized_title_filter(None)
        ));
        assert!(title_matches_filter(
            "Any existing title",
            &normalized_title_filter(Some("  "))
        ));
    }

    #[test]
    fn ambiguous_external_windows_are_never_chosen_by_enumeration_order() {
        assert_eq!(select_external_window_match_index(1, None), Ok(0));
        assert_eq!(select_external_window_match_index(3, Some(1)), Ok(1));
        assert!(select_external_window_match_index(0, None)
            .unwrap_err()
            .contains("No existing application window matched"));
        assert!(select_external_window_match_index(3, None)
            .unwrap_err()
            .contains("narrower title filter"));
        assert!(select_external_window_match_index(3, Some(3))
            .unwrap_err()
            .contains("narrower title filter"));
    }
}

#[cfg(windows)]
struct ExternalWindowSearch {
    executable_name: String,
    title_filter: String,
    matches: Vec<windows_sys::Win32::Foundation::HWND>,
}

#[cfg(windows)]
unsafe extern "system" fn collect_external_window(
    hwnd: windows_sys::Win32::Foundation::HWND,
    parameter: windows_sys::Win32::Foundation::LPARAM,
) -> i32 {
    use windows_sys::Win32::{
        Foundation::CloseHandle,
        System::Threading::{
            OpenProcess, QueryFullProcessImageNameW, PROCESS_QUERY_LIMITED_INFORMATION,
        },
        UI::WindowsAndMessaging::{
            GetWindowTextLengthW, GetWindowTextW, GetWindowThreadProcessId, IsWindowVisible,
        },
    };

    if hwnd.is_null() || unsafe { IsWindowVisible(hwnd) } == 0 {
        return 1;
    }
    let title_length = unsafe { GetWindowTextLengthW(hwnd) };
    if title_length <= 0 {
        return 1;
    }
    let mut title_buffer = vec![0u16; (title_length as usize + 1).min(32_768)];
    let copied =
        unsafe { GetWindowTextW(hwnd, title_buffer.as_mut_ptr(), title_buffer.len() as i32) };
    if copied <= 0 {
        return 1;
    }
    let title = String::from_utf16_lossy(&title_buffer[..copied as usize]);
    let search = unsafe { &mut *(parameter as *mut ExternalWindowSearch) };
    if !title_matches_filter(&title, &search.title_filter) {
        return 1;
    }

    let mut process_id = 0u32;
    unsafe { GetWindowThreadProcessId(hwnd, &mut process_id) };
    if process_id == 0 {
        return 1;
    }
    let process = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, process_id) };
    if process.is_null() {
        return 1;
    }
    let mut image_buffer = vec![0u16; 32_768];
    let mut image_length = image_buffer.len() as u32;
    let image_ok = unsafe {
        QueryFullProcessImageNameW(process, 0, image_buffer.as_mut_ptr(), &mut image_length)
    } != 0;
    unsafe { CloseHandle(process) };
    if !image_ok {
        return 1;
    }
    let image = String::from_utf16_lossy(&image_buffer[..image_length as usize]);
    if image
        .rsplit(['\\', '/'])
        .next()
        .is_some_and(|name| name.eq_ignore_ascii_case(&search.executable_name))
    {
        search.matches.push(hwnd);
    }
    1
}

#[cfg(windows)]
fn perform_window_action(action: &NativeWindowAction) -> Result<(), String> {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        BringWindowToTop, EnumWindows, GetForegroundWindow, IsIconic, IsWindow, IsZoomed,
        SetForegroundWindow, ShowWindow, SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE,
    };

    let foreground = unsafe { GetForegroundWindow() };
    let mut search = ExternalWindowSearch {
        executable_name: executable_name_for_application(action.application).into(),
        title_filter: normalized_title_filter(action.title_contains.as_deref()),
        matches: Vec::new(),
    };
    unsafe {
        EnumWindows(
            Some(collect_external_window),
            &mut search as *mut ExternalWindowSearch as isize,
        );
    }
    let foreground_index = search
        .matches
        .iter()
        .position(|window| *window == foreground);
    let selected_index =
        select_external_window_match_index(search.matches.len(), foreground_index)?;
    let hwnd = search.matches[selected_index];
    unsafe {
        if IsWindow(hwnd) == 0 {
            return Err(
                "The matching application window closed before the action completed".into(),
            );
        }
        match action.operation {
            NativeWindowOperation::Activate => {
                if IsIconic(hwnd) != 0 {
                    ShowWindow(hwnd, SW_RESTORE);
                }
                BringWindowToTop(hwnd);
                if SetForegroundWindow(hwnd) == 0 && GetForegroundWindow() != hwnd {
                    return Err(
                        "Windows did not allow activating the matching application window".into(),
                    );
                }
            }
            NativeWindowOperation::Maximize => {
                ShowWindow(hwnd, SW_MAXIMIZE);
                if IsZoomed(hwnd) == 0 {
                    return Err("Windows did not maximize the matching application window".into());
                }
            }
            NativeWindowOperation::Restore => {
                ShowWindow(hwnd, SW_RESTORE);
                if IsIconic(hwnd) != 0 {
                    return Err("Windows did not restore the matching application window".into());
                }
            }
            NativeWindowOperation::Minimize => {
                ShowWindow(hwnd, SW_MINIMIZE);
                if IsIconic(hwnd) == 0 {
                    return Err("Windows did not minimize the matching application window".into());
                }
            }
        }
    }
    Ok(())
}

pub fn perform_external_window_action(action: &NativeWindowAction) -> Result<(), String> {
    #[cfg(windows)]
    {
        perform_window_action(action)
    }
    #[cfg(not(windows))]
    {
        let _ = action;
        Err("Native external window actions are unsupported on this platform".into())
    }
}

pub fn activate_manager(
    app: AppHandle,
    hub: Hub,
    manager: ManagerProvider,
    tray_visibility: TrayVisibilityState,
) {
    if let Err(error) = manager.show(&hub) {
        eprintln!("could not show manager world: {error}");
        return;
    }
    tray_visibility.make_manager_visible(manager.world_id);
    let label = format!("world-{}", manager.world_id);
    tauri::async_runtime::spawn(async move {
        for _ in 0..40 {
            if let Some(window) = app.get_webview_window(&label) {
                if let Err(error) = window.unminimize() {
                    eprintln!("could not unminimize manager window: {error}");
                }
                if let Err(error) = window.show() {
                    eprintln!("could not show manager window: {error}");
                    return;
                }
                tokio::time::sleep(Duration::from_millis(50)).await;
                if let Err(error) = window.set_focus() {
                    eprintln!("could not focus manager window: {error}");
                }
                return;
            }
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        eprintln!("manager world became visible but its native window was not created");
    });
}

pub fn install_tray(app: &AppHandle) -> tauri::Result<()> {
    use tauri::{
        menu::{Menu, MenuItem},
        tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    };
    let open = MenuItem::with_id(app, "manager", "显示世界管理器", true, None::<&str>)?;
    let new = MenuItem::with_id(app, "new", "新建空白世界", true, None::<&str>)?;
    let hide_all = MenuItem::with_id(app, "hide-all", "暂时隐藏全部窗口", true, None::<&str>)?;
    let show_all = MenuItem::with_id(app, "show-all", "显示全部窗口", true, None::<&str>)?;
    let rescue = MenuItem::with_id(
        app,
        "rescue",
        "找回全部窗口（撤销外部写入权）",
        true,
        None::<&str>,
    )?;
    let exit = MenuItem::with_id(app, "exit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &new, &hide_all, &show_all, &rescue, &exit])?;
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
                    activate_manager(
                        app.clone(),
                        state.hub.clone(),
                        state.manager.clone(),
                        state.tray_visibility.clone(),
                    );
                }
                "new" => {
                    let _ = state.manager.blank(&state.hub);
                }
                "hide-all" => {
                    if let Err(error) = state.tray_visibility.hide_all(app, &state.hub) {
                        eprintln!("hide all windows: {error}");
                    }
                }
                "show-all" => {
                    if let Err(error) = state.tray_visibility.show_all(app, &state.hub) {
                        eprintln!("show all windows: {error}");
                    }
                }
                "rescue" => {
                    if let Err(error) = state.tray_visibility.show_all(app, &state.hub) {
                        eprintln!("restore windows before rescue: {error}");
                    }
                    state.manager.rescue_all(&state.hub);
                }
                "exit" => {
                    let server = state.server.lock().ok().and_then(|mut guard| guard.take());
                    let app = app.clone();
                    tauri::async_runtime::spawn(async move {
                        if let Some(server) = server {
                            server.shutdown().await;
                        }
                        app.exit(0);
                    });
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
                activate_manager(
                    app.clone(),
                    state.hub.clone(),
                    state.manager.clone(),
                    state.tray_visibility.clone(),
                );
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
                let _ = hub.apply_state_change(id, EventSource::Human, None, |core| {
                    core.operator_visibility(manager.session, id, false)?;
                    Ok(true)
                });
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
                let (width, height) = if fit_for_event.collapsed_size(id).is_some() {
                    hub.renderer_snapshot(id)
                        .map(|snapshot| (snapshot.window.width, snapshot.window.height))
                        .unwrap_or((
                            f64::from(size.width) / scale,
                            f64::from(size.height) / scale,
                        ))
                } else {
                    (
                        f64::from(size.width) / scale,
                        f64::from(size.height) / scale,
                    )
                };
                let source = if matches!(event, tauri::WindowEvent::ScaleFactorChanged { .. }) {
                    EventSource::System
                } else {
                    EventSource::Human
                };
                let _ = hub.apply_state_change(id, source, None, |core| {
                    Ok(core.observe_geometry(id, Position { x: p.x, y: p.y }, width, height))
                });
            }
        }
        _ => {}
    });
    Ok(window)
}
fn place_visible(app: &AppHandle, w: &WebviewWindow, s: &Snapshot) -> Result<(), String> {
    let size = w.inner_size().map_err(|e| e.to_string())?;
    let monitors = app.available_monitors().map_err(|e| e.to_string())?;
    if let Some(anchor) = s.window.anchor {
        let current_monitor = w.current_monitor().map_err(|error| error.to_string())?;
        let positioned_monitor = if let Some(position) = &s.window.position {
            monitors.iter().find(|monitor| {
                let area = monitor.work_area();
                geometry::intersects(
                    Rect {
                        x: position.x,
                        y: position.y,
                        width: size.width,
                        height: size.height,
                    },
                    Rect {
                        x: area.position.x,
                        y: area.position.y,
                        width: area.size.width,
                        height: area.size.height,
                    },
                )
            })
        } else {
            None
        };
        let monitor = current_monitor
            .or_else(|| positioned_monitor.cloned())
            .or(app.primary_monitor().map_err(|error| error.to_string())?)
            .or_else(|| monitors.first().cloned());
        if let Some(monitor) = monitor {
            let work = monitor.work_area();
            let position = physical_work_area_anchor(
                anchor,
                Rect {
                    x: work.position.x,
                    y: work.position.y,
                    width: work.size.width,
                    height: work.size.height,
                },
                size,
                monitor.scale_factor(),
            )?;
            return w
                .set_position(PhysicalPosition::new(position.x, position.y))
                .map_err(|error| error.to_string());
        }
        return Err("No monitor is available to resolve the work-area anchor".into());
    }
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
    tray_visibility: &TrayVisibilityState,
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
    if s.window.geometry_control == GeometryControl::Provider {
        content_fit.update_expanded_size(s.id, (s.window.width, s.window.height));
    }
    let (width, height) = content_fit
        .collapsed_size(s.id)
        .unwrap_or((s.window.width, s.window.height));
    content_fit.expect_height(s.id, height);
    native!(w.set_size(LogicalSize::new(width, height)));
    place_visible(app, w, s)?;
    native!(w.set_ignore_cursor_events(s.window.click_through));
    if s.window.visible && !tray_visibility.should_temporarily_hide(s.id, true) {
        native!(w.show());
    } else {
        if !s.window.visible {
            tray_visibility.should_temporarily_hide(s.id, false);
        }
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
    tray_visibility: TrayVisibilityState,
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
                tray_visibility.forget(id);
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
                    match apply(&app, &entry.window, &s, &content_fit, &tray_visibility) {
                        Ok(()) => {
                            entry.applied = s.window_revision;
                            let report = NativeReport {
                                state: "applied".into(),
                                applied_window_revision: Some(s.window_revision),
                                error: None,
                            };
                            let _ = hub.apply_state_change(s.id, EventSource::Host, None, |core| {
                                Ok(core.native_report(s.id, s.window_revision, report))
                            });
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
    let _ = hub.apply_state_change(s.id, EventSource::Host, None, |core| {
        Ok(core.native_report(s.id, s.window_revision, report))
    });
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
        assert_eq!(bounded_content_height(51.0, 60.0), 51.0);
        assert_eq!(bounded_content_height(20.0, 600.0), 50.0);
    }

    #[test]
    fn content_width_is_bounded_by_protocol_and_work_area() {
        assert_eq!(bounded_content_width(120.0, 1_000.0), 160.0);
        assert_eq!(bounded_content_width(300.0, 1_000.0), 300.0);
        assert_eq!(bounded_content_width(3_000.0, 1_000.0), 1_000.0);
        assert_eq!(bounded_content_width(2_800.0, 3_000.0), 2_400.0);
    }

    #[test]
    fn collapsed_window_restores_its_expanded_size_after_a_compact_update() {
        let fit = ContentFitState::default();
        let id = Uuid::new_v4();
        fit.register(id, GeometryControl::Human, 600.0);
        fit.set_collapsed_size(id, (480.0, 600.0), (236.0, 50.0));
        fit.set_collapsed_size(id, (480.0, 600.0), (248.0, 50.0));

        assert_eq!(fit.collapsed_size(id), Some((248.0, 50.0)));
        assert_eq!(fit.restore_expanded_size(id), Some((480.0, 600.0)));
        assert_eq!(fit.collapsed_size(id), None);
    }

    #[test]
    fn provider_size_changes_while_collapsed_become_the_restored_size() {
        let fit = ContentFitState::default();
        let id = Uuid::new_v4();
        fit.register(id, GeometryControl::Provider, 600.0);
        fit.set_collapsed_size(id, (480.0, 600.0), (236.0, 50.0));
        fit.update_expanded_size(id, (520.0, 720.0));

        assert_eq!(fit.restore_expanded_size(id), Some((520.0, 720.0)));
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
        assert!(snapshot.window.always_on_top);
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
