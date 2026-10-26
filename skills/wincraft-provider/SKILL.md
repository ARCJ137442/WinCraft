---
name: wincraft-provider
description: >-
  Use when an Agent needs to become, build, debug, or verify a WinCraft provider;
  connect an automation program to a world; publish dynamic declarative components;
  handle leases, actions, reconnects, or native-window behavior; or adapt an external
  source such as Obsidian or TrafficMonitor to WinCraft.
---

# WinCraft Provider

Teach an Agent to drive a WinCraft world as a capable provider. A world is a native
window assembled from typed components. The provider owns business truth and sends
declarations, data, and action results; it never uploads HTML, JavaScript, or executable
code to the host.

## The first-world tutorial

Complete these lessons in order. Read [the protocol](../../docs/protocol.md) when a
method or field is unclear; the Rust implementation and schema are authoritative.

### 0. Prepare safely

1. Read `AGENTS.md`, `docs/product/DECISIONS.md`, `docs/protocol.md`, and
   `docs/architecture.md`.
2. Install the example provider dependencies with
   `python -m pip install -r examples/python/requirements.txt`.
3. Obtain the **actual** runtime descriptor path from the host manager or its startup
   output. Do not guess a port, enumerate another user's runtime files, print the
   descriptor, or copy its bearer token into logs, prompts, screenshots, or evidence.
   For a local Tauri integration run, launch the built desktop executable with
   `--open-manager` to open the internal manager explicitly; the normal launch remains
   tray-only.
4. For a remote provider, require an SSH tunnel or authenticated TLS. Never send the
   bearer token over plaintext remote `ws://`.

### 1. Join the host

Start from `examples/python/client.py`. The client reads the descriptor, checks the
protocol (`0.2` in this prototype) and `host_id`, opens an authenticated WebSocket, sends `hello`
with the exact protocol version, and maintains its session heartbeat. Keep that order and those checks. A stale
descriptor or mismatched host is a hard error.

Create a world with `world.create`, or join a known world with `world.join`. A write
join returns the one active window-level lease; a read join receives snapshots and
cannot mutate. Discovery only finds metadata; it grants no world or write permission.

### 2. Build the first scene

Send one `scene.replace` containing a root `stack` or `row` and supported leaf nodes:
`text`, `metric`, `progress`, `badge`, `button`, `input`, `key_value`, or `divider`.
Bind values with JSON Pointer `{"$path":"/..."}` or send a complete `data.replace`.
Keep IDs stable and unique: the renderer uses them to preserve component identity.
The default window belongs to the human: it is resizable, and a user's horizontal
resize remains in effect while content height is recalculated. Do not repeatedly send
window geometry to imitate user layout; request provider geometry control only when
the integration genuinely owns placement and size.
Window snapshots expose `surface_opacity`, defaulting to `0.8`. Set it with
`window.configure` only when the provider has a clear reason to change visual opacity;
the property affects the rendered surface while the native window remains transparent.
Window visibility is observable runtime state. A local minimize hides the native
window while keeping the world and lease alive; your next snapshot reports
`window.visible=false`. A current writer may restore it with `window.configure`
(`visible=true`, current lease, and expected revision), and the world manager can also
resurface a hidden world.
The custom title bar is visible and fixed outside the scrollable scene by default;
`title_bar_visible` may hide or restore it through `window.configure`. Pointer
click-through is disabled by default; enabling it also prevents users from clicking
the surface, so keep the manager rescue path available and restore it deliberately.

Use `protocol/examples/focus.scene.json` as the first working shape. Run
`examples/python/focus_demo.py` to see creation, data updates, an action, and an in-place
component replacement in one provider. Its focus/job business values are simulated;
they are not ExoMind or user data.

### 3. Keep building while connected

Use `scene.patch` for `insert`, `remove`, `replace`, `move`, or `props` operations after
the first scene. Patches are atomic: on any invalid operation, keep the previous scene
and revision, report the error, and recover from `world.snapshot`. Reconcile the
provider's desired component tree against the latest snapshot; do not recreate the
whole tree on every tick.

