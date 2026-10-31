"""Synthetic provider used to verify the World Manager .wcp code-package flow."""
from __future__ import annotations

import argparse
import asyncio
from typing import Any

from client import Client, add_runtime_args, destroy_world_safely, event_world_id, require_runtime


def scene(count: int) -> dict[str, Any]:
    return {
        "root": {
            "id": "sample-root",
            "kind": "stack",
            "props": {"gap": 10},
            "children": [
                {"id": "sample-title", "kind": "text", "props": {"text": "WinCraft Provider Package Demo", "size": "title"}, "children": []},
                {"id": "sample-explainer", "kind": "text", "props": {"text": "This is synthetic data from a user-confirmed .wcp package."}, "children": []},
                {"id": "sample-count", "kind": "metric", "props": {"label": "Button clicks", "value": count}, "children": []},
                {"id": "sample-add", "kind": "button", "props": {"label": "Add one", "action": "sample.add", "tone": "accent"}, "children": []},
            ],
        },
        "data": {},
        "theme": {
            "background": "#17212B",
            "foreground": "#EAF2F8",
            "accent": "#80CBC4",
            "font_scale": 1.0,
            "radius_px": 12,
            "spacing_px": 10,
        },
    }


async def run(args: argparse.Namespace) -> None:
    world_id: str | None = None
    lease: dict[str, Any] | None = None
    deleted = False
    async with Client(args.runtime, "wincraft.package.sample") as client:
        client.require_capabilities(
            components=("stack", "text", "metric", "button"),
            scene_features=("theme_tokens",),
            window_properties=("text_selectable",),
        )
        created = await client.call("world.create", {
            "window": {
                "title": "WinCraft Provider Package Demo",
                "width": 420,
                "height": 280,
                "always_on_top": True,
                "text_selectable": False,
                "surface_opacity": 0.9,
            },
            "join_policy": "invite",
            "claim": True,
        })
        world_id = created["world"]["id"]
        lease = created.get("lease")
        if not isinstance(lease, dict):
            raise RuntimeError("Host did not issue a writer lease.")
        count = 0
        try:
            await client.mutate("scene.replace", world_id, lease, scene=scene(count))
            print("Synthetic Provider package connected; close the world to stop.", flush=True)
            while True:
                message = await client.events.get()
                if message.get("event") == "world.deleted" and event_world_id(message) == world_id:
                    deleted = True
                    return
                if message.get("event") in {"connection.error", "connection.closed", "provider.error"}:
                    raise ConnectionError("WinCraft Host connection ended.")
                if message.get("event") != "interaction":
                    continue
                event = message.get("data")
                if not isinstance(event, dict) or event.get("world_id") != world_id:
                    continue
                ok, error = True, None
                try:
                    if event.get("action") != "sample.add":
                        raise ValueError("Unsupported sample action.")
                    count += 1
                    await client.mutate("scene.replace", world_id, lease, scene=scene(count))
                except Exception as exc:
                    ok, error = False, str(exc)
                await client.call("action.result", {
                    "world_id": world_id,
                    "lease": lease,
                    "event_id": event.get("id"),
                    "ok": ok,
                    "message": error,
                })
        finally:
            if world_id is not None and lease is not None and not deleted:
                await destroy_world_safely(client, world_id, lease, provider_name="Provider package sample")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    args = parser.parse_args()
    require_runtime(parser, args)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
