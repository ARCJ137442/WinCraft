---
title: WinCraft native platform capability matrix
updated_at: 2026-10-28
last_verified_at: 2026-10-28
protocol_baseline: 0.3
status: matrix-not-native-validated
audience: maintainer, release-validator
---

# Native platform capability matrix

The Rust core, protocol schemas and provider SDK are intended to be platform-neutral. Native behavior is separate and must be validated per platform/window system. This matrix records design expectations and current evidence; a Tauri compile is not a native equivalence test.

| Capability | Windows | macOS | Linux X11 | Linux Wayland |
|---|---|---|---|---|
| Core/protocol/lease model | automated PASS | not built here | not built here | not built here |
| Tauri/WebView renderer | Windows compile PASS | NOT_RUN | NOT_RUN | NOT_RUN |
| Tray host | implemented, manual gate NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Human move/resize and DPI | automated geometry + manual DPI NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Work-area anchor | core/Tauri wiring and headless PASS; monitor detach NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Click-through/rescue | wired, manual gate NOT_RUN | NOT_RUN | NOT_RUN | compositor-dependent/NOT_RUN |
| Foreground/external window actions | allowlist wired, real click NOT_RUN | unsupported/NOT_RUN | unsupported/NOT_RUN | unsupported/NOT_RUN |
| Global hotkey | intent registry only; OS registration NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Virtual desktop “all workspaces” | unsupported by public Tauri/tao API | NOT_RUN | NOT_RUN | NOT_RUN |

## Release rule

Only publish a platform capability after a platform-specific build and native acceptance record exist. Unsupported or untested capabilities must remain visible as such; they are not inferred from Tauri's target list. Cross-platform migration must preserve the Windows protocol contract and must not silently downgrade security or ownership checks.
