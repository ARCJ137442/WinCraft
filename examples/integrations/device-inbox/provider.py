"""Open a short-lived device inbox from synthetic messages only."""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

PYTHON_EXAMPLES = Path(__file__).resolve().parents[2] / "python"
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import Client, add_runtime_args, destroy_world_safely, require_runtime  # noqa: E402
from device_inbox import DeviceInbox, build_scene, load_synthetic_messages, synthetic_receipt  # noqa: E402


async def run(args: argparse.Namespace) -> None:
    now = datetime.now(timezone.utc)
    inbox = DeviceInbox()
    for message in load_synthetic_messages():
        inbox.ingest(message, synthetic_receipt(message, now), now=now)
    scene = build_scene(inbox.active_messages(now=now))

    world_id: str | None = None
    lease: dict | None = None
    async with Client(args.runtime, "python.device-inbox.synthetic", args.ws_url) as client:
        created = await client.call(
            "world.create",
            {
                "window": {
                    "title": args.title,
                    "width": 480,
                    "height": 360,
                    "geometry_control": "human",
                },
                "join_policy": "invite",
            },
        )
        world_id, lease = created["world"]["id"], created["lease"]
        try:
            await client.mutate("scene.replace", world_id, lease, scene=scene)
            print(
                "Device Inbox is showing synthetic redacted summaries only; no transport or raw body is read.",
                flush=True,
            )
            await asyncio.sleep(args.duration_seconds)
        finally:
            if world_id is not None and lease is not None:
                await destroy_world_safely(
                    client,
                    world_id,
                    lease,
                    provider_name="Device Inbox",
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument("--duration-seconds", type=float, default=30)
    parser.add_argument("--title", default="Device Inbox · 合成只读示例")
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
