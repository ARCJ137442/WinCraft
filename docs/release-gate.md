---
title: WinCraft release gate and claims boundary
updated_at: 2026-10-29
last_verified_at: 2026-10-29
protocol_baseline: 0.3
status: pre-release-gate
audience: maintainer, release-validator
---

# Release gate and claims boundary

This is a pre-release audit for the current working tree. It is not a release approval and contains no unmeasured performance claims.

## Claims allowed from current evidence

- The current Windows worktree passed `npm run check:local`: 28 Node UI tests, 116 Rust workspace tests, 145 Python tests, offline contracts and 27 Provider Skill references; this does not replace native acceptance.
- Windows Actions run `40855749607` passed for pushed commit `283c1b8`; it does not include the current uncommitted inventory/session-card changes.
- `npm run desktop:build` built `target/release/wincraft-desktop.exe` from the current working tree; a separately launched `--open-manager` release produced a real manager window.
- Protocol, lease, revocation, reader/writer isolation, dynamic scene, theme, event subscription and anchor behavior have automated tests.
- A real isolated Rust headless host passed a 41-check `lease_probe.py` run; the current workspace also passes its Rust core/server/Tauri automated suite.
- The latest Tauri release host reported native application of `always_on_top=false/true`; actual z-order against ordinary and other topmost windows is still NOT_RUN.
- Current release UIA showed the four session-card fields with a synthetic Codex App snapshot; the real connector snapshot is still BLOCKED, and Codex App deep-link click/load remains NOT_RUN.
- TrafficMonitor and Obsidian Obsidian Workspace providers have documented read-only/source boundaries and prior current-release evidence.
- Native external actions are allowlisted and fail closed in service tests; real Windows click success/failure remains unverified.

## Claims forbidden until manual gates pass

- default tray-only startup, tray-menu focus/open, global hide/show and graceful tray Exit on the current build;
- pixel-perfect content fitting/no window-level scrollbar across changing content, current-build collapse sizing recheck, click-through rescue;
- multi-monitor/DPI behavior, monitor detach migration and virtual-desktop behavior;
- real Popup UI success/cancel, keyboard/IME/UIA/reader and position reuse;
- real Obsidian Workspace Obsidian activation or TrafficMonitor window actions;
- Windows global hotkeys, voice APIs, browser bridges, TeamSense, TouchAI, SysTorch or ExoMind;
- CPU, memory, latency, throughput, leak or “lightweight” performance numbers;
- signed installer, ACL isolation or production security certification.

## Manual gate packet

Run these in one controlled Windows session against the final isolated release, recording only redacted screenshots/exit codes:

1. `W01/W02/W07/W09/W11/W12/W13/W15/W17/W18/W19/W20/W22/W23/W25/W27` from `docs/engineering/ACCEPTANCE.md`.
2. `R01/R02/R03/R06` after closing any previous WinCraft host.
3. B03-02 Popup success/cancel/position/keyboard/IME/UIA.
4. B04-03 native hotkey only after explicit user authorization.

If a gate cannot run because the source, account, device or user authorization is missing, record `BLOCKED` or `NOT_RUN` with the exact reason. Do not convert a browser preview, headless probe or compile result into a native PASS.
