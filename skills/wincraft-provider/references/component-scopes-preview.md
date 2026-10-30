# Component scope leases: 0.4 preview

**Status:** experimental preview, not part of stable protocol 0.3. B07-01/02 provide disjoint scope writers, scoped structural transactions, parent revocation, and filtered live snapshots. B07-03 adds typed, explicitly shared state slots. Scope-owned component interactions and metadata-only lifecycle reads are optional capabilities; native window actions inside scopes remain unavailable.

## Opt in explicitly

`Client` defaults to stable `0.3`. The runtime descriptor advertises supported protocol versions. A provider selects the preview deliberately and verifies the matching host capability before using scope methods:

```python
from client import Client, COMPONENT_LEASES_PREVIEW_PROTOCOL

async with Client(
    runtime_path,
    "my-composed-provider",
    protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
) as client:
    client.require_component_leases(version=1)
```

There is no silent version fallback. Stable 0.3 behavior remains one whole-world writer with immutable snapshot readers. A 0.3 writer cannot join or mutate a composition world after it has been partitioned.

## Partition a world

First create and populate an ordinary exclusive world. Before partitioning, make each provider-owned subtree a disjoint child in the full scene and place its business projection under a unique top-level `scene.data` namespace. Binding paths in the full scene include that namespace:

```json
{
  "root": {
    "id": "root",
    "kind": "stack",
    "children": [
      {"id":"focus-panel","kind":"stack","children":[
        {"id":"focus-value","kind":"text","props":{"text":{"$path":"/focus/value"}}}
      ]},
      {"id":"tasks-panel","kind":"stack","children":[
        {"id":"tasks-value","kind":"text","props":{"text":{"$path":"/tasks/value"}}}
      ]}
    ]
  },
  "data": {
    "focus": {"value":"synthetic focus"},
    "tasks": {"value":"synthetic tasks"}
  }
}
```

Then transfer the exclusive world lease into root authority and scope grants in one revision-checked operation:

```python
result = await client.partition_scopes(
    world_id,
    current_lease,
    current_revision,
    [
        {"root_node_id":"focus-panel", "data_namespace":"focus"},
        {"root_node_id":"tasks-panel", "data_namespace":"tasks"},
    ],
)
```

Partitioning is atomic. It refuses overlapping roots, duplicate namespaces, an obsolete revision, or a world with other readers already attached. The old whole-world lease is fenced. Keep `authority_lease` for the separate window authority and share each `scope` grant only with the intended provider; grant keys are credentials and must stay out of logs and evidence.

## Join, update, and read

Each scope admits one writer and any number of readers. A scoped lease contains the scope ID, lease ID, epoch, and generation. The scope revision changes only when that scope changes, so updates to another disjoint scope do not cause a scope revision conflict.

`scope.snapshot` returns only the granted subtree and its local data namespace. Paths are localized within that projection (`/value` rather than `/focus/value`). A scope-only member receives `SCOPE_REQUIRED` from full `world.snapshot`; it cannot read sibling subtree contents or sibling namespace data.

`scope.patch` supports atomic `props`, `insert`, `remove`, `replace`, and `move` batches inside the caller's subtree. The scope root itself cannot be removed or moved by its child writer. Keep controls display-only unless the Host advertises `scope_interactions` and the provider has called `client.require_scope_interactions()`. Data bindings are localized on snapshots and written back under the scope's own namespace.

## Read scope lifecycle metadata

The optional `scope_status` capability reports whether a scope is `online`, `stale`, `vacant`, `revoked`, or `unknown`. It returns only world/scope IDs, requested/current generation, scope revision, world sequence, and status. It does not expose scope data, component trees, or writer identity.

```python
client.require_scope_status(version=1)
status = await client.read_scope_status(
    world_id,
    scope_id,
    scope_generation,
)
```

Only a trusted local operator, an active world authority, or a member of the requested scope may read its status. An expired authority cannot inspect sibling scopes; a session that remains a member can still inspect its own scope. `stale` means a writer previously claimed the scope but no current valid writer lease exists. `revoked` means the requested generation was fenced or a retained removal tombstone confirms deletion. A future generation, unknown scope, or evicted tombstone returns `unknown`; do not infer that an external business session was revoked from this Host status. Source health and local-file freshness remain separate provider-owned facts.

## Share typed state deliberately

State slots are a preview coordination channel attached to an owning scope. They do not store provider business truth, expose pointers, or make arbitrary JSON globally writable. Values must match one of the advertised scalar schemas: boolean, bounded integer, finite bounded number, bounded string, or enum. The host enforces a per-value byte cap and per-world/per-scope slot quotas.

The owning scope writer creates a slot and names any reader scopes explicitly. A reader must both join one of those scopes and match the granted scope generation. Only the writer of the owning scope may update, change readers, or delete the slot; updates use the slot's own revision and compare-and-set:

