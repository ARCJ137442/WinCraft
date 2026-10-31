---
title: Window groups and roles — minimal proof of concept
updated_at: 2026-10-31
last_verified_at: 2026-10-31
protocol_baseline: 0.3
status: implemented-verified-at-protocol-level
audience: maintainer, provider-author
---

# Window groups and roles: minimal proof of concept

This note records the B10-03 proof of concept. It is a small, reversible
capability on top of the existing world ownership model, not a new ownership
mode.

## What the POC is

A **presentation group** is a host-side, ordered set of worlds that one
provider already owns. It exists so that a provider can present several
windows as one unit — a HUD, a workbench, a dashboard — without the host
inventing a new authority model.

Three properties are deliberate and load-bearing:

- **Groups grant nothing.** Every member keeps its own write lease, revision
  and fencing epoch. A group never creates, widens or transfers a lease.
- **Operations are per member.** `presentation.group.apply` applies one
  window patch to each member independently. The result is never atomic and
  the Host never reports a partial failure as a group-wide success.
- **Roles are labels.** A role is a descriptive string attached to the group
  or to one member. Roles carry no business semantics, no emotion or mood
  engine, and no authority of their own.

## What the POC is not

This is deliberately **not** any of the following:

- not a shared-memory or cross-process shared-state construct;
- not a role-based access control system;
- not a business-affinity or "mood" engine;
- not an atomic group transaction;
- not a screen-capture, AppBar, DWM or input-region feature. Those remain
  independently unbuilt; see "Not yet built" below.

## Contract surface

The capability is advertised in the `0.4-preview.1` capability table only. A
provider must negotiate that protocol explicitly and call
`client.require_presentation_groups()` before using it; anything else fails
closed.

| Method | Purpose |
|---|---|
| `presentation.group.create` | Register a named, ordered group with optional roles. |
| `presentation.group.list` | List the groups registered by this session only. |
| `presentation.group.patch` | Add or remove members, add roles. |
| `presentation.group.delete` | Remove the group. Member worlds are untouched. |
| `presentation.group.apply` | Apply one window patch to every member, per member. |

Limits: 32 members per group, 16 roles per group, 64 bytes per role name, and
one member per world.

`presentation.group.apply` takes a lease and an expected revision **per
member**. A member with a missing lease, an expired lease, a mismatched
epoch, a stale revision, or a human-controlled geometry write refuses on its
own and keeps its machine-readable fault code. The remaining members still
run. The response always carries `atomic: false`, a per-member
`result.results` list, and a `changed` list containing only the members that
actually accepted the operation.

## Observable partial failure

Native window failures stay per member. The host already reports native
apply errors through each world's own `native` report, so a member whose
window could not be created or resized is distinguishable from a member that
refused at the protocol level. The group layer does not merge these two
outcomes into a single group verdict.

## Roles

Roles are presentation metadata only. A role may name the whole group
(`member: null`) or one member. Removing a member also drops the roles that
were scoped to that member. A role that references a world outside the group
is refused. No role implies membership, authority, priority, ownership or
any behavioural rule; the host never uses a role to decide what a member is
allowed to do.

## Verification

| Layer | Check | Result |
|---|---|---|
| Core | 7 unit tests in `crates/wincraft-core/src/presentation_group.rs`: ordering and de-duplication, member limit, partial failure reporting, every member visited after a failure, role labelling, role cleanup on member removal, empty role rejection. | PASS |
| Server | 3 tests in `crates/wincraft-server/src/hub.rs`: per-member outcomes with a fault code, cross-session invisibility, stable-protocol rejection. Capability-table assertions cover the preview-only and non-atomic guarantees. | PASS |
| Python SDK | 4 capability tests in `tests/test_client_capabilities.py`: the capability is required, and a Host claiming atomic semantics or discovery-granted rights is rejected. | PASS |
| Real protocol | `scripts/presentation_group_headless_smoke.py` drives the **release** headless Rust Host over a real WebSocket: 17 checks covering the capability gate, group creation, listing, roles, per-member apply with one deliberately wrong lease, refusal codes, changed-member reporting, cross-session blocking, and the resulting world state. | PASS |

## Not yet built

The following were explicitly out of scope for this POC and remain unbuilt:

- AppBar / DWM integration;
- region input routing;
- screen capture, and any capture-exclusion behaviour;
- any guarantee that a capture exclusion is confidential.

No capture feature exists yet, so the "exclusions are opt-in and never a
confidentiality promise" rule is recorded here as a constraint for a future
implementation rather than as current behaviour.

## Rollback

The group registry is in-memory host state. Removing the capability and the
five methods restores ordinary independent windows; no world, lease or scene
needs migration. The Python SDK helper and the smoke script are additive and
can be dropped independently.
