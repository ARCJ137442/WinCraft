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

For the staged path from first connection to native-window integrations, use the
[provider journey](../../docs/provider-journey.md). It is a navigation aid over the
lessons and references below; the protocol, schemas, and Rust implementation remain
authoritative.

## The first-world tutorial

Complete these lessons in order. Read [the protocol](../../docs/protocol.md) when a
method or field is unclear; the Rust implementation and schema are authoritative.

For a guided, real-host walkthrough, run `examples/python/provider_tutorial.py` with the
actual runtime descriptor path shown by the manager. It uses the shared `client.py`,
ordinary components, and synthetic values; it does not read external business data.
The tutorial creates one ordinary invited world and destroys only that world on exit.
If a create/destroy result times out, the outcome is unknown: inspect the manager before
retrying. Do not treat this provider as the internal manager or an operator.

The five interactive lessons are:

1. **看见第一个世界** — create a world, move it, then optionally hide and resurface it
   through the local manager.
2. **搭一块会变的方块** — replace data and insert a component with `scene.patch`.
3. **与程序对话** — send a choice or input to provider-owned demo state and acknowledge
   its interaction.
4. **换一个自己的外观** — apply or reset the bounded `theme_tokens` feature.
5. **发现与加入是两件事** — summarize `world.list` metadata and join policies only;
   the lesson never opens another world's scene. Stable Protocol 0.3 remains world-only;
   the optional Provider inventory is a separate 0.4 preview capability.

Every lesson can be skipped. The course banner and all values identify the content as
synthetic. Use an isolated test host for repeatable runs. If a connected host does not
advertise `theme_tokens`, the provider must fail before creating a world.

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
protocol (stable `0.3` by default) and `host_id`, opens an authenticated WebSocket, sends
`hello` with the exact protocol version, and maintains its session heartbeat. Keep that
order and those checks. A stale descriptor or mismatched host is a hard error. The
separate `0.4-preview.1` component-scope path requires an explicit `protocol_version`
selection and a matching host capability; see [component scope preview](references/component-scopes-preview.md).

Create a world with `world.create`, or join a known world with `world.join`. A write
join returns the one active window-level lease; a read join receives snapshots and
cannot mutate. `world.list` returns only worlds this session has joined plus explicitly
`open_authenticated` non-system worlds. Unjoined invite-only worlds stay hidden. A listed
world still requires `world.join` before its snapshot can be read; discovery grants no
membership or write permission.

### Optional Provider inventory (0.4-preview.1)

Use the inventory only after selecting an endpoint descriptor and negotiating
`0.4-preview.1`:

```python
client.require_provider_inventory()
registered = await client.register_provider_inventory(registration_snapshot)
inventory = await client.list_provider_inventory()
```

Registration accepts bounded source ID/instance ID, type, display label, adapter version,
source state, claimed capabilities, freshness timestamp, and TTL. The schema rejects
unknown fields; a Provider cannot submit `grants`. The Host returns an empty `grants`
list, so registration and listing do not authorize a source operation, join a world, or
obtain a lease. Treat `capabilities` as source claims and check `grants` separately.

Each inventory response includes its `endpoint_id`. An Agent may query multiple endpoints
only when each descriptor was explicitly selected and authenticated; do not discover
endpoints by scanning processes, files, browser profiles, or the LAN. `state` reports
online/offline/degraded, while `source_updated_at` and `fresh_for_seconds` carry freshness.
The registry is in-memory and is rebuilt after Host restart. Stable 0.3 providers continue
to use `world.list`; the Host omits `provider_inventory` from their capability table.

### 2. Build the first scene

