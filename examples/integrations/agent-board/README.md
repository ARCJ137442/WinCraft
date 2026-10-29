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

## One-window global overview

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
navigation, stale view actions, empty states, and pagination; a real Codex/Claude data
adapter remains a separate NOT_RUN boundary.

To open the interactive synthetic view on the local host:

```powershell
python examples/integrations/agent-board/global_overview_provider.py --runtime "<actual descriptor path>" --duration-seconds 120
```

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
