---
title: WinCraft next-generation handoff delivery summary
updated_at: 2026-10-28
protocol_baseline: 0.3
status: handoff-ready-with-open-gates
audience: maintainer, release-validator
---

# WinCraft next-generation handoff delivery summary

This workspace integrates the `<handoff-dir> 2026-10-26` handoff package and records the current implementation and evidence boundary. It is a local development handoff, not release authorization.

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
- Corrected the ordinary-input native-action guard and folded-height minimum; added SVG titlebar icons and a temporary compact-width overlay that preserves the expanded window size. Automated UI/Rust checks pass; the latest native collapsed-width/expand path remains unverified because Computer Use could not route a click to the target window.

## Reproduction commands

```powershell
cargo fmt --all -- --check
cargo test --workspace --no-fail-fast
cargo clippy --workspace --all-targets -- -D warnings
npm run check
python -m unittest discover -s tests -v
python scripts/check_contracts.py
python skills/wincraft-provider/scripts/verify.py
```

## Stage release artifact

- `target/codex-collapse-input-fix-20261028/release/wincraft-desktop.exe`
- 11,793,408 bytes
- SHA-256: `1175191A6CB51E1542E31A125BDE5F018E94F1A885BCB1387F30A9449B19A633`
- Built from the current working tree based on `fea00bc4f9342d68ecca0d9ecda88a289491334a`; launched for the real ExoMind read-only projection. It is a local validation artifact, not a published release.
- Chinese manual acceptance guide: [`验收指南-阶段性release-2026-10-28.md`](验收指南-阶段性release-2026-10-28.md)

The final isolated headless Rust probe passed 38 `lease_probe.py` checks. Local evidence is under `evidence/local/nextgen-2026-10-27/` and contains no runtime token, descriptor contents, note body or telemetry.

## Open gates

- Current release tray manager open/focus, global hide/show, graceful exit and redacted UIA/manual acceptance.
- Latest W23 native compact-width/expanded-width restoration and pixel-level titlebar alignment. Height-to-titlebar was observed at 480×50 on the preceding release; the latest combined build's width click was blocked because Computer Use targeted the Edge overlay after one recovery retry.
- Popup real release success/cancel, position reuse, keyboard/IME/UIA and concurrent-window acceptance.
- Obsidian Workspace/TrafficMonitor real external-window clicks and Windows foreground-denial path.
- Multi-monitor/DPI pixels, monitor detach migration, click-through rescue and virtual desktop behavior.
- Native RegisterHotKey/IME, Windows voice APIs, browser bridge, TeamSense, TouchAI and SysTorch integrations.
- ExoMind currently has a verified live read-only active-timeblock projection; a broader workbench replica and any write behavior remain unimplemented. RT build hash differs from the skill's recorded hash.
- Runtime pack import/preview/submit/rollback and second-machine migration.
- Long-run process/resource measurements, signing/installer/ACL and macOS/Linux builds.

These remain `NOT_RUN`, `BLOCKED` or `IMPLEMENTED_UNVERIFIED` in the matrix. They must not be converted to PASS from browser previews, headless tests, compile success or design prose.

## Checkpoint and rollback

This implementation and documentation checkpoint is being committed and pushed to the existing public `ARCJ137442/WinCraft` `dev` branch under the user's explicit authorization. No release upload, release tag, installer publication, license change or remote permission change is included. The code changes remain reversible by reverting the checkpoint; provider business data and external installations were not modified.