Send one `scene.replace` containing a root `stack` or `row` and supported leaf nodes:
`text`, `metric`, `progress`, `badge`, `button`, `input`, `key_value`, or `divider`.
The optional `textarea` node is available only when the host capability table advertises it.
For the Popup-Ask form pattern, check every optional behavior before creating its world:
`client.require_capabilities(components=("textarea",), keyboard_shortcuts=("escape", "ctrl_enter"), button_features=("selection_groups",))`.
Bind values with JSON Pointer `{"$path":"/..."}` or send a complete `data.replace`.
Keep IDs stable and unique: the renderer uses them to preserve component identity.
The default window belongs to the human: it is resizable, and a user's horizontal
resize remains in effect while content height is recalculated. `geometry_control`
controls size ownership. An optional `position_control` independently selects who may
set placement; when omitted it inherits `geometry_control`, preserving older providers.
Check `client.require_capabilities(window_properties=("position_control",))` before
using the split. For a fixed-size but user-movable HUD, request
`geometry_control="provider"`, `position_control="human"`, and `resizable=false`.
With `background_drag_enabled=true`, blank non-text, non-interactive regions can move
the native window even when the custom title bar is hidden. Buttons, links, inputs,
text, and an active text selection are excluded as drag surfaces. Do not repeatedly send
window geometry to imitate user layout; request provider ownership only for the
dimension the integration genuinely owns.
Windows default to `always_on_top=true`; a provider can explicitly opt out or restore
topmost behavior with `window.configure`. This keeps a world above ordinary windows,
while the OS continues to order it relative to other topmost windows.
Check `client.require_capabilities(window_properties=("always_on_top",))` before
depending on this property from a host implementation.
Window snapshots expose `surface_opacity`, defaulting to `0.8`. Set it with
`window.configure` only when the provider has a clear reason to change visual opacity;
the property affects the rendered surface while the native window remains transparent.
With provider position control, a window can use `anchor: {corner, margin_x, margin_y}`
instead of fixed `position`. The corner is relative to the selected monitor work area and
margins are logical pixels scaled by that monitor's DPI. The host clamps the result into
the work area. Human position control rejects provider position/anchor writes; a local
move clears an existing anchor. Local rescue clears the anchor and restores human control.
Anchors remain capability-gated as `window_property:anchor`.
Window visibility is observable runtime state. A local minimize hides the native
window while keeping the world and lease alive; your next snapshot reports
`window.visible=false`. A current writer may restore it with `window.configure`
(`visible=true`, current lease, and expected revision), and the world manager can also
resurface a hidden world.
The custom title bar is visible and fixed outside the scrollable scene by default;
`title_bar_visible` may hide or restore it through `window.configure`. Pointer
click-through is disabled by default; enabling it also prevents users from clicking
the surface, so keep the manager rescue path available and restore it deliberately.
Window snapshots expose `text_selectable=true` by default. The writer may change it with
`window.configure`; it controls the whole world's default text-selection behavior while
renderer component styles can override individual elements. The title bar remains
unselectable in either mode. Providers cannot submit CSS or scripts to create overrides.

An optional scene theme is available only when `ready.capabilities.scene_features`
contains `theme_tokens`. Call `client.require_capabilities(scene_features=("theme_tokens",))`
before sending `scene.theme`. The allowlist contains only background/foreground/accent
colors, font scale, radius, and spacing; never send CSS, markup, scripts, remote assets,
or a `trusted_chrome` claim. The host owns the title bar, provider identity, status,
permission cues, and rescue controls. OS high contrast/reduced motion and local user
text zoom override provider styling. An invalid token returns `INVALID_SCENE` atomically;
read the snapshot and correct the theme explicitly instead of replaying unrelated writes.
See [the scene theme guide](references/theme.md).

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

Buttons and inputs have a static action name. A button may declare the capability-gated
`shortcut: "escape"` together with a distinct static `shortcut_action`; a textarea may
use `shortcut: "ctrl_enter"` the same way. Each fixed shortcut is registered at most once
per world. The click and keyboard actions remain distinct. Option buttons can declare a
shared `selection_group`, its `selection_mode`, and `pressed` state when the host advertises
`button_features: ["selection_groups"]`; this gives the group one Tab stop and arrow-key
navigation while preserving provider-owned selection state.
Buttons, inputs, and textareas may also declare a static `context_action`; right-clicks
are ignored unless it is registered, and the host suppresses the browser's native context menu. Consume `interaction` events only for
your world, validate their shape, perform the provider-owned operation, update the
world with the resulting business state, then send `action.result` with the same event
ID and current lease. Report failure as failure. A delivered event is not proof that
the requested business operation succeeded.

