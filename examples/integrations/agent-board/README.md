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
local project/session JSONL files and the local Codex CLI `app-server` `thread/list`
method. The Codex CLI request always sets `useStateDbOnly=true`, so it does not scan
rollout JSONL. Codex App uses its separate local state DB/rollout reader; Claude and
Codex App process presence is enumerated separately from their disk data. The renderer
receives bounded labels, normalized statuses, freshness, source health and data-read
health; actions remain local `view.*` navigation.

Codex app-server is experimental and this adapter reports the CLI's local state database
as `Codex CLI · 本机状态库`. It remains distinct from Codex Desktop's local state rows. Claude Code and Codex
App health badges mean the matching local process was found; their data-health badges and
last-read age are shown separately. Offline processes do not hide readable local history,
and unreadable data is not presented as an empty successful result.

To open the live, read-only view on the local host:

```powershell
python examples/integrations/agent-board/live_provider.py --runtime "<actual descriptor path>" --duration-seconds 600 --refresh-seconds 15
```

By default, the provider reads three separate local sources:

- **Codex CLI** uses `codex app-server thread/list` with `useStateDbOnly=true` and reads no rollout history.
- **Codex App** reads `CODEX_HOME/state_*.sqlite` in read-only mode, filters to `originator=Codex Desktop`, and reads a bounded rollout tail only after its `session_meta` UUID matches. It does not call the App, start an App server, or require an Agent connector.
- **Claude Code** enumerates top-level project session JSONL files and their known `session/<id>/subagents/agent-*.jsonl` children under `CLAUDE_CONFIG_DIR/projects` (or `~/.claude/projects`). It does not run `claude agents --json`.

For Codex App and Claude Code, source online/offline state comes from OS process metadata; session details come from the local files. The process check does not launch a Harness. When the process is absent, the source reports offline and continues to show readable history. A missing process is never presented as idle. Per-session status remains `unknown` when the persisted files do not contain authoritative status.

To verify only Codex CLI and Claude Code, select just those sources:

```powershell
python examples/integrations/agent-board/live_provider.py --runtime "<actual descriptor path>" --sources codex claude-code --duration-seconds 60 --refresh-seconds 15
```

In this mode the provider does not read Codex App state or rollouts; the App tab reports “本轮未查询”.

Given a source process is absent but its local session files remain readable, when the provider refreshes, then it shows that source as offline while retaining its bounded local history and last Agent output. If the process is present, the process badge reports online independently from disk-read quality and snapshot age. A failed read stales only that source; no process is launched to recover it.

Session titles, project labels, and output previews are treated as untrusted local text and sanitized before rendering. The provider does not send full prompts, thinking, tool output, file diffs, absolute paths, or process command lines to the Host. Codex App navigation remains a separate explicit click through the host's UUID-only `codex://threads/<UUID>` action; source monitoring itself does not communicate with or start the App.

## Shared session card fields

The default overview and source tabs use the same compact session-card shape: name,
status, project label, and a bounded latest-output excerpt. The default overview shows
up to two Codex CLI sessions, two Codex App sessions, and three Claude Code sessions;
source tabs reveal the rest. Per-session details reveal a longer bounded excerpt and
the source freshness.

Codex App cards read the newest `state_*.sqlite` in read-only mode and filter rows by
the exact `originator=Codex Desktop` marker. The adapter uses only thread identity,
title/name, cwd, archive state and the local rollout pointer. For at most four recent
rows, it verifies `session_meta.payload.id` against the thread UUID before reading a
bounded 1 MiB tail and extracting only `event_msg.agent_message` or
`task_complete.last_agent_message`. User messages, tool output, reasoning, absolute
paths and unmatched rollouts stay out of the card. Its local state query never writes
to SQLite; output caches remain in provider memory.

Claude Code reads top-level project session files plus the known nested
`<session UUID>/subagents/agent-*.jsonl` paths. It verifies the filename/session identity
and child `agentId`, keeps parent-child relations, and reads bounded tails only for the
most recent 24 entries. Session names come from local `custom-title`/`ai-title` records;
project labels use only the cwd's final directory segment. It never reads full prompts,
thinking blocks or tool results. Codex App and Claude Code process checks use image and
parent-process metadata only; they never start the target app or inspect command-line
arguments. Process absence is displayed separately from readable history.

Codex CLI continues to use `thread/list` with `useStateDbOnly=true`, then calls
read-only `thread/read` for at most the four most recently updated threads and extracts
only the last `agentMessage`; the app-server response may contain earlier turns, but
they are discarded in memory. The unlabelled `thread/list` preview is ignored. All
source identities are hashed, selected text is clipped/redacted and retained only in
process memory. No transcript text is written to the repository, logs or evidence.
When the Host advertises `codex_thread_navigation`, a user click can open the UUID-only
`codex://threads/<UUID>` action; this is a navigation request, not a data connector.

When a source does not expose a usable Agent message, the card says `暂无最近 Agent
输出`; it does not relabel a user prompt or tool output as an Agent response.

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
