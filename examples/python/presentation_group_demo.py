'''Present two synthetic worlds as one presentation group.

The demo creates two small worlds, registers them as one ordered group, and
applies one operation to the group. It shows the per-member outcome: one
member accepts the operation while the other refuses it, because the demo
deliberately supplies a wrong lease for the second member.

Everything on screen is synthetic. The demo reads no external business data,
touches no user source file, and destroys only the worlds it created.
'''
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .client import (
        COMPONENT_LEASES_PREVIEW_PROTOCOL,
        Client,
        add_runtime_args,
        require_runtime,
    )
else:
    from client import (
        COMPONENT_LEASES_PREVIEW_PROTOCOL,
        Client,
        add_runtime_args,
        require_runtime,
    )


def panel_scene(title: str, subtitle: str) -> dict[str, Any]:
    '''Build one small synthetic panel scene.'''
    return {
        "root": {
            "id": "root",
            "kind": "stack",
            "props": {"gap": 8},
            "children": [
                {
                    "id": "heading",
                    "kind": "text",
                    "props": {"text": title, "size": "title"},
                    "children": [],
                },
                {
                    "id": "caption",
                    "kind": "text",
                    "props": {"text": subtitle, "size": "body"},
                    "children": [],
                },
            ],
        }
    }


async def _current_revision(client: Client, world_id: str) -> int:
    '''Read the current revision of a world this provider owns.'''
    snapshot = await client.call("world.snapshot", {"world_id": world_id})
    return int(snapshot["revision"])


async def run_demo(runtime: str, duration_seconds: int) -> dict[str, Any]:
    '''Create two worlds, group them, apply once, then clean up.'''
    summary: dict[str, Any] = {
        "synthetic_only": True,
        "group_created": False,
        "applied": 0,
        "refused": 0,
        "changed": [],
        "worlds_destroyed": False,
    }
    created: list[dict[str, Any]] = []
    async with Client(
        runtime,
        "python.demo.presentation-group",
        protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
    ) as client:
        # Fail closed before touching the Host when the capability is absent.
        client.require_presentation_groups()

        for title, subtitle in (
            ("面板 A", "合成数据 · 第一块"),
            ("面板 B", "合成数据 · 第二块"),
        ):
            result = await client.call(
                "world.create",
                {
                    "window": {
                        "title": f"WinCraft 窗口组 · {title}",
                        "width": 280.0,
                        "height": 180.0,
                        "always_on_top": True,
                        "skip_taskbar": True,
                        "text_selectable": False,
                    },
                    "claim": True,
                },
            )
            created.append(result)
            await client.call(
                "scene.replace",
                {
                    "world_id": result["world"]["id"],
                    "lease": result["lease"],
                    "expected_revision": result["world"]["revision"],
                    "scene": panel_scene(title, subtitle),
                },
            )

        first, second = created
        first_id = first["world"]["id"]
        second_id = second["world"]["id"]
        # The scene replacement advanced each world's revision, so the group
        # operation must carry the current revision, not the creation one.
        first_revision = await _current_revision(client, first_id)
        second_revision = await _current_revision(client, second_id)

        group = await client.create_presentation_group(
            "demo-workbench",
            members=[
                {"world_id": first_id, "order": 0},
                {"world_id": second_id, "order": 1},
            ],
            roles=[
                {"name": "primary", "member": None},
                {"name": "secondary", "member": second_id},
            ],
        )
        summary["group_created"] = True
        summary["group_id"] = group["id"]
        summary["roles"] = group["roles"]

        # The second member receives a deliberately wrong lease, so the demo
        # shows that a group operation is never atomic and never hides a
        # refusal behind a group-wide success.
        second_lease = second["lease"]
        outcome = await client.apply_presentation_group(
            group["id"],
            leases={
                first_id: first["lease"],
                second_id: {"id": second_lease["id"], "epoch": second_lease["epoch"] + 99},
            },
            expected_revisions={
                first_id: first_revision,
                second_id: second_revision,
            },
            visible=False,
        )
        summary["atomic"] = outcome["atomic"]
        summary["applied"] = outcome["result"]["applied"]
        summary["refused"] = outcome["result"]["refused"]
        summary["changed"] = outcome["changed"]
        summary["results"] = [
            {
                "world_id": entry["world_id"],
                "status": entry["outcome"]["status"],
                "code": entry["outcome"].get("code"),
            }
            for entry in outcome["result"]["results"]
        ]

        # Restore visibility for the accepted member, so the demo ends with a
        # visible window instead of a hidden one.
        await client.apply_presentation_group(
            group["id"],
            leases={first_id: first["lease"]},
            expected_revisions={first_id: first_revision},
            visible=True,
        )

        for world in created:
            try:
                await client.call(
                    "world.destroy",
                    {"world_id": world["world"]["id"], "lease": world["lease"]},
                )
            except Exception:
                pass
        summary["worlds_destroyed"] = True

    if duration_seconds > 0:
        await asyncio.sleep(duration_seconds)
    return summary


def main() -> int:
    '''Run the presentation group demo and print a synthetic summary.'''
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=6,
        help="keep the worlds on screen for this many seconds before cleanup",
    )
    arguments = parser.parse_args()
    require_runtime(parser, arguments)
    runtime = arguments.runtime
    summary = asyncio.run(run_demo(runtime, arguments.duration_seconds))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
