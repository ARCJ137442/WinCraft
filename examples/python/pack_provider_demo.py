"""Receive a user-confirmed configuration-pack world and render synthetic data."""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PYTHON_EXAMPLES = Path(__file__).resolve().parent
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import (  # noqa: E402
    COMPONENT_LEASES_PREVIEW_PROTOCOL,
    Client,
    add_runtime_args,
    require_runtime,
)


def inventory_registration(instance_id: str, generation: int) -> dict[str, Any]:
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "kind": "wincraft.inventory.registration",
        "schema_version": "draft-2026-10-29",
        "generation": generation,
        "observed_at": observed_at,
        "valid_for_seconds": 60,
        "providers": [
            {
                "source_id": "example.agent-board",
                "source_instance_id": instance_id,
                "provider_type": "agent-board",
                "display_name": "Synthetic pack provider",
                "adapter_contract": 1,
                "state": "online",
                "capabilities": ["activity.read", "world.import.accept"],
                "source_updated_at": observed_at,
                "fresh_for_seconds": 45,
            }
        ],
    }


def initial_scene() -> dict[str, Any]:
    return {
        "root": {
            "id": "root",
            "kind": "stack",
            "props": {"gap": 12},
            "children": [
                {"id": "title", "kind": "text", "props": {"text": "Pack import demo", "size": "title"}},
                {"id": "workload", "kind": "metric", "props": {
                    "label": "Synthetic queue", "value": 3, "unit": "items",
                    "caption": "Generated locally; no external source is read",
                }},
                {"id": "status", "kind": "badge", "props": {"text": "Provider connected", "tone": "success"}},
            ],
        },
        "data": {},
    }


async def handle_import_event(client: Any, message: dict[str, Any], duration_seconds: float) -> str:
    """Accept one Host-directed invitation and update only its newly imported world."""
    data = client.validate_provider_import_event(message)
    if "activity.read" not in data["approved_permissions"]:
        raise RuntimeError("The local user did not approve the demo's activity.read permission")
    world = data["world"]
    world_id = world["id"]
    lease = dict(data["lease"])
    try:
        await client.mutate("scene.replace", world_id, lease, scene=initial_scene())
        await asyncio.sleep(duration_seconds / 2)
        # A declared in-place structural replacement demonstrates that an imported
        # window remains a normal WinCraft world while its provider is connected.
        await client.mutate(
            "scene.patch",
            world_id,
            lease,
            ops=[
                {
                    "op": "replace",
                    "node_id": "status",
                    "node": {
                        "id": "status",
                        "kind": "progress",
                        "props": {"label": "Synthetic work", "value": 2, "max": 4},
                        "children": [],
                    },
                }
            ],
        )
        await asyncio.sleep(duration_seconds / 2)
        return world_id
    finally:
        # Leave the imported world for its local user; the provider never destroys it.
        try:
            await client.call("world.leave", {"world_id": world_id})
        except Exception as error:
            raise RuntimeError(
                "world.leave outcome is unknown; inspect the manager and do not replay the import automatically"
            ) from error


async def run(args: argparse.Namespace) -> None:
    instance_id = str(uuid.uuid4())
    generation = 0
    async with Client(
        args.runtime,
        "python.pack-provider-demo",
        args.ws_url,
        protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
    ) as client:
        client.require_provider_import(version=1)
        while True:
            generation += 1
            await client.register_provider_inventory(inventory_registration(instance_id, generation))
            try:
                message = await asyncio.wait_for(client.events.get(), timeout=15)
            except asyncio.TimeoutError:
                continue
            if message.get("event") == "connection.error":
                raise ConnectionError("provider connection ended before a pack was imported")
            if message.get("event") == "world.import.joined":
                world_id = await handle_import_event(client, message, args.duration_seconds)
                print(f"User-confirmed pack world finished its synthetic demo: {world_id}", flush=True)
                return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=30,
        help="How long to show the synthetic imported world (2..120)",
    )
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 2 <= args.duration_seconds <= 120:
        parser.error("--duration-seconds must be between 2 and 120")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
