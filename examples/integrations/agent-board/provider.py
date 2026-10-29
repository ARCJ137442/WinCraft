"""Run a short-lived Agent Board using synthetic read-only activity fixtures."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

PYTHON_EXAMPLES = Path(__file__).resolve().parents[2] / "python"
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import Client, add_runtime_args, require_runtime  # noqa: E402
from activity_board import aggregate_activities, build_scene, load_synthetic_activities  # noqa: E402


async def _destroy_owned_world(client: Client, world_id: str, lease: dict[str, Any]) -> None:
    """Finish cleanup before propagating cancellation or an unknown outcome."""
    cleanup = asyncio.create_task(
        client.call("world.destroy", {"world_id": world_id, "lease": lease})
    )
    was_cancelled = False
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            was_cancelled = True
        except Exception as exc:
            raise RuntimeError(
                "Agent Board world cleanup outcome is unknown; inspect the manager before retrying"
            ) from exc
    if cleanup.cancelled():
        raise RuntimeError(
            "Agent Board world cleanup was cancelled; inspect the manager before retrying"
        )
    error = cleanup.exception()
    if error is not None:
        raise RuntimeError(
            "Agent Board world cleanup outcome is unknown; inspect the manager before retrying"
        ) from error
    print("Agent Board test world cleanup confirmed.", flush=True)
    if was_cancelled:
        raise asyncio.CancelledError


async def run(args: argparse.Namespace) -> None:
    world_id: str | None = None
    lease: dict[str, Any] | None = None
    async with Client(args.runtime, "python.agent-board.synthetic", args.ws_url) as client:
        created = await client.call(
            "world.create",
            {
                "window": {
                    "title": args.title,
                    "width": 520,
                    "height": 460,
                    "geometry_control": "human",
                },
                "join_policy": "invite",
            },
        )
        world_id = created["world"]["id"]
        lease = created["lease"]
        try:
            projection = aggregate_activities(load_synthetic_activities())
            scene = build_scene(projection)
            await client.mutate("scene.replace", world_id, lease, scene=scene)
            print(
                "Agent Board is displaying repository-owned synthetic activity only; "
                "it has no approval, file-write, or continue-execution actions.",
                flush=True,
            )
            await asyncio.sleep(args.duration_seconds)
        finally:
            if world_id is not None and lease is not None:
                await _destroy_owned_world(client, world_id, lease)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=30,
        help="How long to keep the synthetic test window open (1..300)",
    )
    parser.add_argument(
        "--title",
        default="Agent Board · 合成只读示例",
        help="Window title for distinguishing this synthetic test world",
    )
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 1 <= args.duration_seconds <= 300:
        parser.error("--duration-seconds must be between 1 and 300")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