The event ID is for correlation, **not** an idempotency key. If a provider action
causes an external side effect, use that service's own transaction/idempotency mechanism
before acknowledging it. Never retry a timed-out write blindly.

If `ready.capabilities.button_features` includes `external_window_actions`, a button
may declare the host-managed `native_window_action` described in
[the native window action guide](references/native-window-actions.md). Check the
capability before creating the world. The current allowlist is `obsidian` and
`traffic_monitor`, with `activate`, `maximize`, `restore`, and `minimize` operations
plus an optional bounded `title_contains` filter. The host performs the OS operation only after a trusted
renderer interaction, then forwards the same interaction to the provider for its normal
acknowledgement. On native failure, the provider receives no event and the user sees a
failure result. Do not add process paths, shell commands, AHK, or OS code to provider
props; ordinary world visibility and geometry still use the world APIs.

For read-only changes to a joined world's position/size or logical visibility, use the
session-scoped event flow in [the window state event guide](references/window-events.md).
Read event types from the host capability table first. Subscriptions do not grant a
world read membership, writer lease, or permission to trigger native actions.

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

## Experimental component-scope preview

Stable protocol 0.3 still has one writer for the whole world. The opt-in
`0.4-preview.1` scope path adds filtered subtree snapshots and one writer per disjoint
scope while retaining a separate world/window authority. Scope writers can apply
atomic insert/remove/replace/move/props patches only inside their fixed subtree;
root authority edits only unowned layout through `scope.structure.patch`. Parent
revocation fences descendant generations, and scope readers receive filtered live
`scope.snapshot` events plus `scope.revoked` notices. Cross-scope moves and
component action routing remain unsupported. B07-03 also exposes explicitly shared,
typed state slots with owner-scope CAS. Values are bounded scalars, reader grants are
scope-generation specific, and slots never become provider business truth or arbitrary
JSON references. Call `client.require_state_slots(version=1)` before using slot helpers.
Follow the [scope preview guide](references/component-scopes-preview.md) exactly; use
the capability-aware SDK helpers and never treat preview methods as stable 0.3.
For real-source scope isolation, `examples/python/composition_probe.py` requires an
explicit runtime descriptor, TrafficMonitor bridge path, and currently open Obsidian
vault. It runs a fixed read-only Obsidian Workspace query, creates/destroys only its own test
world, and waits for the runner to stop the staged TrafficMonitor copy; never point it
at the original installation's configuration or put source values in evidence.

## Provider invariants

- Business records remain in their authoritative provider. WinCraft stores only
  rebuildable scene, input, session, and rendering state.
- Stable protocol 0.3 has one active writer for the whole world lease; readers get
  immutable snapshots. The experimental 0.4 preview has one writer per disjoint scope,
  filters each scope snapshot, and keeps window authority separate.
- Validate protocol version, `host_id`, membership, lease ID/epoch, expected revision,
  and action result. Do not bypass checks to make a demo appear green.
- Lifecycle deletion is `{"event":"world.deleted","world_id":"..."}` with a
  top-level `world_id`; interaction events put the world identity in `data`. Use
  `client.event_world_id(message)` and match only your own world before stopping. If a
  destroy request returns `NOT_FOUND`, verify absence with a read-only snapshot before
  reporting cleanup complete; never blindly retry a timed-out destroy.
- Keep source freshness visible. Missing, stale, rejected, or disconnected data is not
  zero and is not a successful empty result.