### 4. Handle interactions as requests

Buttons and inputs have a static action name. They may also declare a static
`context_action`; right-clicks are ignored unless it is registered, and the host
suppresses the browser's native context menu. Consume `interaction` events only for
your world, validate their shape, perform the provider-owned operation, update the
world with the resulting business state, then send `action.result` with the same event
ID and current lease. Report failure as failure. A delivered event is not proof that
the requested business operation succeeded.

The event ID is for correlation, **not** an idempotency key. If a provider action
causes an external side effect, use that service's own transaction/idempotency mechanism
before acknowledging it. Never retry a timed-out write blindly.

### 5. Survive expiry and reconnect

On disconnect, expiry, revocation, `resync_required`, or a host-ID mismatch:

1. Stop using the old lease immediately.
2. Reconnect and send a new `hello` to the verified host.
3. Rejoin and acquire a **new** lease epoch if writing is still allowed.
4. Read the current snapshot and rebuild the UI from the provider's source of truth.
5. Resume only after the new session and lease are verified.

Retry only an explicit `REVISION_CONFLICT` after rereading state. A timeout has an
unknown outcome; do not replay a write or action automatically. A local operator's
takeover/hold is authoritative. Do not try to reacquire control behind the user's back.

### 6. Respect the window owner

Human geometry is the default. Do not configure position or size unless the world is
explicitly in provider geometry mode. Human movement, click-through rescue, hiding,
recovery, and operator takeover belong to the local user. Accepted window intent is
not proof that Windows applied it; inspect the native report separately.

## Provider invariants

- Business records remain in their authoritative provider. WinCraft stores only
  rebuildable scene, input, session, and rendering state.
- One active writer owns the whole world lease. Readers get immutable snapshots.
- Validate protocol version, `host_id`, membership, lease ID/epoch, expected revision,
  and action result. Do not bypass checks to make a demo appear green.
- Keep source freshness visible. Missing, stale, rejected, or disconnected data is not
  zero and is not a successful empty result.
- Keep data bounded to protocol limits. Never pass HTML, CSS, JavaScript, `eval`, shell
  commands, arbitrary URLs, or general OS calls through component props or actions.
- A provider integration must state whether it is synthetic, file-backed, plugin-backed,
  or reading a live service. Do not label a mock as a real protocol test.

## Verification path

1. Run `python skills/wincraft-provider/scripts/verify.py` to check that the tutorial's
   links and working examples exist.
2. Run `python scripts/check_contracts.py` and the relevant UI build/tests after changing
   protocol-facing code.
3. Run `python examples/python/lease_probe.py --runtime "<actual descriptor>"` against
   the real Rust host. It exercises authentication, positive/atomic scene patches,
   fencing, reconnect, expiry, and a slow consumer; source test definitions alone do
   not count as passes.
4. Run your provider against the real host. Verify initial scene, data refresh, dynamic
   structure change, action result, source loss/staleness, and clean disconnect.
5. Use the Tauri release executable for native claims. Browser preview and headless
   protocol tests do not prove native window behavior.
6. Record command, exit code, environment, and evidence scope in `evidence/local/`.
   Keep runtime descriptors, tokens, private notes, and real business contents out of
   committed files and evidence screenshots.

## Guided examples

- `examples/python/focus_demo.py` — first provider and dynamic components.
- `examples/python/trafficmonitor_provider.py` — live values from the local
  TrafficMonitor bridge, when its companion plugin is loaded.
- For the plugin-backed Windows setup, staging boundary, and local run steps, follow
  the [TrafficMonitor provider reference](references/trafficmonitor.md).
- `examples/python/obsidian-workspace.py` — read-only Obsidian Workspace dashboard projection;
  it requires an explicitly named open Obsidian vault and never edits notes.
- `examples/python/lease_probe.py` — protocol acceptance against the actual Rust host.

When adapting a different source, reuse `client.py` and this sequence. Keep the adapter
thin; let the external application remain authoritative and let the shared renderer
remain the only component renderer.
