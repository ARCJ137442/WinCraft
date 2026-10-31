# Draft WinCraft pack export

`export_pack.py` creates a configuration-only `.wcp` archive with kind
`wincraft.pack.draft` from an explicit draft
pack and its referenced blueprint. It validates both files against the proposals in
`docs/strategy/2026-10-26/contracts/`, bounds each JSON input to 1 MiB, rejects
traversal and symlinked blueprint paths, and never overwrites an existing output.

The archive contains only `pack.json` and the referenced blueprint JSON. It does not
include a Provider binary, runtime descriptor, lease, or installer. Adapter entries
are references only; this command does not download or execute them. Exporting does
not import or apply a pack, start a Host, or contact any network service.

Example:

```powershell
python tools/pack/export_pack.py `
  --pack docs/strategy/2026-10-26/examples/packs/workday.pack.json `
  --output workday.wcp
```

This configuration archive is distinct from the local executable Provider bundle
kind `wincraft.provider-bundle`. Dragging a Provider bundle to the manager does not
change the behavior of this exporter or the configuration-only import path. See the
[Provider bundle guide](../../docs/provider-bundles.zh-CN.md).

This is a draft interchange format, not a protocol 0.3 feature. Review the pack's
human-readable titles and adapter reference before sharing; schema validation cannot
decide whether user-authored text is private.

## Importing on this Host

The current Windows manager has a local configuration-pack flow:

1. Paste the `.wcp` path into **Configuration packs** and choose **Preview pack**.
2. Review each new window's properties, provider matches, requested permissions,
   warnings, inventory generation, and preview expiry.
3. If a provider permission is missing, approve only the requested declared capability.
   That changes the inventory generation and invalidates the old preview, so preview again.
   The Provider must also claim `world.import.accept`; the Python SDK helper
   `require_provider_import()` fails closed on Hosts that do not advertise its preview contract.
4. **Apply and create windows** is a separate explicit action. It creates new worlds and
   assigns a selected provider the exclusive writer lease for its window. Existing worlds
   are never replaced. Each world can have only one distinct writer; conflicts are blocked.
5. **Rollback** is a two-step action. It removes only worlds whose imported scene/window,
   revision, lease epoch and membership still match the import ledger. Edited or joined
   worlds are kept and reported as a partial rollback.

The manager reads exactly the two JSON entries from the archive, enforces input and path
limits, rejects extra files and symlinks, and never executes an adapter reference.
Blueprints contain a declarative component tree and a restricted set of window properties;
`Scene.data`, device coordinates, credentials, sessions and leases are excluded. Native
window creation happens per window after the Host accepts the import; it is not an OS-level
multi-window transaction. The manager reports each window's actual native state separately.

This local manager flow is not a stable protocol 0.3 method. The preview/apply/rollback
ledger exists only in Host memory, and imported worlds remain ephemeral. Applying a pack
never synchronizes later changes over a user's existing window.

For a synthetic end-to-end provider exercise, start `examples/python/pack_provider_demo.py`
with the manager's actual runtime descriptor, then export `workday.pack.json` and enter the
resulting `.wcp` path in the manager. The provider claims `world.import.accept`, refreshes its
inventory while waiting, and only updates the imported world after it validates the
user-confirmed event. It uses synthetic values and leaves the world alive on exit.