- Keep data bounded to protocol limits. Never pass HTML, CSS, JavaScript, `eval`, shell
  commands, arbitrary URLs, process paths, or general OS calls through component props
  or actions; use only the capability-gated native window operation allowlist.
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
  it requires an explicitly named open Obsidian vault and never edits notes; its title
  activates an existing Obsidian window through the native host action.
- `examples/python/lease_probe.py` — protocol acceptance against the actual Rust host.
- `examples/python/scope_probe.py` — opt-in 0.4 preview probe against the actual Rust host;
  uses synthetic scopes and cleans up only its temporary world.
- `examples/python/composition_probe.py` — B07-04 real-source fault-isolation probe using
  an explicit staged TrafficMonitor snapshot path and an open Obsidian vault; both source
  integrations are read-only and its temporary WinCraft world is destroyed.
- `examples/integrations/agent-board/README.md` — B08-01 draft activity model and a
  synthetic-only read-only aggregate provider. It does not connect to live Harness
  sessions, and the activity schema is not a protocol 0.3 host method.
- `examples/integrations/agent-board/global_overview_provider.py` — B08-03 single-window
  Codex/Claude Code source switcher using synthetic activity only. Local `view.*`
  navigation does not grant access to live sessions or provide approval/write actions.
- `examples/integrations/agent-board/live_provider.py` and `live_sources.py` — read-only
  local Harness adapters. Claude Code uses `agents --json`; Codex CLI uses the
  experimental app-server `thread/list` method with `useStateDbOnly=true`; Codex Desktop
  local fallback filters a read-only SQLite state database by the exact `Codex Desktop`
  originator and keeps missing status explicitly unknown. A matched local rollout tail
  contributes only a bounded, sanitized `agent_message`. The Codex CLI state database
  and Codex App connector remain distinct sources; never merge their counts as one source.
  Claude `agents --json` reports background-agent records, not every interactive Claude
  conversation. A successful CLI query proves that the command responded, not that the
  Claude Code UI or an interactive session is open; keep source reachability separate from
  agent status and display the last successful read age.
- When an authorized Codex App connector is available to the calling Agent, that Agent can
  send a whitelisted JSONL snapshot to `live_provider.py --codex-app-bridge` over stdin:
  UUID thread id, title, status, project label, source order, and a bounded last-output
  excerpt. `list_threads`/`list_projects` supply sidebar metadata; use `read_thread` only
  with a small turn limit and output cap when an exact last assistant message is needed.
  Do not send full tool results, cwd, credentials, complete turn histories, or JSONL
  rollouts. The Provider treats every title/output as untrusted plain text and does not
  execute it. Having Codex App open does not automatically populate the live bridge. The
  local fallback can expose bounded title/project metadata, with status unknown until a
  connector snapshot arrives; if neither source is available, report the source as waiting.
- Codex App title links require `codex_thread_navigation`. The host accepts only a typed
  UUID and constructs `codex://threads/<UUID>` itself; never send a general URL or shell
  command. Clicks are explicit user actions, and OS acceptance is not proof that the
  target conversation loaded. Missing identity/state yields a partial source; a source
  failure stales only that source.
- `examples/integrations/device-inbox/README.md` — B09-01 draft message envelope,
  duplicate/TTL/revocation policy, and synthetic-only read-only projection. Authentication
  evidence must come from an external transport adapter; this example opens no listener.
- `examples/python/theme_demo.py` — synthetic theme preview, host-chrome boundary, and an explicit invalid-token rejection probe.
- `examples/python/popup_ask_provider.py` — optional WinCraft transport for an installed
  Popup-Ask skill; it reuses that skill's validate-only parser and result serializer.
  The adapter requires an explicit skill-script path and runtime descriptor and creates
  a temporary ordinary world; see [the transport reference](references/popup-ask.md).
- `protocol/examples/theme.scene.json` — capability-gated scene theme fixture.

When adapting a different source, reuse `client.py` and this sequence. Keep the adapter
thin; let the external application remain authoritative and let the shared renderer
remain the only component renderer.
