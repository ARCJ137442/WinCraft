---
title: Configuration pack new-machine acceptance
updated_at: 2026-10-27
last_verified_at: 2026-10-27
protocol_baseline: 0.3
status: proposal-validated
audience: maintainer, provider-author
---

# New-machine acceptance for configuration packs

The handoff pack provides synthetic environments for full sources, optional missing sources, required missing sources, ambiguous matches and missing grants. The repository planner now exercises all five outcomes with a fixed clock.

Expected results:

- Full inventory: `ready`
- Optional source missing: `degraded`, with an explainable warning
- Required source missing: `blocked`
- Multiple equivalent providers: `blocked` until the user selects an instance
- Provider exists without the required grant: `blocked`

The plan is review-only: `mutates_host=false` and `requires_confirmation=true`. It does not download, install, launch, connect, or request credentials. A new machine reuses only non-secret pack configuration; providers and permissions must be discovered and authorized again. The plan output must not contain runtime descriptor names, bearer tokens, leases, account identifiers, private note titles or original machine paths.

This is schema/planner evidence, not a real two-machine migration. Runtime import, user preview/submit, resource ledger, rollback and a second Windows machine remain future acceptance work.
