"""Read two local sources into disjoint WinCraft preview scopes."""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

if __package__:
    from . import obsidian_workspace, trafficmonitor_provider
    from .client import COMPONENT_LEASES_PREVIEW_PROTOCOL, Client, add_runtime_args, require_runtime
else:
    import obsidian_workspace
    import trafficmonitor_provider
    from client import COMPONENT_LEASES_PREVIEW_PROTOCOL, Client, add_runtime_args, require_runtime


def prefix_scope_bindings(value: Any, namespace: str) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$path"}:
            path = value["$path"]
            if not isinstance(path, str) or not path.startswith("/"):
                raise ValueError("scope scene contains an invalid data binding")
            suffix = path.lstrip("/")
            return {"$path": f"/{namespace}/{suffix}" if suffix else f"/{namespace}"}
        return {key: prefix_scope_bindings(child, namespace) for key, child in value.items()}
    if isinstance(value, list):
        return [prefix_scope_bindings(child, namespace) for child in value]
    return value


def make_read_only_obsidian_root(node: dict[str, Any]) -> dict[str, Any] | None:
    if node.get("kind") == "button":
        if node.get("id") in {"obsidian-title", "obsidian-activate-selected"}:
            return {
                "id": node.get("id", "obsidian-title"),
                "kind": "text",
                "props": {"text": "Obsidian Workspace", "size": "title"},
                "children": [],
            }
        return None
    result = dict(node)
    if isinstance(result.get("children"), list):
        result["children"] = [
            child
            for item in result["children"]
            if isinstance(item, dict)
            if (child := make_read_only_obsidian_root(item)) is not None
        ]
    result.pop("native_window_action", None)
    result.get("props", {}).pop("native_window_action", None)
    return result


def composition_scene(traffic_data: dict[str, Any], obsidian_data: dict[str, Any]) -> dict[str, Any]:
    traffic_scene = trafficmonitor_provider.scene()
    obsidian_scene = obsidian_workspace.build_scene([obsidian_data])
    traffic_root = prefix_scope_bindings(traffic_scene["root"], "traffic")
    obsidian_root = make_read_only_obsidian_root(
        prefix_scope_bindings(obsidian_scene["root"], "obsidian")
    )
    if obsidian_root is None:
        raise ValueError("Obsidian workspace scene has no read-only content")
    traffic_root["id"] = "traffic-root"
    obsidian_root["id"] = "obsidian-root"
    return {
        "root": {
            "id": "composition-root",
            "kind": "stack",
            "props": {"gap": 12},
            "children": [traffic_root, obsidian_root],
        },
        "data": {"traffic": traffic_data, "obsidian": obsidian_data},
        "theme": obsidian_scene.get("theme"),
    }


