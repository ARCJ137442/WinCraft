# Presentation groups (0.4-preview.1)

A presentation group lets one provider present several of its own worlds as a
single on-screen unit. It is a small, reversible orchestration capability on top
of the existing ownership model.

## When to use it

Use a group when several worlds should read as one thing to the user: a HUD, a
multi-panel workbench, a dashboard whose panes are separate worlds. Do not use
it to share data between worlds — business truth stays in your provider, and
WinCraft stores only rebuildable state.

## Before you start

1. Negotiate `0.4-preview.1` explicitly. The stable `0.3` protocol does not
   carry this capability.
2. Call `client.require_presentation_groups()`. If the Host does not advertise
   the capability, or advertises it with different semantics, the SDK raises and
   you must not use the feature.

```python
from client import COMPONENT_LEASES_PREVIEW_PROTOCOL, Client

async with Client(runtime_path, "my.provider",
                  protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL) as client:
    client.require_presentation_groups()
```

## Methods

| Method | Purpose |
|---|---|
| `presentation.group.create` | Register a named, ordered group with optional roles. |
| `presentation.group.list` | List the groups registered by this session. |
| `presentation.group.patch` | Add or remove members; add roles. |
| `presentation.group.delete` | Remove the group. Member worlds are untouched. |
| `presentation.group.apply` | Apply one window patch to every member, per member. |

Limits: 32 members per group, 16 roles per group, 64 bytes per role name, and a
world may appear only once in a group.

## Applying an operation

`presentation.group.apply` takes one window patch plus a lease and an expected
revision **for each member**:

```python
outcome = await client.apply_presentation_group(
    group_id,
    leases={world_a: lease_a, world_b: lease_b},
    expected_revisions={world_a: rev_a, world_b: rev_b},
    visible=False,
)
```

Read the result per member:

```python
for entry in outcome["result"]["results"]:
    if entry["outcome"]["status"] == "refused":
        log.warning("member %s refused: %s", entry["world_id"],
                    entry["outcome"]["code"])
```

`outcome["atomic"]` is always `false`. `outcome["changed"]` lists the members
that accepted the operation; a member that refused is absent from it. The
refusal reason is a stable fault code such as `STALE_LEASE`,
`REVISION_CONFLICT` or `HUMAN_GEOMETRY`.

Native window failures stay per member too: the Host reports them through each
world's own `native` report, so a member whose window could not be resized is
distinguishable from a member that refused at the protocol level.

## Roles

A role is a descriptive label:

```python
{"name": "primary", "member": None}      # applies to the whole group
{"name": "secondary", "member": world_b}  # applies to one member
```

Roles are presentation metadata. They carry no business meaning, no emotion or
mood engine, and no authority. The Host never uses a role to grant a lease,
bypass a check, or decide what a member may do. Removing a member also drops
the roles scoped to that member. A role that points at a world outside the
group is refused.

## Rebuilding after a Host restart

The group registry lives in Host memory and is empty after a restart. A
provider that needs groups must recreate them from its own state on the next
connection. Do not assume a group survives; do not store a group id in
evidence or in another provider's data.

## Failure handling

- **A member refuses.** Inspect its code, fix the cause (renew the lease,
  re-read the revision, or ask the user to release human geometry), then apply
  again to that member only if the operation is idempotent for it.
- **The Host is old.** `require_presentation_groups()` raises. Fall back to
  operating each world individually with `window.configure`.
- **The session changed.** Another session cannot see or operate on your
  groups. Re-create them after reconnecting.

## Rollback

Delete the group with `presentation.group.delete`, or simply stop using it. The
member worlds keep their own leases and behaviour; removing a group never
destroys a world and never changes who owns it.

## Verifying your integration

`scripts/presentation_group_headless_smoke.py` drives the release headless Rust
Host over a real WebSocket and checks group creation, ordering, per-member
outcomes, refusal codes and cross-session isolation. Run it against an isolated
test host; it uses synthetic worlds only.

The protocol details are in [`docs/protocol.md`](../../../docs/protocol.md) and
the experiment notes in [`docs/poc/presentation-extensions.md`](../../../docs/poc/presentation-extensions.md).
