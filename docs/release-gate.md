---
title: WinCraft release gate and claims boundary
updated_at: 2026-10-30
last_verified_at: 2026-10-30
protocol_baseline: 0.3
status: pre-release-gate
audience: maintainer, release-validator
---

# Release gate and claims boundary

This is a pre-release audit for the current working tree. It is not a release approval and contains no unmeasured performance claims.

## Claims allowed from current evidence

- The current Windows worktree passed `npm run check:local`: 28 Node UI tests, Rust fmt/check/workspace tests/Clippy, 176 Python tests (one symlink case skipped because Windows denied creation), offline contracts and 27 Provider Skill references. The handoff suite separately passed 40 tests. These do not replace native acceptance.
- Historical Windows Actions run `40876095509` passed for pushed commit `32c8eee` in 11m42s; it validates that commit's automated source checks, not the current worktree. B06 checkpoint commit `e3e8df4` run `40976867333` passed fmt/check/workspace tests but failed Clippy 1.99's new `chunks_exact_to_as_chunks` lint. The working tree contains a minimal `as_chunks::<2>()` fix plus regression; local full checks pass and hosted rerun is pending.
- `npm run desktop:build` on 2026-10-30 built a current-source local candidate at `target/release/wincraft-desktop.exe` (13,277,184 bytes; SHA-256 `AA6A656F08DBC79F2C5900906095CA13CAEE78A780633A23049DD9F0BE124EB0`). It was launched with `--open-manager`; Computer Use listed the manager but two window-state captures failed with `GetCursorPos` access denied. No UI clicks/text were sent. This dirty-worktree candidate is not a published release.
- A Python SDK hello/capability request to the live Tauri host negotiated `0.4-preview.1` and verified `provider_import` schema/event/claim/writer-scope/local-confirmation fields; it did not register inventory or create worlds.
- Protocol, lease, revocation, reader/writer isolation, dynamic scene, theme, event subscription and anchor behavior have automated tests.
- A real isolated Rust headless host previously passed a 41-check `lease_probe.py` run; the current workspace also passes its Rust core/server/Tauri automated suite.
- B06-01/B06-02 are VERIFIED at draft-export/pure-planner scope; B06-03/B06-04 are `IMPLEMENTED_UNVERIFIED` with PARTIAL acceptance. The new `.wcp` manual flow and two-user sharing checks are documented in the Chinese acceptance guide and remain NOT_RUN.
- A preceding Tauri release host reported native application of `always_on_top=false/true`; the current 2026-10-30 build has not repeated that setter test, and actual z-order against ordinary and other topmost windows remains NOT_RUN.
- An earlier release UIA smoke showed four session-card fields with a synthetic Codex App snapshot; the current release window could not be captured by Computer Use, so no current-build pixel/UIA claim is made. The real connector snapshot is still BLOCKED, and Codex App deep-link click/load remains NOT_RUN.
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
5. B06-03 synthetic `.wcp` preview, permission grant/re-preview, explicit apply, directed Provider event, cancellation and two-step rollback; then B06-04 import the same config-only pack in two independent user environments and re-authorize each local Provider.

If a gate cannot run because the source, account, device or user authorization is missing, record `BLOCKED` or `NOT_RUN` with the exact reason. Do not convert a browser preview, headless probe or compile result into a native PASS.
