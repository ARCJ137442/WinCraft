"""Interactive one-window Codex/Claude overview using synthetic fixtures only."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Mapping

PYTHON_EXAMPLES = Path(__file__).resolve().parents[2] / "python"
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import Client, add_runtime_args, destroy_world_safely, event_world_id, require_runtime  # noqa: E402
from global_overview import (  # noqa: E402
    GlobalOverviewState,
    build_global_overview_scene,
    load_synthetic_global_projection,
    transition_view,
)


async def handle_view_interaction(
    client: Any,
    world_id: str,
    lease: Mapping[str, Any],
    projection: Mapping[str, Any],
    state: GlobalOverviewState,
    detail_targets: Mapping[str, tuple[str, str, str, str]],
    page_count: int,
    event: Mapping[str, Any],
) -> tuple[GlobalOverviewState, dict[str, tuple[str, str, str, str]], int]:
    """Apply a local navigation event and acknowledge it without source-side effects."""
    action = str(event.get("action", ""))
    component_id = str(event.get("component_id", ""))
    next_state = state
    next_targets = dict(detail_targets)
    next_page_count = page_count
    ok = True
    message: str | None = None
    try:
        next_state = transition_view(state, action, component_id, detail_targets, page_count)
        scene, next_targets, next_page_count = build_global_overview_scene(projection, next_state)
        await client.mutate("scene.replace", world_id, dict(lease), scene=scene)
    except Exception as exc:
        ok = False
        # UI acknowledgements expose a bounded, non-sensitive error category only.
        message = f"View update failed ({type(exc).__name__})."
        next_state = state
        next_targets = dict(detail_targets)
        next_page_count = page_count
    await client.call(
        "action.result",
        {
            "world_id": world_id,
            "lease": dict(lease),
            "event_id": event["id"],
            "ok": ok,
            "message": message,
        },
    )
    return next_state, next_targets, next_page_count


async def cleanup_global_overview_world(
    client: Any,
    world_id: str,
    lease: Mapping[str, Any],
) -> None:
    """Confirm cleanup if the local operator already destroyed this world."""
    try:
        await destroy_world_safely(
            client,
            world_id,
            lease,
            provider_name="Global Agent Overview",
        )
    except RuntimeError as cleanup_error:
        if getattr(cleanup_error.__cause__, "code", None) != "NOT_FOUND":
            raise
        try:
            await client.call("world.snapshot", {"world_id": world_id})
        except Exception as verification_error:
            if getattr(verification_error, "code", None) == "NOT_FOUND":
                print("Global Agent Overview cleanup confirmed after local world close.", flush=True)
                return
            raise cleanup_error from verification_error
        raise cleanup_error


async def run(args: argparse.Namespace) -> None:
    world_id: str | None = None
    lease: dict[str, Any] | None = None
    world_deleted = False
    async with Client(args.runtime, "python.agent-board.global-overview.synthetic", args.ws_url) as client:
        created = await client.call(
            "world.create",
            {
                "window": {
                    "title": args.title,
                    "width": 520,
                    "height": 440,
                    "always_on_top": True,
                    "geometry_control": "human",
                },
                "join_policy": "invite",
                "claim": True,
            },
        )
        world_id = created["world"]["id"]
        lease = created.get("lease")
        if not isinstance(lease, dict):
            raise RuntimeError("Host did not issue a writer lease for the synthetic overview")

        projection = load_synthetic_global_projection()
        state = GlobalOverviewState()
        try:
            scene, detail_targets, page_count = build_global_overview_scene(projection, state)
            await client.mutate("scene.replace", world_id, lease, scene=scene)
            print(
                "Global Agent Overview uses repository-owned synthetic records only; "
                "it does not inspect or control Codex/Claude sessions.",
                flush=True,
            )
            deadline = asyncio.get_running_loop().time() + args.duration_seconds
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    message = await asyncio.wait_for(client.events.get(), timeout=remaining)
                except TimeoutError:
                    break
                event_name = message.get("event")
                data = message.get("data", {})
                if event_name == "world.deleted" and event_world_id(message) == world_id:
                    world_deleted = True
                    return
                if event_name in ("connection.error", "connection.closed", "provider.error"):
                    raise ConnectionError("Global overview connection ended; source data was not written.")
                if event_name != "interaction" or not isinstance(data, dict) or data.get("world_id") != world_id:
                    continue
                state, detail_targets, page_count = await handle_view_interaction(
                    client,
                    world_id,
                    lease,
                    projection,
                    state,
                    detail_targets,
                    page_count,
                    data,
                )
        finally:
            if world_id is not None and lease is not None and not world_deleted:
                await cleanup_global_overview_world(client, world_id, lease)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=120,
        help="How long to keep the synthetic interactive window open (1..600)",
    )
    parser.add_argument(
        "--title",
        default="Agent Activity · 全局纵览（合成）",
        help="Window title for distinguishing the synthetic test world",
    )
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 1 <= args.duration_seconds <= 600:
        parser.error("--duration-seconds must be between 1 and 600")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
