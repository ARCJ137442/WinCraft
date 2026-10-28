"""Exercise the experimental component-scope API against a real Rust host.

All names and values are synthetic. The script creates and destroys only its own
temporary world. Use an explicit preview protocol selection; it never falls back
to the stable whole-world protocol.
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any

from client import (
    COMPONENT_LEASES_PREVIEW_PROTOCOL,
    Client,
    RpcError,
    add_runtime_args,
    require_runtime,
)


def scope_scene() -> dict[str, Any]:
    return {
        "root": {
            "id": "root",
            "kind": "stack",
            "children": [
                {
                    "id": "focus-panel",
                    "kind": "stack",
                    "children": [
                        {
                            "id": "focus-value",
                            "kind": "text",
                            "props": {"text": {"$path": "/focus/value"}},
                        }
                    ],
                },
                {
                    "id": "tasks-panel",
                    "kind": "stack",
                    "children": [
                        {
                            "id": "tasks-value",
                            "kind": "text",
                            "props": {"text": {"$path": "/tasks/value"}},
                        }
                    ],
                },
            ],
        },
        "data": {
            "focus": {"value": "synthetic focus"},
            "tasks": {"value": "synthetic tasks"},
        },
    }


async def run(runtime: str) -> None:
    async with Client(
        runtime,
        "scope-probe-owner",
        protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
    ) as owner:
        owner.require_component_leases()
        created = await owner.call(
            "world.create",
            {"window": {"title": "Synthetic scope probe"}, "claim": True},
        )
        world_id = created["world"]["id"]
        cleanup_lease = created["lease"]
        try:
            replaced = await owner.call(
                "scene.replace",
                {
                    "world_id": world_id,
                    "lease": created["lease"],
                    "expected_revision": created["world"]["revision"],
                    "scene": scope_scene(),
                },
            )
            partition = await owner.partition_scopes(
                world_id,
                created["lease"],
                replaced["revision"],
                [
                    {"root_node_id": "focus-panel", "data_namespace": "focus"},
                    {"root_node_id": "tasks-panel", "data_namespace": "tasks"},
                ],
            )
            cleanup_lease = partition["authority_lease"]
            grants = {scope["root_node_id"]: scope for scope in partition["scopes"]}

            async with (
                Client(runtime, "scope-probe-focus", protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL) as focus,
                Client(runtime, "scope-probe-tasks", protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL) as tasks,
                Client(runtime, "scope-probe-reader", protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL) as reader,
            ):
                focus_join = await focus.join_scope(world_id, grants["focus-panel"], "write")
                tasks_join = await tasks.join_scope(world_id, grants["tasks-panel"], "write")
                focus_result = await focus.patch_scope(
                    world_id,
                    focus_join["lease"],
                    focus_join["snapshot"]["revision"],
                    [{"op": "props", "node_id": "focus-value", "props": {"text": "focus updated"}}],
                )
                tasks_result = await tasks.patch_scope(
                    world_id,
                    tasks_join["lease"],
                    tasks_join["snapshot"]["revision"],
                    [{"op": "props", "node_id": "tasks-value", "props": {"text": "tasks updated"}}],
                )
                focus_data = await focus.replace_scope_data(
                    world_id,
                    focus_join["lease"],
                    focus_result["revision"],
                    {"value": "synthetic focus updated"},
                )
                tasks_data = await tasks.replace_scope_data(
                    world_id,
                    tasks_join["lease"],
                    tasks_result["revision"],
                    {"value": "synthetic tasks updated"},
                )
                reader_join = await reader.join_scope(world_id, grants["focus-panel"], "read")
                projection = reader_join["snapshot"]
                serialized = str(projection)
                if projection["root"]["id"] != "focus-panel":
                    raise AssertionError("reader projection does not start at its owned subtree")
                if projection["data"] != {"value": "synthetic focus updated"}:
                    raise AssertionError("reader projection did not keep its scoped data namespace")
                if "tasks-panel" in serialized or "synthetic tasks" in serialized:
                    raise AssertionError("reader projection leaked a sibling scope")
                if focus_data["revision"] != focus_join["snapshot"]["revision"] + 2:
                    raise AssertionError("focus scope revision did not advance independently")
                if tasks_data["revision"] != tasks_join["snapshot"]["revision"] + 2:
                    raise AssertionError("tasks scope revision did not advance independently")

                legacy = Client(runtime, "scope-probe-legacy")
                async with legacy:
                    capabilities = await legacy.call("host.capabilities", {})
                    if capabilities["component_leases"] is not False:
                        raise AssertionError("stable 0.3 connection advertised preview scopes")
                    try:
                        await legacy.call(
                            "world.join",
                            {"world_id": world_id, "join_key": created["join_key"], "mode": "write"},
                        )
                    except RpcError as error:
                        if error.code != "SCOPE_REQUIRED":
                            raise
                    else:
                        raise AssertionError("stable whole-world writer joined a scoped world")

                print(
                    "PASS: real Rust WebSocket scope preview; "
                    f"focus_revision={focus_data['revision']}, tasks_revision={tasks_data['revision']}, "
                    "sibling data filtered, stable 0.3 writer refused"
                )
        finally:
            try:
                await owner.call("world.destroy", {"world_id": world_id, "lease": cleanup_lease})
                remaining = await owner.call("world.list", {})
                if any(summary.get("id") == world_id for summary in remaining):
                    raise RuntimeError("temporary scoped world still appears in world.list")
            except Exception as error:
                # A timeout is unknown; inspect the local manager before any retry.
                raise RuntimeError(
                    f"Cleanup needs manager inspection for synthetic world {world_id}"
                ) from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    args = parser.parse_args()
    require_runtime(parser, args)
    asyncio.run(run(args.runtime))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
