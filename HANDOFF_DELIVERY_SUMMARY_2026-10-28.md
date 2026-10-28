---
title: WinCraft next-generation handoff delivery summary
updated_at: 2026-10-28
protocol_baseline: 0.3
status: handoff-ready-with-open-gates
audience: maintainer, release-validator
---

# WinCraft next-generation handoff delivery summary

This workspace integrates the 2026-10-26 platform evolution handoff package and records the current implementation and evidence boundary. It is a local development handoff, not release authorization.

## Task status

| Status | Count | Meaning |
|---|---:|---|
| VERIFIED | 10 | Automated and/or real protocol evidence covers the task scope |
| IMPLEMENTED_UNVERIFIED | 15 | Core, contract or documentation work exists; native/external acceptance remains |
| IN_PROGRESS | 2 | Popup native acceptance and B04-02 native/manual behavior |
| BLOCKED | 3 | External source, runtime, authorization or platform dependency missing |
| NOT_STARTED | 18 | Dependencies are not satisfied or task is future scope |

The machine-readable source is [`docs/strategy/2026-10-26/plan/status.json`](docs/strategy/2026-10-26/plan/status.json). The detailed audit is [`docs/strategy/2026-10-26/plan/TASK_AUDIT_2026-10-27.json`](docs/strategy/2026-10-26/plan/TASK_AUDIT_2026-10-27.json).

The 48 tasks are all represented in the generated acceptance matrix: 147 acceptance cases total, 38 currently PASS and 109 still NOT_RUN. No task is missing an acceptance case; NOT_RUN cases are retained where native, external-source or future-batch evidence is unavailable.

## Verified implementation slices

- Rust core/server/Tauri compile, tests and Clippy.
- Protocol 0.3 lease/revocation/reader-writer isolation and dynamic scene behavior.
- Typed geometry/visibility subscriptions with coalescing and slow-consumer handling.
- Provider journey/tutorial, theme tokens, i18n, accessibility DOM checks and Popup state machine.
- Allowlisted Obsidian/TrafficMonitor native action service boundary and failure-closed routing tests.
- Work-area semantic anchor: four corners, logical margins, DPI scaling, negative origins, clamping, human-mode rejection, rescue clearing and anchor-aware events.
- Session-scoped shortcut intent registry with conflict/reserved-key rejection and disconnect cleanup; no OS hook is installed.
- Pack, inventory, usage observation, web-chat observation and voice-session draft schemas with positive/negative fixtures.
- Pure adaptive planner and submission eligibility guard; no Host mutation or adapter execution.
- Corrected the ordinary-input native-action guard and folded-height measurement; added centered SVG titlebar icons, a compact-width overlay that restores expanded size, `background_drag_enabled` gating for blank non-text surfaces, and capability-gated `position_control` separate from provider size control. Automated UI/Rust/headless protocol checks pass; native collapsed-width and hidden-titlebar drag pixels remain unverified because Computer Use could not route a click to the target window.
- Added a fixture-tested, read-only ExoMind workbench provider prototype. It projects the active timeblock through GET and changes only the local WinCraft world layout. Fixture tests pass; live behavior for this newer prototype remains NOT_RUN.
- Added per-checkout CodeGraph commands and ignore rules, a single `npm run check:local` validation path, Windows push/PR CI, and a behavior/evidence-focused PR template. The local index is fresh; its database is intentionally untracked.
- Distilled the supplied study material into WinCraft-specific delivery and evidence practices. Original private source material, personal paths and evaluation answer keys were not copied into this public repository.

## Reproduction commands

```powershell
npm ci
python -m pip install -r requirements-dev.txt -r examples/python/requirements.txt
npm run check:local
```

CodeGraph: `npm run codegraph:init` once per new checkout, then `npm run codegraph:explore -- "<query>"`; after code changes use `npm run codegraph:sync` and confirm `npm run codegraph:status`.

## Stage release artifact

- `target/release/wincraft-desktop.exe`
- 11,806,720 bytes
- SHA-256: `3BAA25F64D32C207CFC3C9467921F9F983ECF505A073C24D28055F64A05D41C7`
- Built from the working tree based on commit `24161e2`, including the `position_control` and background-drag changes that are part of this checkpoint. `npm run desktop:build` passed. The new executable was launched with `--open-manager` and the real Tauri manager appeared in UIA; a separate no-argument run kept the process alive with zero target windows. It is a local validation artifact, not a published release.
- Chinese manual acceptance guide: [`验收指南-阶段性release-2026-10-28.md`](验收指南-阶段性release-2026-10-28.md)

The freshly built Tauri release host passed 39 real-WebSocket `lease_probe.py` checks. Local evidence is under `evidence/local/nextgen-2026-10-27/` and `evidence/local/nextgen-2026-10-28/`; these records exclude runtime tokens, descriptor contents, note bodies and telemetry. Tray menu activation, global hide/show, collapse width on the latest release, background dragging pixels, DPI/multi-monitor, and user-driven acceptance remain open.

## Open gates

- Current release tray manager open/focus, global hide/show, graceful exit and redacted UIA/manual acceptance.
- Latest W23 native compact-width/expanded-width restoration, pixel-level titlebar alignment, provider-size/human-position split and hidden-titlebar background drag. Height-to-titlebar was observed at 480×50 on the preceding release; latest width/drag click was blocked because Computer Use targeted the Edge overlay after one recovery retry.
- Popup real release success/cancel, position reuse, keyboard/IME/UIA and concurrent-window acceptance.
- Obsidian Workspace/TrafficMonitor real external-window clicks and Windows foreground-denial path.
- Multi-monitor/DPI pixels, monitor detach migration, click-through rescue and virtual desktop behavior.
- Native RegisterHotKey/IME, Windows voice APIs, browser bridge, TeamSense, TouchAI and SysTorch integrations.
- A previous user-authorized read-only smoke exercised the ExoMind active-timeblock projection. No profile identifier, current block state, returned content, or RT connection details are included here. The newer workbench provider's tests use synthetic fixtures; live behavior remains NOT_RUN.
- Runtime pack import/preview/submit/rollback and second-machine migration.
- Long-run process/resource measurements, signing/installer/ACL and macOS/Linux builds.
- Future idea only: a read-only TeamSense status card, with TeamSense retaining business truth and authorization; no credential-file or private-web-page access. This does not expand the current release scope.

These remain `NOT_RUN`, `BLOCKED` or `IMPLEMENTED_UNVERIFIED` in the matrix. They must not be converted to PASS from browser previews, headless tests, compile success or design prose.

## Checkpoint and rollback

This checkpoint extends the existing public `ARCJ137442/WinCraft` `dev` history from base `24161e2` with position-control, the read-only ExoMind provider prototype, CodeGraph/toolchain setup, and the updated validation/acceptance documentation. The EXE is delivered as a local handoff artifact, not uploaded as a GitHub release. No release tag, installer publication, license change or remote permission change is included. Provider business data and external installations were not modified.
