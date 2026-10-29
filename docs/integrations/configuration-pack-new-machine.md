---
title: Configuration pack new-machine acceptance
updated_at: 2026-10-30
last_verified_at: 2026-10-30
protocol_baseline: 0.3
status: static-fixtures-pass-runtime-ui-pending
audience: maintainer, provider-author
---

# New-machine acceptance for configuration packs

The handoff pack provides synthetic environments for full sources, optional missing sources, required missing sources, ambiguous matches and missing grants. The repository planner exercises all five outcomes with a fixed clock. B06-04's current share packet additionally indexes full, optional-missing, required-missing and no-grant inventory snapshots for the `workday` pack.

Expected results:

- Full inventory: `ready`
- Optional source missing: `degraded`, with an explainable warning
- Required source missing: `blocked`
- Multiple equivalent providers: `blocked` until the user selects an instance
- Provider exists without the required grant: `blocked`

The plan is review-only: `mutates_host=false` and `requires_confirmation=true`. It does not download, install, launch, connect, or request credentials. A new machine reuses only non-secret pack configuration; providers and permissions must be discovered and authorized again. The plan output must not contain runtime descriptor names, bearer tokens, leases, account identifiers, private note titles or original machine paths.

The local Rust runtime now supports manager preview/apply/rollback behind an optional `0.4-preview.1` capability and an explicit local confirmation. The current-source release was built and launched; the real Tauri host capability handshake passes. Computer Use could not read the manager window state (`GetCursorPos` access denied), so preview/submit/ledger/rollback UI acceptance remains PARTIAL/NOT_RUN.

This is not a completed two-machine migration. B06-04 still needs two independent user environments to import only the `.wcp` file, verify that no provider is auto-downloaded or executed, and separately authorize local providers/permissions in each environment. Do not copy runtime descriptors, grants, leases, user titles or business data between them.
