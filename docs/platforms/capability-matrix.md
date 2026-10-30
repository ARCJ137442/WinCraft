---
title: WinCraft desktop platform capability matrix
updated_at: 2026-10-31
protocol_baseline: 0.3 plus optional 0.4-preview.1
status: partial-cross-platform-build
audience: maintainer, release-validator
---

# WinCraft 平台能力矩阵

Tauri 编译成功只证明该目标上的源码和依赖可以编译；它不证明托盘、窗口定位、置顶、点击穿透、全局快捷键或 X11/Wayland 行为等价。下表分别记录编译、源码能力和原生交互验收，`NOT_RUN` 不折算为支持。

## 平台状态

| Capability | Windows 11 x64 | Linux x86_64 WSL2 | Linux X11 | Linux Wayland | macOS |
|---|---|---|---|---|---|
| Core/protocol/lease model | automated PASS | workspace build/test PASS | NOT_RUN | NOT_RUN | NOT_RUN |
| Tauri desktop build | release build PASS | debug ELF build PASS | NOT_RUN | NOT_RUN | NOT_RUN |
| Tray host | 用户确认托盘可用；其余人工 gates 分开记录 | dependency/build PASS；tray UI NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Common Tauri window properties | Windows acceptance varies by property; see [ACCEPTANCE](../engineering/ACCEPTANCE.md) | API compiles; native behavior NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Human move/resize and DPI | automated geometry + platform-specific manual gates | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Work-area anchor | core/Tauri wiring and headless PASS; monitor detach NOT_RUN | Tauri compile only | NOT_RUN | NOT_RUN | NOT_RUN |
| Click-through/rescue | Windows manual acceptance tracked separately | NOT_RUN | NOT_RUN | compositor-dependent/NOT_RUN | NOT_RUN |
| External window actions | Win32 implementation; individual user-facing actions tracked separately | unsupported and fails closed | unsupported | unsupported | unsupported |
| Codex thread navigation | Windows-only capability; real UI navigation remains NOT_RUN | not advertised | not advertised | not advertised | not advertised |
| Global hotkey | OS registration/manual behavior remains tracked separately | build only; runtime NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Native opacity | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED |
| Virtual desktop “all workspaces” | unsupported by current public Tauri/tao API | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

The shared Tauri adapter calls window setters for title, z-order, decorations, taskbar visibility, size, position, cursor pass-through and show/hide. This confirms implementation wiring only; platform-specific behavior still needs platform-specific testing. `WindowSpec.surface_opacity` is protocol state, but native opacity is listed as not implemented and the desktop adapter does not apply it.

## Evidence: Ubuntu 24.04 WSL2

**Given** Ubuntu 24.04 WSL2 with the `x86_64-unknown-linux-gnu` target and Tauri GTK/WebKit/AppIndicator dependencies, **When** the formatter, workspace tests, strict Clippy and Tauri desktop build run with a separate Cargo target under WSL `/tmp`, **Then** the Linux compile boundary passes; this does not claim GUI or window-manager behavior.

- Environment: WSL2 kernel `6.6.114.1-microsoft-standard-WSL2`, x86_64, rustc/Cargo `1.96.0`, Ubuntu `24.04`.
- Tauri build dependencies were installed inside Ubuntu WSL: `pkg-config`, `libdbus-1-dev`, `libgtk-3-dev`, `libwebkit2gtk-4.1-dev`, `libayatana-appindicator3-dev`, `libxdo-dev`, `librsvg2-dev` and `libssl-dev`. APT added 189 packages and upgraded 14 existing graphics/system dependencies; details are in ignored local evidence.
- Workspace tests: 147 passed (core 10, core invariants 62, desktop 22, server 53); strict workspace Clippy passed.
- Debug ELF: `/tmp/wincraft-linux-target-1ced028/debug/wincraft-desktop`, 288,532,064 bytes, SHA-256 `eb5529e4890d2ae5bb85783256844395fa3b1427a77aeb57e2bc4e28f58211a8`.
- The WSLg environment had `DISPLAY=:0` and `WAYLAND_DISPLAY=wayland-0`, but the app was not launched and no window tree or screenshot was inspected. Do not infer which compositor behavior the compiled app would receive.
- Local evidence: `evidence/local/nextgen-2026-10-31/b11-03-linux-platform-build.json`.

## Host capability implementation

- [`main.rs`](../../apps/desktop/src-tauri/src/main.rs) ties `external_window_actions` to the compiled Windows target; its regression test checks the Host capability response matches the target.
- [`windows.rs`](../../apps/desktop/src-tauri/src/windows.rs) contains the Win32 process/window search and focus actions behind `cfg(windows)`. Other platforms return an explicit unsupported result. Pure filtering/selection policy helpers remain available to tests on every target.
- [`hub.rs`](../../crates/wincraft-server/src/hub.rs) advertises external window actions only when the Host enables them; Codex thread navigation additionally requires Windows.
- [`scene.rs`](../../crates/wincraft-core/src/scene.rs) and [`model.rs`](../../crates/wincraft-core/src/model.rs) preserve the opacity request/state, but the capability response lists `native_opacity` as not implemented.

## Remaining acceptance

- WSLg launch, rendering, tray menu, placement, z-order, title bar, click-through rescue, resize and hide/restore remain `NOT_RUN`.
- Native X11 and native Wayland require separate runs for tray menu, visibility, placement/DPI, click-through, drag and shutdown behavior.
- macOS build and native interaction are `NOT_RUN` because no macOS host/toolchain is available.
- Keep Windows as the only currently user-accepted native target. Cross-platform builds must not weaken the Windows protocol, ownership or rescue contracts.

B11-03 remains `IMPLEMENTED_UNVERIFIED`: Linux compilation and a target-aware capability report now have evidence, but WSLg/X11/Wayland runtime behavior and macOS remain unverified. B11-01 performance baselining is tracked separately.