async def capture_sources(metrics_path: Path, vault_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    now_ms = int(time.time() * 1000)
    metrics = await asyncio.to_thread(trafficmonitor_provider.read_metrics, metrics_path)
    if metrics is None:
        raise RuntimeError("TrafficMonitor bridge has no snapshot")
    traffic_data = trafficmonitor_provider.make_view_data(metrics, now_ms=now_ms)
    if traffic_data["status"]:
        raise RuntimeError("TrafficMonitor bridge snapshot is not fresh")
    obsidian_data = await asyncio.to_thread(
        obsidian_workspace.read_snapshot,
        obsidian_workspace.plugin_directory(vault_path),
    )
    return traffic_data, obsidian_data


async def wait_for_failure_marker(path: Path, timeout_seconds: float) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while not path.is_file():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("test runner did not stop the staged TrafficMonitor source")
        await asyncio.sleep(0.1)


async def run(args: argparse.Namespace) -> None:
    metrics_path = Path(args.traffic_metrics).expanduser().resolve()
    ready_file = Path(args.ready_file).expanduser().resolve()
    failure_file = Path(args.failure_file).expanduser().resolve()
    if ready_file.exists() or failure_file.exists():
        raise FileExistsError("composition-probe control marker already exists")
    traffic_data, obsidian_data = await capture_sources(metrics_path, args.vault)
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    world_id: str | None = None
    cleanup_lease: dict[str, Any] | None = None

    async with Client(
        args.runtime,
        "composition-probe-owner",
        protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
    ) as owner:
        owner.require_component_leases()
        owner.require_capabilities(
            components=("stack", "row", "text", "badge", "metric", "icon", "key_value", "bar_chart", "divider"),
            scene_features=("theme_tokens", "rich_key_value"),
        )
        created = await owner.call("world.create", {
            "window": {"title": "WinCraft multi-source fault-isolation probe", "width": 620, "height": 760, "text_selectable": False},
            "join_policy": "invite",
            "claim": True,
        })
        world_id = created["world"]["id"]
        cleanup_lease = created.get("lease")
        probe_passed = False
        try:
            if not isinstance(cleanup_lease, dict):
                raise RuntimeError("composition owner did not receive a world lease")
            replaced = await owner.call("scene.replace", {
                "world_id": world_id,
                "lease": cleanup_lease,
                "expected_revision": created["world"]["revision"],
                "scene": composition_scene(traffic_data, obsidian_data),
            })
            partition = await owner.partition_scopes(
                world_id,
                cleanup_lease,
                replaced["revision"],
                [
                    {"root_node_id": "traffic-root", "data_namespace": "traffic"},
                    {"root_node_id": "obsidian-root", "data_namespace": "obsidian"},
                ],
            )
            cleanup_lease = partition["authority_lease"]
            grants = {scope["root_node_id"]: scope for scope in partition["scopes"]}

            async with (
                Client(args.runtime, "composition-probe-trafficmonitor", protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL) as traffic,
                Client(args.runtime, "composition-probe-obsidian-workspace", protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL) as obsidian,
            ):
                traffic.require_component_leases()
                obsidian.require_component_leases()
                traffic_join = await traffic.join_scope(world_id, grants["traffic-root"], "write")
                obsidian_join = await obsidian.join_scope(world_id, grants["obsidian-root"], "write")
                traffic_initial = await traffic.replace_scope_data(
                    world_id, traffic_join["lease"], traffic_join["snapshot"]["revision"], traffic_data
                )
                obsidian_initial = await obsidian.replace_scope_data(
                    world_id, obsidian_join["lease"], obsidian_join["snapshot"]["revision"], obsidian_data
                )
                if traffic_initial["data"] != traffic_data or obsidian_initial["data"] != obsidian_data:
                    raise AssertionError("source projection did not remain in its owning scope")

                ready_file.write_text("ready\n", encoding="utf-8")
                print("READY_FOR_TRAFFICMONITOR_FAILURE", flush=True)
                await wait_for_failure_marker(failure_file, args.failure_timeout)
                await asyncio.sleep(2.1)
                latest_metrics = await asyncio.to_thread(trafficmonitor_provider.read_metrics, metrics_path)
                traffic_after_failure = trafficmonitor_provider.make_view_data(
                    latest_metrics,
                    source_error="TrafficMonitor bridge file unavailable" if latest_metrics is None else None,
                    now_ms=int(time.time() * 1000),
                    stale_after_seconds=1.0,
                )
                if not traffic_after_failure["status"]:
                    raise AssertionError("stopped TrafficMonitor did not become stale")
                traffic_updated = await traffic.replace_scope_data(
                    world_id, traffic_join["lease"], traffic_initial["revision"], traffic_after_failure
                )
                traffic_snapshot = await traffic.read_scope(
                    world_id, grants["traffic-root"]["scope_id"], grants["traffic-root"]["generation"]
                )
                obsidian_snapshot = await obsidian.read_scope(
                    world_id, grants["obsidian-root"]["scope_id"], grants["obsidian-root"]["generation"]
                )
                if traffic_snapshot["data"]["status"] != traffic_after_failure["status"]:
                    raise AssertionError("TrafficMonitor stale status did not update its own scope")
                if obsidian_snapshot["data"] != obsidian_initial["data"]:
                    raise AssertionError("TrafficMonitor failure changed the Obsidian scope")
                if traffic_updated["revision"] <= traffic_initial["revision"]:
                    raise AssertionError("TrafficMonitor scope revision did not advance")
                probe_passed = True
        finally:
            if cleanup_lease is not None:
                await owner.call("world.destroy", {"world_id": world_id, "lease": cleanup_lease})
                remaining = await owner.call("world.list", {})
                if any(summary.get("id") == world_id for summary in remaining):
                    raise RuntimeError("temporary composition world still appears in world.list")
        if probe_passed:
            print(
                "PASS: TrafficMonitor and Obsidian workspace metadata occupied separate scopes; "
                "stopping TrafficMonitor changed only its stale projection.",
                flush=True,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument("--traffic-metrics", required=True, help="Snapshot written by the staged local TrafficMonitor bridge")
    parser.add_argument("--vault", type=Path, required=True, help="Explicit Obsidian vault folder with the WinCraft Workspace Dashboard enabled")
    parser.add_argument("--ready-file", required=True, help="Temporary orchestration marker path")
    parser.add_argument("--failure-file", required=True, help="Temporary marker created after the staged source is stopped")
    parser.add_argument("--failure-timeout", type=float, default=90.0)
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 10 <= args.failure_timeout <= 300:
        parser.error("--failure-timeout must be between 10 and 300 seconds")
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
