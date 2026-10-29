# Draft WinCraft pack export

`export_pack.py` creates a configuration-only `.wcp` archive from an explicit draft
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

This is a draft interchange format, not a protocol 0.3 feature. Review the pack's
human-readable titles and adapter reference before sharing; schema validation cannot
decide whether user-authored text is private.
