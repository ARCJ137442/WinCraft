# Component scope leases: 0.4 preview

**Status:** experimental preview, not part of stable protocol 0.3. B07-01/02 implement disjoint scope writers, scoped structural transactions, parent revocation, and filtered live snapshots. Component action routing and typed shared state remain future work.

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

`scope.patch` supports atomic `props`, `insert`, `remove`, `replace`, and `move` batches inside the caller's subtree. The scope root itself cannot be removed or moved by its child writer. Inserted/replaced nodes must remain display-only until component action routing is implemented. Data bindings are localized on snapshots and written back under the scope's own namespace.

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
