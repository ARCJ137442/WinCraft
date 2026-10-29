# Agent Board: synthetic read-only activity projection

This example uses only `fixtures/synthetic_activities.json`. It does not discover,
connect to, or read any Claude Code, Codex, OpenCode, DeepSeek Harness, or `omp`
session. The activity record in `protocol/activity.schema.json` is `draft-2026-10-29`,
a draft proposal and not a protocol 0.3 host method. The separate `draft-2026-10-26`
handoff schema remains preserved as its original planning artifact.

The aggregator keeps source status and freshness separate. Expired fresh records become
`stale`; disconnected/expired data cannot be normalized as idle or completed. Identity
is the tuple `device_id + provider_id + source_instance_id + session_id`; display names
and model names never participate. Parent sessions are rendered as containers and only
leaf sessions contribute to work-item counts. Incomplete, duplicate, or cyclic trees
fail closed.

The rendered scene contains only ordinary read-only components. It has no buttons,
inputs, native window actions, approval affordances, file writes, or continue-execution
actions. Source IDs, raw source statuses, and model details stay in the provider process;
only display summaries and aggregate counts enter scene data.

## One-window synthetic overview

`global_overview_provider.py` is a separate synthetic demo for the requested single
floating overview of Codex and Claude Code. Its first view shows the Codex parallel count,
the Claude session count, and up to three Claude session status previews. Source lists,
pagination, and per-session details appear only after a local view action. Only
`view.*` navigation actions are registered; the provider does not connect to real
Harness processes, approve work, write files, or continue sessions. Raw source status,
instance IDs, and model metadata are not sent to the renderer.

Given repository-owned synthetic activity records, when a user switches between sources
and opens a session, then the same world displays a bounded list/detail view with
freshness preserved and no business-side effects. Automated tests cover the projection,
navigation, stale view actions, empty states, and pagination.

To open the interactive synthetic view on the local host:

```powershell
python examples/integrations/agent-board/global_overview_provider.py --runtime "<actual descriptor path>" --duration-seconds 120
```

## One-window live CLI overview

`live_provider.py` reads only the current status metadata exposed by Claude Code
`agents --json` and the local Codex CLI `app-server` `thread/list` method. The Codex
request always sets `useStateDbOnly=true`, so it does not scan JSONL rollouts. It does
not read turn contents, prompt previews, names, working directories, or raw session IDs.
Session identities are hashed in memory; the renderer receives only bounded labels,
normalized statuses, freshness, and source-health badges. Actions remain local
`view.*` navigation.

Codex app-server is experimental and this adapter reports the CLI's local state database
as `Codex CLI · 本机状态库`. That source is distinct from the Codex App connector; the two
must not be silently treated as one inventory. Claude entries missing a stable identity
or state are skipped and mark that source `部分可用`. A source read failure leaves only
that source stale; a successful empty result is shown as `CLI 可查询` with zero records.
The `claude agents --json` endpoint lists Claude Code background-agent records, not every
interactive Claude conversation. Its `CLI 可查询` badge means the status command responded;
it does not claim that a Claude Code app or interactive session is still open. Blocked
background-agent records can remain visible after a foreground session closes.
Each live source row shows the time since its last successful local read; a disconnected
or expired source keeps that time visible so a user can distinguish old data from an empty
successful result.

To open the live, read-only view on the local host:

```powershell
python examples/integrations/agent-board/live_provider.py --runtime "<actual descriptor path>" --duration-seconds 600 --refresh-seconds 15
```

Given a successful CLI snapshot, when a source refreshes, then its own session list and
freshness update without approval, file-write, or continue-execution actions. If one
source fails, only that source becomes disconnected/stale and the other source remains
current.

## Codex App connector bridge

The Codex App connector is not the same source as the local Codex CLI state database.
`live_provider.py --codex-app-bridge` accepts one bounded JSON snapshot per stdin line
from an Agent that has the authorized Codex App MCP tools. The Agent can resolve
`project_label` with the project list and provide a clipped recent `agent_message` for
active threads; connector summaries are labeled separately. The Python Provider does
not invoke `mcp__codex_app` itself.

Opening Codex App alone does not send a snapshot to the Provider. The source stays
`等待 Agent 桥接` until an authorized Agent supplies one. Codex App rows show the
conversation title, status, project and a bounded recent-output excerpt; opening details
reveals more of the same output. Exact assistant messages and connector summaries are
labeled differently.

The bridge accepts only `thread_id`, `title`, `status`, `project_label`, a bounded
`last_agent_output`, its `last_output_kind`, and a source order. It does not accept
cwd, prompts, arbitrary URLs, commands, or tool arguments. Display text remains plain
text. When the host advertises `codex_thread_navigation`, clicking a Codex App title
passes a UUID-only `native_window_action`; the Windows host constructs
`codex://threads/<UUID>`. Without that capability the title is not an external link.
OS acceptance confirms a navigation request, not that the target conversation loaded.

```json
{"snapshot_version":1,"source_health":"online","threads":[{"thread_id":"00000000-0000-4000-8000-000000000001","title":"Synthetic Codex App thread","status":"active","project_label":"Synthetic project","last_agent_output":"Synthetic last Agent output","last_output_kind":"agent_message","source_sequence":0}]}
```

Start the bridge mode from the repository root, then let the authorized Agent write
newline-delimited snapshots to the Provider process stdin:

```powershell
python examples/integrations/agent-board/live_provider.py --runtime "<actual descriptor path>" --codex-app-bridge --duration-seconds 600 --refresh-seconds 15
```

The Codex App connector snapshot is held in process memory for rendering and expires
into a stale/disconnected source if updates stop. It is not written to repository files
or evidence. The current local host still needs end-to-end visual acceptance of the
Codex App deep link.

## Validate the model

From the repository root:

```powershell
python -m unittest tests.test_agent_activity_board -v
python scripts/check_contracts.py
```

## Open the synthetic world on a real local host

Install the repository's Python example dependencies, obtain the actual runtime
descriptor from the WinCraft manager, then run:

```powershell
python examples/integrations/agent-board/provider.py --runtime "<actual descriptor path>" --duration-seconds 30
```

The provider creates one ordinary invited world, publishes one static scene, waits for
the chosen duration, and destroys only its own world. It does not call any Harness
source or approval API. A timeout or disconnect can leave cleanup outcome unknown; check
the manager before retrying.
