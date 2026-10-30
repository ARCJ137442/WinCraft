"""Synthetic provider demo for owner-routed interactions in a component scope."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Mapping

EXAMPLES = Path(__file__).resolve().parent
if str(EXAMPLES) not in sys.path:
    sys.path.insert(0, str(EXAMPLES))

from client import (  # noqa: E402
    COMPONENT_LEASES_PREVIEW_PROTOCOL,
    Client,
    RpcError,
    add_runtime_args,
    destroy_world_safely,
    event_world_id,
    require_runtime,
)

ACTION_SCOPE_ROOT = "counter-panel"
ACTION_SCOPE_NAMESPACE = "counter"
ACTION_COMPONENT_ID = "counter-increment"
ACTION_ID = "counter.increment"


def scene() -> dict[str, Any]:
    """The action lives inside an owned scope; the second scope stays display-only."""
    return {
        "root": {
            "id": "scope-action-root",
            "kind": "stack",
            "props": {"gap": 10},
            "children": [
                {
                    "id": ACTION_SCOPE_ROOT,
                    "kind": "stack",
                    "props": {"gap": 8},
                    "children": [
                        {
                            "id": "counter-title",
                            "kind": "text",
                            "props": {"text": "Scope-owned action", "size": "heading"},
                            "children": [],
                        },
                        {
                            "id": "counter-value",
                            "kind": "metric",
                            "props": {"label": "Accepted clicks", "value": {"$path": "/counter/count"}},
                            "children": [],
                        },
                        {
                            "id": ACTION_COMPONENT_ID,
                            "kind": "button",
                            "props": {"label": "Increment", "action": ACTION_ID},
                            "children": [],
                        },
                    ],
                },
                {
                    "id": "notes-panel",
                    "kind": "stack",
                    "props": {"gap": 8},
                    "children": [
                        {
                            "id": "notes-label",
                            "kind": "text",
                            "props": {"text": "A separate scope keeps its own owner."},
                            "children": [],
                        }
                    ],
                },
            ],
        },
        "data": {"counter": {"count": 0}, "notes": {}},
        "theme": {
            "background": "#1A1820",
            "foreground": "#F4EFFA",
            "accent": "#C4B5FD",
            "font_scale": 1.0,
            "radius_px": 12,
            "spacing_px": 10,
        },
    }


def owns_scope_interaction(
    message: Mapping[str, Any], world_id: str, scope_id: str, generation: int
) -> bool:
    if message.get("event") != "scope.interaction":
        return False
    data = message.get("data")
    return (
        isinstance(data, Mapping)
        and event_world_id(message) == world_id
        and data.get("scope_id") == scope_id
        and data.get("scope_generation") == generation
    )


async def handle_interaction(
    client: Client,
    *,
    world_id: str,
    scope: Mapping[str, Any],
    lease: Mapping[str, Any],
    message: Mapping[str, Any],
) -> int:
    """Apply one provider-owned demo action and acknowledge through the same scope lease."""
    data = message.get("data")
    if not isinstance(data, Mapping) or not owns_scope_interaction(
        message, world_id, str(scope["scope_id"]), int(scope["generation"])
    ):
        raise ValueError("interaction is not owned by this scope")
    ok = data.get("component_id") == ACTION_COMPONENT_ID and data.get("action") == ACTION_ID
    message_text = "Unsupported scoped action"
    count: int | None = None
    if ok:
        key = (world_id, str(scope["scope_id"]))
        snapshot = client.scope_snapshots.get(key)
        if snapshot is None or snapshot.get("generation") != scope["generation"]:
            snapshot = await client.read_scope(
                world_id, str(scope["scope_id"]), int(scope["generation"])
            )
        data_state = snapshot.get("data")
        current = data_state.get("count", 0) if isinstance(data_state, Mapping) else 0
        if isinstance(current, bool) or not isinstance(current, int) or current < 0:
            ok = False
            message_text = "Counter state is invalid"
        else:
            try:
                updated = await client.replace_scope_data(
                    world_id,
                    dict(lease),
                    int(snapshot["revision"]),
                    {"count": current + 1},
                )
            except RpcError as error:
                ok = False
                message_text = error.code
            else:
                count = int(updated["data"]["count"])
                message_text = f"Accepted click {count}"
    await client.scope_action_result(
        world_id,
        lease,
        str(data.get("id", "")),
        ok=ok,
        message=message_text,
    )
    return count if count is not None else -1


async def run(args: argparse.Namespace) -> None:
    world_id: str | None = None
    authority_lease: dict[str, Any] | None = None
    world_deleted = False
    async with Client(
        args.runtime,
        "python.scope-interaction-demo",
        args.ws_url,
        protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
    ) as client:
        client.require_capabilities(
            components=("stack", "text", "metric", "button"),
            scene_features=("theme_tokens",),
            window_properties=("text_selectable", "surface_opacity"),
            component_leases_version=1,
        )
        client.require_scope_interactions()
        created = await client.call(
            "world.create",
            {
                "window": {
                    "title": args.title,
                    "width": 420,
                    "height": 300,
                    "always_on_top": True,
                    "geometry_control": "human",
                    "resizable": True,
                    "text_selectable": False,
                    "surface_opacity": 0.8,
                },
                "join_policy": "invite",
                "claim": True,
            },
        )
        world_id = created["world"]["id"]
        world_lease = created.get("lease")
        if not isinstance(world_lease, dict):
            raise RuntimeError("Host did not issue the initial world lease")
        authority_lease = world_lease
        try:
            replaced = await client.mutate(
                "scene.replace",
                world_id,
                world_lease,
                expected_revision=created["world"]["revision"],
                scene=scene(),
            )
            partitioned = await client.partition_scopes(
                world_id,
                world_lease,
                replaced["revision"],
                [
                    {"root_node_id": ACTION_SCOPE_ROOT, "data_namespace": ACTION_SCOPE_NAMESPACE},
                    {"root_node_id": "notes-panel", "data_namespace": "notes"},
                ],
            )
            authority_lease = partitioned["authority_lease"]
            action_scope = next(
                item for item in partitioned["scopes"]
                if item["root_node_id"] == ACTION_SCOPE_ROOT
            )
            joined = await client.join_scope(world_id, action_scope, "write")
            scope_lease = joined.get("lease")
            if not isinstance(scope_lease, dict):
                raise RuntimeError("Host did not issue the action scope lease")
            print(
                "Scope interaction demo ready; click Increment to test owner routing. "
                "All counter data is synthetic.",
                flush=True,
            )
            deadline = asyncio.get_running_loop().time() + args.duration_seconds
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    event = await asyncio.wait_for(client.events.get(), timeout=remaining)
                except TimeoutError:
                    break
                if event.get("event") == "world.deleted" and event_world_id(event) == world_id:
                    world_deleted = True
                    return
                if event.get("event") in {"connection.error", "connection.closed", "provider.error"}:
                    raise ConnectionError("WinCraft host connection ended")
                if not owns_scope_interaction(
                    event, world_id, str(action_scope["scope_id"]), int(action_scope["generation"])
                ):
                    continue
                count = await handle_interaction(
                    client,
                    world_id=world_id,
                    scope=action_scope,
                    lease=scope_lease,
                    message=event,
                )
                print(f"Scoped action acknowledged; synthetic count={count}.", flush=True)
        finally:
            if world_id is not None and authority_lease is not None and not world_deleted:
                await destroy_world_safely(
                    client,
                    world_id,
                    authority_lease,
                    provider_name="Scope interaction demo",
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument("--title", default="Scope Action Demo · WinCraft")
    parser.add_argument("--duration-seconds", type=float, default=120)
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
