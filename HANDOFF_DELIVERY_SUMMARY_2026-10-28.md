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
- Corrected the ordinary-input native-action guard and folded-height measurement; added centered SVG titlebar icons, a compact-width overlay that restores expanded size, `background_drag_enabled` gating for blank non-text surfaces, and capability-gated `position_control` separate from provider size control. Automated UI/Rust/headless protocol checks pass; native collapsed-width and hidden-titlebar drag pixels remain unverified. The current Computer Use retry enumerated the manager but activation failed after fresh selection, so no UI input was sent.
- Unified topmost defaults: ordinary provider worlds and the internal manager use `always_on_top=true`; providers can toggle the existing property through `window.configure`. The Tauri host applied both values in a 40-check release probe; visible stacking against ordinary and other topmost windows still needs a physical overlap check.
- Fixed the titlebar fold/expand size contract on the prior release: observed `620×765 → 212×50 → 620×765`. The newly built topmost-default release has not had this UI path re-clicked yet.
- Refined the read-only ExoMind workbench prototype to represent full → compact → mini display modes and a separate idle content state; its only actions change/hide the local WinCraft projection. Thirteen synthetic fixture tests and one user-authorized live GET/projection smoke pass. The temporary provider was stopped with Ctrl+C; manager cleanup was not visually rechecked. Native mode UI and steady-state dimensions remain NOT_RUN; mini/full values are documented as fallback sizes, not measured steady-state dimensions.
- Added per-checkout CodeGraph commands and ignore rules, a single `npm run check:local` validation path, Windows push/PR CI, and a behavior/evidence-focused PR template. The local index is fresh; its database is intentionally untracked.
- Fixed nine consecutive Windows Actions failures: normalized translation source hashes across LF/CRLF checkouts and made handoff maintenance JSON reads/writes explicitly UTF-8. The B07-01 component-scope preview follow-up commit (`be7a50c`) passed hosted Windows run `40707844155` in 6m16s; Actions use Node 24 releases and show no Node 20 deprecation warning.
- Distilled the supplied study material into WinCraft-specific delivery and evidence practices. Original private source material, personal paths and evaluation answer keys were not copied into this public repository.

## Reproduction commands

```powershell
npm ci
python -m pip install -r requirements-dev.txt -r examples/python/requirements.txt
npm run check:local
```

CodeGraph: `npm run codegraph:init` once per new checkout, then `npm run codegraph:explore -- "<query>"`; after code changes use `npm run codegraph:sync` and confirm `npm run codegraph:status`.

## Previous stage release artifact (2026-10-28)

- `target/release/wincraft-desktop.exe`
- 11,806,720 bytes
- SHA-256: `0465752DB32BC4AAE37D7DA7D306F899FD8586F805A914B3EA0990C6FDD6963D`
- Built from the working tree through source commit `405b0ee`, including the manager topmost default. `npm run desktop:build` passed; the running release manager appeared in the application list, but Computer Use returned `failed to activate captured window` after refreshing selection. This is a local validation artifact, not a published release.
- Chinese manual acceptance guide: [`验收指南-阶段性release-2026-10-28.md`](验收指南-阶段性release-2026-10-28.md)

The freshly built Tauri release host passed 40 real-WebSocket `lease_probe.py` checks, including native application of `always_on_top=false/true`. A previous release's collapse test measured `620×765 → 212×50 → 620×765`; titlebar drag attempts via Computer Use produced no measurable move. The current topmost build's visual overlap, tray actions, fold dimensions and titlebar drag remain unverified. The user-authorized Computer Use retry enumerated the current manager but activation failed after refreshing selection; the returned screenshot was not trusted and no UI input was sent. Local evidence is under `evidence/local/nextgen-2026-10-27/` and `evidence/local/nextgen-2026-10-28/`; these records exclude runtime tokens, descriptor contents, note bodies and telemetry.

## Open gates

- Current release tray manager open/focus, global hide/show, graceful exit and redacted UIA/manual acceptance.
- Visual topmost ordering against ordinary and other topmost windows; only the provider/native setter round-trip is automated so far.
- Latest W23 titlebar drag, pixel-level icon alignment, hidden-titlebar background drag and width restoration. Collapse/expand dimensions were verified on the immediately preceding build; current UI automation could not produce a measurable drag or inspect the newest manager window.
- Popup real release success/cancel, position reuse, keyboard/IME/UIA and concurrent-window acceptance.
- Obsidian/TrafficMonitor real external-window clicks and Windows foreground-denial path.
- Multi-monitor/DPI pixels, monitor detach migration, click-through rescue and virtual desktop behavior.
- Native RegisterHotKey/IME, Windows voice APIs, browser bridge, TeamSense, TouchAI and SysTorch integrations.
- The ExoMind workbench provider has a fixture-tested read-only projection and three local display modes; one live GET/projection smoke passed. No profile identifier, current block state, returned content, or RT connection details are included here. Native mode interactions and steady-state dimensions remain NOT_RUN.
- Runtime pack import/preview/submit/rollback and second-machine migration.
- Long-run process/resource measurements, signing/installer/ACL and macOS/Linux builds.
- Future idea only: a read-only TeamSense status card, with TeamSense retaining business truth and authorization; no credential-file or private-web-page access. This does not expand the current release scope.

These remain `NOT_RUN`, `BLOCKED` or `IMPLEMENTED_UNVERIFIED` in the matrix. They must not be converted to PASS from browser previews, headless tests, compile success or design prose.

## Checkpoint and rollback

This checkpoint extends the existing public `ARCJ137442/WinCraft` `dev` history from base `24161e2` with position-control, the read-only ExoMind provider prototype, CodeGraph/toolchain setup, and the updated validation/acceptance documentation. The EXE is delivered as a local handoff artifact, not uploaded as a GitHub release. No release tag, installer publication, license change or remote permission change is included. Provider business data and external installations were not modified.

## Follow-up checkpoint (2026-10-29)

- B07-02 is implemented and recorded `VERIFIED`: component owners can atomically modify only their own subtree; root authority can remove child boundaries with namespace cleanup and revoke notifications; parent authority revocation fences child generations/epochs; scope-only readers get filtered live snapshots.
- Source commit `27b8677d13ee0a2bb885aeda7fac3872db0c7e52` passed Windows Actions run `40726526250`. Local `npm run check:local` passed with 28 UI, 101 Rust, 86 Python tests, contracts, Clippy, and 19 Provider Skill reference checks.
- The release EXE was rebuilt from that commit at `target/release/wincraft-desktop.exe` (12,060,160 bytes; SHA-256 `572507C80123CB0236E4024BCA2AD51B97E7FD034C1963591287BBD2BE56DB98`). A real Tauri host passed 40 `lease_probe.py` checks and the B07-02 `scope_probe.py`; the manager window appeared under `--open-manager`.
- Chinese release guide: [`WinCraft 0.1.0-alpha.1 Windows 验收指南`](docs/release/WINCRAFT_ALPHA1_ACCEPTANCE_CN.md). Default tray-only startup/click/normal exit, visual z-order, fold/resize pixels, click-through rescue, and multi-display/DPI still need the listed manual checks; those probes were not promoted to PASS.
