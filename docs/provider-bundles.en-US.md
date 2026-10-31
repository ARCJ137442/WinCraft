# `.wcp` Provider code bundles

`.wcp` now carries two isolated manifest kinds: the existing `wincraft.pack.draft`
configuration pack and the local `wincraft.provider-bundle` code package. Configuration
packs remain blueprint-only and never execute code. Provider bundles use a separate
validation, preview, unpack, and per-launch confirmation flow.

## User flow

1. Run `python scripts/build_provider_bundle.py` from the repository to create the
   synthetic test package at `target/provider-bundles/wincraft-sample-provider.wcp`.
2. Open the WinCraft World Manager and drop the `.wcp` file onto it. The manager fills
   the path and previews its title, version, runtime, entrypoint, expanded size, and
   SHA-256 digest.
3. Choose **Install code (unpack only)**. No code runs and no Python dependency is
   installed at this step.
4. Choose **Run this Provider** to review the execution warning and entrypoint. The
   process starts only after the final confirmation.

To try the Obsidian plugin, run `python scripts/package_obsidian_plugin.py` to create
`target/obsidian-plugin/wincraft-workspace-dashboard.zip`, then follow the
[installation guide](integration-obsidian.en-US.md). If the Python Provider dependency
is missing, its launcher asks before installing the sample requirements with pip.

## Package boundary

The package contains the strict JSON manifest `wincraft-provider.json`, with `kind`,
`schema_version`, `id`, `version`, bilingual `title`, and a typed `entrypoint`. Entrypoints
are limited to `.py`, `.js/.mjs`, or Windows `.exe`. Entries must be regular files;
paths, file count, archive size, and expanded size are bounded. Symlinks, duplicate
paths, traversal, overwriting an installed version, and any package whose digest changed
after preview are rejected.

Installation writes only validated files into the local WinCraft Provider store.
Launching uses no shell, installs no dependencies, inherits no arbitrary environment
variables, and hides the runtime console. The Host stops Provider processes it started
when WinCraft exits. Python, Node, and `.exe` entrypoints all receive the standard
`--runtime <descriptor-path>` argument. The user confirms each run.

This is not a code sandbox. After confirmation, bundle code runs with the current
user's permissions. It can access files and network available to that user and can read
the bearer token in the runtime descriptor to exercise the connection's WinCraft
permissions. Run only trusted, reviewed code. Never package, commit, or put runtime
descriptors, their contents, or real business snapshots in evidence.

## Provider author notes

The sample manifest and builder are in `examples/provider-bundle-sample/` and
`scripts/build_provider_bundle.py`. An entrypoint must accept `--runtime <path>`, verify
Host identity, protocol, lease and capabilities, and clean up only worlds it created.
The `adapter` field in a configuration pack remains a reference; code cannot be hidden
inside a blueprint or configuration pack to avoid the separate execution confirmation.

This local prototype format is not a protocol 0.3 network feature and does not provide
dependency management, signed distribution, or sandbox isolation.
