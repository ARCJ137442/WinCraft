# Component scope leases: 0.4 preview

**Status:** experimental preview, not part of stable protocol 0.3. The implementation is the B07-01 slice; structural transactions and owner-routed interactions are not included yet.

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

The B07-01 preview accepts `props` patches for nodes inside the scope and full replacement of that scope's own data namespace. Cross-scope writes return a permission error. Cross-scope insert/move/delete/replace and parent-scope revocation are intentionally deferred to B07-02. Interactive components are rejected during partition because action routing by component owner is not implemented until B07-04.

The root authority may configure window properties and destroy its world, but it cannot use stable whole-scene replacement to overwrite the child scopes. Its snapshot is redacted to remove child content and scoped data. The trusted local operator can still render and inspect the aggregate window.

## Failure and recovery

- A timeout has an unknown outcome; read the affected scope snapshot before deciding what happened.
- Disconnect, expiry, or explicit leave fences the old scoped lease. Rejoin with the grant key in a new session and use the returned lease and scope generation.
- Local rescue holds the world and revokes root and scoped writers. A provider cannot reclaim until the user releases the hold.
- A composition world cannot silently revert to stable whole-world ownership. Destroy it and rebuild a new world in exclusive mode, or use a future explicit migration operation.

Run the synthetic real-host probe with an actual local descriptor:

```powershell
python examples/python/scope_probe.py --runtime "<actual runtime descriptor path>"
```

It verifies preview negotiation, independent writers, filtered readers, stable 0.3 refusal, and destruction of only its own temporary world. It does not prove Tauri pixels or native window presentation.
