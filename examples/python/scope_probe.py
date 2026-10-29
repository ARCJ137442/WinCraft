"""Exercise the experimental component-scope API against a real Rust host.

All names and values are synthetic. The script creates and destroys only its own
temporary world. Use an explicit preview protocol selection; it never falls back
to the stable whole-world protocol.
"""
from __future__ import annotations

import argparse
import asyncio
import socket
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


async def wait_for_scope_revision(
    client: Client,
    world_id: str,
    scope_id: str,
    minimum_revision: int,
) -> dict[str, Any]:
    for _ in range(100):
        snapshot = client.scope_snapshots.get((world_id, scope_id))
        if snapshot and snapshot.get("revision", -1) >= minimum_revision:
            return snapshot
        await asyncio.sleep(0.05)
    raise AssertionError("reader did not receive the filtered scope.snapshot update")


async def run(runtime: str) -> None:
    async with Client(
        runtime,
        "scope-probe-owner",
        protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
    ) as owner:
        owner.require_component_leases()
        owner.require_state_slots()
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
                reader_join = await reader.join_scope(world_id, grants["focus-panel"], "read")
                reader_scope_id = str(grants["focus-panel"]["scope_id"])
                slot = await focus.create_state_slot(
                    world_id,
                    focus_join["lease"],
                    "focus.progress",
                    {"type": "integer", "min": 0, "max": 100},
                    1,
                    [grants["tasks-panel"]],
                )
                tasks_scope_id = str(grants["tasks-panel"]["scope_id"])
                try:
                    await reader.read_state_slot(
                        world_id,
                        slot["slot_id"],
                        slot["generation"],
                        tasks_scope_id,
                        grants["tasks-panel"]["generation"],
                    )
                except RpcError as error:
                    if error.code != "FORBIDDEN":
                        raise
                else:
                    raise AssertionError("joining another scope must be required before reading")
                await reader.join_scope(world_id, grants["tasks-panel"], "read")

                async def compare_and_set(value: int) -> dict[str, Any] | RpcError:
                    try:
                        return await focus.compare_and_set_state_slot(
                            world_id,
                            focus_join["lease"],
                            slot["slot_id"],
                            slot["generation"],
                            slot["revision"],
                            value,
                        )
                    except RpcError as error:
                        return error

                outcomes = await asyncio.gather(
                    compare_and_set(2),
                    compare_and_set(3),
                )
                commits = [result for result in outcomes if isinstance(result, dict)]
                conflicts = [
                    result for result in outcomes
                    if isinstance(result, RpcError) and result.code == "STATE_REVISION_CONFLICT"
                ]
                if len(commits) != 1 or len(conflicts) != 1:
                    raise AssertionError("competing CAS writes must produce one commit and one revision conflict")
                committed_slot = commits[0]
                if committed_slot["revision"] != slot["revision"] + 1:
                    raise AssertionError("state slot revision did not advance after compare-and-set")
                observed_slot = await reader.read_state_slot(
                    world_id,
                    slot["slot_id"],
                    slot["generation"],
                    tasks_scope_id,
                    grants["tasks-panel"]["generation"],
                )
                if observed_slot["value"] != committed_slot["value"]:
                    raise AssertionError("authorized reader did not observe the winning CAS value")

                try:
                    await tasks.compare_and_set_state_slot(
                        world_id,
                        tasks_join["lease"],
                        slot["slot_id"],
                        slot["generation"],
                        committed_slot["revision"],
                        4,
                    )
                except RpcError as error:
                    if error.code != "STATE_SLOT_FORBIDDEN":
                        raise
                else:
                    raise AssertionError("a reader scope writer must not write a foreign slot")

                try:
                    await focus.compare_and_set_state_slot(
                        world_id,
                        focus_join["lease"],
                        slot["slot_id"],
                        slot["generation"],
                        committed_slot["revision"],
                        "wrong type",
                    )
                except RpcError as error:
                    if error.code != "INVALID_STATE_SLOT_VALUE":
                        raise
                else:
                    raise AssertionError("typed slot accepted a value outside its integer schema")

                slot_after_rejection = await focus.read_state_slot(
                    world_id,
                    slot["slot_id"],
                    slot["generation"],
                    reader_scope_id,
                    grants["focus-panel"]["generation"],
                )
                if slot_after_rejection["value"] != committed_slot["value"]:
                    raise AssertionError("rejected wrong-type value changed the state slot")
                temporary_slot = await tasks.create_state_slot(
                    world_id,
                    tasks_join["lease"],
                    "tasks.probe_cleanup",
                    {"type": "boolean"},
                    True,
                )
                await tasks.delete_state_slot(
                    world_id,
                    tasks_join["lease"],
                    temporary_slot["slot_id"],
                    temporary_slot["generation"],
                    temporary_slot["revision"],
                )
                revoked_slot = await focus.set_state_slot_readers(
                    world_id,
                    focus_join["lease"],
                    slot["slot_id"],
                    slot["generation"],
                    committed_slot["revision"],
                    [],
                )
                try:
                    await reader.read_state_slot(
                        world_id,
                        slot["slot_id"],
                        slot["generation"],
                        tasks_scope_id,
                        grants["tasks-panel"]["generation"],
                    )
                except RpcError as error:
                    if error.code != "STATE_SLOT_FORBIDDEN":
                        raise
                else:
                    raise AssertionError("revoked reader grant still allowed a slot read")

                async with Client(
                    runtime,
                    "scope-probe-slow-reader",
                    protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
                ) as slow_reader:
                    await slow_reader.join_scope(world_id, grants["focus-panel"], "read")
                    if slow_reader.reader is None:
                        raise AssertionError("slow-reader fixture did not start its network reader")
                    slow_socket = slow_reader.socket.transport.get_extra_info("socket")
                    if slow_socket is not None:
                        slow_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
                    slow_reader.reader.cancel()
                    await asyncio.gather(slow_reader.reader, return_exceptions=True)
                    slow_reader.reader = None

                    current_scope_revision = focus_join["snapshot"]["revision"]
                    starting_scope_revision = current_scope_revision
                    # Let setup calls clear the host's per-session request-rate window.
                    await asyncio.sleep(1.1)
                    for update_index in range(64):
                        try:
                            update = await asyncio.wait_for(
                                focus.patch_scope(
                                    world_id,
                                    focus_join["lease"],
                                    current_scope_revision,
                                    [{
                                        "op": "props",
                                        "node_id": "focus-value",
                                        "props": {"text": f"slow consumer update {update_index}"},
                                    }],
                                ),
                                timeout=5,
                            )
                        except Exception as error:
                            raise RuntimeError(
                                f"writer stopped at slow-consumer update {update_index}; "
                                f"reader_task_done={focus.reader.done() if focus.reader else True}"
                            ) from error
                        current_scope_revision = update["revision"]
                        await asyncio.sleep(0.05)
                    if current_scope_revision < starting_scope_revision + 64:
                        raise AssertionError("writer did not finish updates while a reader stopped consuming")

                    after_slow_reader = await asyncio.wait_for(
                        focus.compare_and_set_state_slot(
                            world_id,
                            focus_join["lease"],
                            slot["slot_id"],
                            slot["generation"],
                            revoked_slot["revision"],
                            33,
                        ),
                        timeout=5,
                    )
                    if after_slow_reader["value"] != 33:
                        raise AssertionError("idle reader blocked or corrupted the owner CAS write")

                focus_result = await focus.patch_scope(
                    world_id,
                    focus_join["lease"],
                    current_scope_revision,
                    [{"op": "props", "node_id": "focus-value", "props": {"text": "focus updated"}}],
                )
                focus_structure = await focus.patch_scope(
                    world_id,
                    focus_join["lease"],
                    focus_result["revision"],
                    [
                        {
                            "op": "insert",
                            "parent": "focus-panel",
                            "index": 1,
                            "node": {
                                "id": "focus-extra",
                                "kind": "text",
                                "props": {"text": {"$path": "/value"}},
                                "children": [],
                            },
                        },
                        {"op": "move", "node_id": "focus-extra", "parent": "focus-panel", "index": 0},
                    ],
                )
                if focus_structure["root"]["children"][0]["id"] != "focus-extra":
                    raise AssertionError("scope-local insert/move did not update its subtree")
                tasks_result = await tasks.patch_scope(
                    world_id,
                    tasks_join["lease"],
                    tasks_join["snapshot"]["revision"],
                    [{"op": "props", "node_id": "tasks-value", "props": {"text": "tasks updated"}}],
                )
                focus_data = await focus.replace_scope_data(
                    world_id,
                    focus_join["lease"],
                    focus_structure["revision"],
                    {"value": "synthetic focus updated"},
                )
                tasks_data = await tasks.replace_scope_data(
                    world_id,
                    tasks_join["lease"],
                    tasks_result["revision"],
                    {"value": "synthetic tasks updated"},
                )
                projection = reader_join["snapshot"]
                serialized = str(projection)
                if projection["root"]["id"] != "focus-panel":
                    raise AssertionError("reader projection does not start at its owned subtree")
                if projection["data"] != {"value": "synthetic focus"}:
                    raise AssertionError("reader projection did not keep its scoped data namespace")
                if "tasks-panel" in serialized or "synthetic tasks" in serialized:
                    raise AssertionError("reader projection leaked a sibling scope")
                if focus_data["revision"] != focus_join["snapshot"]["revision"] + 64 + 3:
                    raise AssertionError("focus scope revision did not advance independently")
                if tasks_data["revision"] != tasks_join["snapshot"]["revision"] + 2:
                    raise AssertionError("tasks scope revision did not advance independently")
                live_projection = await wait_for_scope_revision(
                    reader,
                    world_id,
                    reader_scope_id,
                    focus_data["revision"],
                )
                serialized_live = str(live_projection)
                if "focus-extra" not in serialized_live or "tasks-panel" in serialized_live:
                    raise AssertionError("live scope.snapshot was not filtered to the reader's scope")

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
                    try:
                        await legacy.read_state_slot(
                            world_id,
                            slot["slot_id"],
                            slot["generation"],
                            reader_scope_id,
                            grants["focus-panel"]["generation"],
                        )
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError("stable 0.3 provider reached preview-only state slots")

                authority_snapshot = await owner.call("world.snapshot", {"world_id": world_id})
                await owner.patch_structure(
                    world_id,
                    cleanup_lease,
                    authority_snapshot["revision"],
                    [{"op": "remove", "node_id": "tasks-panel"}],
                )
                while True:
                    revoked = await asyncio.wait_for(tasks.events.get(), 5)
                    if revoked.get("event") == "scope.revoked":
                        if revoked.get("data", {}).get("scope_id") != grants["tasks-panel"]["scope_id"]:
                            continue
                        break
                try:
                    await tasks.patch_scope(
                        world_id,
                        tasks_join["lease"],
                        tasks_data["revision"],
                        [{"op": "props", "node_id": "tasks-value", "props": {"text": "must be rejected"}}],
                    )
                except RpcError as error:
                    if error.code != "STALE_SCOPE":
                        raise
                else:
                    raise AssertionError("parent structure removal did not revoke the child scope")

                print(
                    "PASS: real Rust WebSocket scope preview; "
                    f"focus_revision={focus_data['revision']}, tasks_revision={tasks_data['revision']}, "
                    "scope-local structure, filtered live snapshots, typed slot grants/CAS/revocation, "
                    "parent revocation, and stable 0.3 refusal"
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