```python
client.require_state_slots(version=1)
slot = await client.create_state_slot(
    world_id,
    focus_scope_lease,
    "focus.progress",
    {"type": "integer", "min": 0, "max": 100},
    25,
    [{"scope_id": tasks_scope_id, "generation": tasks_scope_generation}],
)

value = await client.read_state_slot(
    world_id,
    slot["slot_id"],
    slot["generation"],
    tasks_scope_id,
    tasks_scope_generation,
)
updated = await client.compare_and_set_state_slot(
    world_id,
    focus_scope_lease,
    slot["slot_id"],
    slot["generation"],
    value["revision"],
    30,
)
```

The SDK checks the nested `state_slots` capability and its schema/access rules before sending a request. A stale concurrent write returns `STATE_REVISION_CONFLICT`; read the latest slot and make a new decision instead of blindly replaying a timed-out write. Removing a reader grant blocks later reads. Removing the owner scope deletes its slots; removing a reader scope removes that grant; parent authority revocation clears all child scopes and slots. A provider that already received a snapshot may retain that copy, so revocation controls future host reads rather than erasing data already observed.

Slot operations are short, synchronous host mutations. They do not wait for reader providers or hold a lock across network or human interaction. Use them only for deliberately shared coordination values; keep durable or business-authoritative state in its provider.

The root authority may configure window properties and use `scope.structure.patch` on unowned layout. It may move an intact child root/group between unowned layout parents. It cannot patch inside a child scope or move a scope into another scope. Removing a child root or an unowned ancestor containing it atomically removes that scope and its data namespace, fences its grant, and sends `scope.revoked` to joined readers/writers. Replacing a parent that still contains child scopes is rejected; remove it explicitly so the scopes are revoked.

Releasing, disconnecting, expiring, or rescuing the root authority increments child generations/epochs, rotates grants, and fences active child writers. Existing readers receive a final filtered `scope.snapshot` with stale status. Old grants cannot reacquire access; recreate the temporary composition world to issue new grants. The root authority snapshot is redacted to remove child content and scoped data. The trusted local operator can still render and inspect the aggregate window.

Joined scope readers receive server-filtered `scope.snapshot` events as their scope changes. They do not receive a complete `world.snapshot` and then hide siblings in the client. The SDK cache is keyed by `(world_id, scope_id)` and accepts only newer `(generation, revision)` snapshots; `scope.revoked` clears that entry.

Use the capability-aware helpers before each optional feature:

```python
await client.patch_scope(world_id, scope_lease, scope_revision, [
    {"op": "insert", "parent": "focus-panel", "index": 1,
     "node": {"id": "focus-note", "kind": "text", "props": {"text": "synthetic"}, "children": []}}
])
await client.patch_structure(world_id, authority_lease, world_revision, [
    {"op": "remove", "node_id": "obsolete-panel"}
])
```

The SDK checks the advertised operation list and root structure capability before sending those requests. Cross-scope moves and unsupported features fail closed in the host.

## Failure and recovery

- A timeout has an unknown outcome; read the affected scope snapshot before deciding what happened.
- A child writer's own disconnect/expiry fences its lease; while root authority remains active, it may rejoin with its current grant and receive a new lease epoch.
- Parent authority release, disconnect, expiry, rescue, or deletion of a containing layout node invalidates child generations/grants. Old writers cannot reacquire under that parent; use the updated filtered snapshot for read-only recovery or rebuild the composition world to issue new grants.
- Local rescue holds the world and revokes root and scoped writers. A provider cannot reclaim until the user releases the hold.
- A composition world cannot silently revert to stable whole-world ownership. Destroy it and rebuild a new world in exclusive mode, or use a future explicit migration operation.

Run the synthetic real-host probe with an actual local descriptor:

```powershell
python examples/python/scope_probe.py --runtime "<actual runtime descriptor path>"
```

It verifies preview negotiation, independent writers, scope-local insert/move, filtered live reader updates, stable 0.3 refusal, root-authority scope deletion/revocation, stale-lease rejection, and destruction of only its own temporary world. It does not prove Tauri pixels or native window presentation.

The probe also exercises typed state-slot creation, a pair of competing CAS writes, filtered reader authorization, wrong-type rejection, reader-grant revocation, and explicit slot deletion over the real Rust WebSocket host.

For the B07-04 two-source isolation check, `examples/python/composition_probe.py` reads an explicitly staged TrafficMonitor bridge snapshot and the selected open Obsidian vault through the fixed Obsidian Workspace query. Start a separate headless Rust host, pass the actual descriptor/metrics path/vault name, wait for `READY_FOR_TRAFFICMONITOR_FAILURE`, then stop only the marked temporary TrafficMonitor stage and create the supplied failure marker. The probe verifies that the traffic scope alone becomes stale while the Obsidian Workspace scope remains unchanged, then destroys only its temporary world. It never writes notes, plugin settings, TrafficMonitor configuration, or durable source data. This verifies the Rust protocol and provider boundary; it does not prove Tauri window rendering.
