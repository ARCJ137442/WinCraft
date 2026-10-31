---
title: WinCraft release gate and claims boundary
updated_at: 2026-10-31
last_verified_at: 2026-10-31
protocol_baseline: 0.3
status: pre-release-gate
audience: maintainer, release-validator
---

# Release gate and claims boundary

This is a pre-release audit for WinCraft `0.1.0-alpha.1`. It is not release approval. The repository remains private; no GitHub Release, tag, installer or public announcement was created.

## Claims allowed from current evidence

- Source validation on commit `f39de58` passed `npm run check:local`: 28 UI tests, 149 Rust workspace tests, 225 Python tests (one Windows symlink-capability skip), Clippy, contracts and 33 Provider Skill references. Windows Actions run [41170007833](https://github.com/exomind-team/WinCraft/actions/runs/41170007833) passed in 12m19s. The documentation-only follow-up `8746400` passed Windows Actions run [41173578234](https://github.com/exomind-team/WinCraft/actions/runs/41173578234) in 12m05s. CI validates source; it does not replace native UI acceptance.
- `target/release/wincraft-desktop.exe` is a local, unsigned, single-file Tauri build from product-source commit `9073b3b`: 13,600,256 bytes, SHA-256 `7E910E01057DADB17991B00D2A51CE63419628F818C35C06C1EE3D0C3179D691`. It launches tray-only by default and has passed real Tauri-hosted `lease_probe.py` checks. The build is not an installer and is not a GitHub Release.
- Synthetic performance evidence includes 5-, 15- and 30-minute visible refresh runs (60/180/360 updates), provider-crash reacquisition, headless Host disconnect and one forced Tauri Host shutdown. In the Tauri crash sample, six WebView descendants exited within three seconds. The 30-minute sample's private-byte median declined while working set increased about 20 MB; this is not a long-term leak guarantee or a cross-machine performance claim. Full context and boundaries are in [`docs/performance.md`](performance.md).
- The quota HUD accepted a three-second synthetic Codex/MiniMax/DeepSeek scene on the current Tauri release and cleaned its world. No auth file or external account was read, no network request was sent, and no pixel claim follows from the scene smoke.
- `B06-03` stale-grant logic and `B06-04` export hygiene have automated checks. Manager preview/grant/apply/rollback pixels and two-user import remain NOT_RUN/PARTIAL; detailed steps are in the [Chinese acceptance guide](release/WINCRAFT_ALPHA1_ACCEPTANCE_CN.md).
- Repository identity remains `exomind-team/WinCraft`, private on branch `dev`. No release or tags exist. The current license files, product/package names and ownership were not changed from baseline; `WinCraft` and `窗构` remain explicitly provisional names.
- The Chinese Windows acceptance guide is versioned for `0.1.0-alpha.1` and updated `2026-10-31`; this English gate states the same claim limits and pending native checks. Neither document declares the prototype ready for public release.

## Claims forbidden until manual gates pass

- current-build manager preview/grant/re-preview/apply/cancel/rollback and tray reopen behavior;
- screenshot-level fit, collapse, hidden-window restoration, click-through rescue and z-order;
- multi-monitor/DPI, monitor detach, Windows virtual desktop and native hotkey behavior;
- real Popup user success/cancel/position reuse, WebView2 UIA/IME and screen-reader operation;
- Obsidian Workspace activation of an existing Obsidian window, TrafficMonitor actions and UUID-only Codex App navigation;
- live TeamSense/Codex quota, browser bridge, voice, TouchAI, SysTorch, ExoMind or Android sources;
- long-term leak freedom, sleep/wake, resource thresholds, signed installer, ACL isolation or production security certification.

The Computer Use helper's Windows native pipe failed both initial and post-reset attempts on `2026-10-31`; no clicks or screenshots were issued during those attempts. Historical user reports for tray/window behaviors are not tied to this exact executable hash and are not substituted for a current-build PASS.

## Manual gate packet

Run these in one controlled Windows session against the final isolated release, recording only redacted screenshots/exit codes:

1. `W01/W02/W07/W09/W11/W12/W13/W15/W17/W18/W19/W20/W22/W23/W25/W27` from `docs/engineering/ACCEPTANCE.md` against the exact EXE hash above.
2. `R01/R02/R03/R06` after closing any previous WinCraft host.
3. B03-02 Popup success/cancel/position/keyboard/IME/UIA.
4. B04-03 native hotkey only after explicit user authorization.
5. B06-03 synthetic `.wcp` preview, permission grant/re-preview, explicit apply, directed Provider event, cancellation and two-step rollback; then B06-04 import the same config-only pack in two independent user environments and re-authorize each local Provider.

If a gate cannot run because the source, account, device or user authorization is missing, record `BLOCKED` or `NOT_RUN` with the exact reason. Do not convert a browser preview, headless probe or compile result into a native PASS.
