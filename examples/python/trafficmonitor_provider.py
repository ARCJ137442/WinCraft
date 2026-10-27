"""Read-only WinCraft provider for a locally staged TrafficMonitor bridge.

The native TrafficMonitor plugin writes a tiny JSON snapshot to an explicitly chosen
local path. This process owns no system-monitoring truth and never sends these values
to an external service.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__:
    from .client import Client, add_runtime_args, require_runtime
else:
    from client import Client, add_runtime_args, require_runtime

BRIDGE_SCHEMA = "wincraft.trafficmonitor.v1"
MAX_METRICS_BYTES = 16_384
READINGS = ("download", "upload", "cpu", "memory", "gpu")


def read_metrics(path: Path) -> dict[str, Any] | None:
    """Return a validated snapshot; missing files are waiting, never numeric zero."""
    try:
        if path.stat().st_size > MAX_METRICS_BYTES:
            raise ValueError("bridge snapshot exceeds the size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict) or value.get("schema") != BRIDGE_SCHEMA:
        raise ValueError("unrecognized TrafficMonitor bridge snapshot")
    if type(value.get("sampled_at_ms")) is not int or not (0 < value["sampled_at_ms"] <= 253402300799999):
        raise ValueError("missing sample timestamp")
    if type(value.get("generation")) is not int or not (0 <= value["generation"] <= 9_007_199_254_740_991):
        raise ValueError("missing sample generation")
    if value.get("app_version") is not None and (
        not isinstance(value["app_version"], str) or len(value["app_version"]) > 64
    ):
        raise ValueError("invalid TrafficMonitor version")
    for name in READINGS:
        reading = value.get(name)
        if reading is not None and (not isinstance(reading, str) or len(reading) > 128):
            raise ValueError(f"invalid {name} reading")
    return value


def make_view_data(
    metrics: dict[str, Any] | None,
    *,
    source_error: str | None = None,
    now_ms: int | None = None,
    stale_after_seconds: float = 5.0,
) -> dict[str, Any]:
    """Build renderer data while preserving missing/stale distinctions."""
    now = int(time.time() * 1000) if now_ms is None else now_ms
    if metrics is None:
        return {
            "status": source_error or "等待 TrafficMonitor",
            "app_version": "—",
            "sample_time": "暂无采样",
            "age_seconds": None,
            "download": "—",
            "upload": "—",
            "cpu": "—",
            "memory": "—",
            "gpu": "—",
        }

    age = max(0, (now - metrics["sampled_at_ms"]) // 1000)
    stale = age > stale_after_seconds
    sampled = datetime.fromtimestamp(metrics["sampled_at_ms"] / 1000).strftime("%H:%M:%S")
    result: dict[str, Any] = {
        "status": source_error or ("数据已过期" if stale else ""),
        "app_version": metrics.get("app_version") or "未知版本",
        "sample_time": f"采样于 {sampled} · {age} 秒前",
        "age_seconds": age,
    }
    result.update({name: metrics.get(name) or "—" for name in READINGS})
    return result


def scene() -> dict[str, Any]:
    """A stable component tree; only its provider-owned data changes."""
    def metric(node_id: str, label: str, path: str) -> dict[str, Any]:
        return {
            "id": node_id,
            "kind": "metric",
            "props": {"label": label, "value": {"$path": path}},
            "children": [],
        }

    def text(node_id: str, value: str | dict[str, str], size: str | None = None) -> dict[str, Any]:
        props: dict[str, Any] = {"text": value}
        if size is not None:
            props["size"] = size
        return {"id": node_id, "kind": "text", "props": props, "children": []}

    return {
        "root": {
            "id": "traffic-root",
            "kind": "stack",
            "props": {"gap": 10},
            "children": [
                {
                    "id": "traffic-heading",
                    "kind": "row",
                    "props": {"gap": 10},
                    "children": [
                        text("traffic-title", "TrafficMonitor", "title"),
                        {
                            "id": "traffic-status",
                            "kind": "badge",
                            "props": {"text": {"$path": "/status"}, "tone": "accent"},
                            "children": [],
                        },
                    ],
                },
                {
                    "id": "traffic-network",
                    "kind": "row",
                    "props": {"gap": 12},
                    "children": [
                        metric("traffic-down", "下载", "/download"),
                        metric("traffic-up", "上传", "/upload"),
                    ],
                },
                {
                    "id": "traffic-hardware",
                    "kind": "row",
                    "props": {"gap": 12},
                    "children": [
                        metric("traffic-cpu", "CPU", "/cpu"),
                        metric("traffic-memory", "内存", "/memory"),
                        metric("traffic-gpu", "GPU", "/gpu"),
                    ],
                },
                text("traffic-version", {"$path": "/app_version"}),
                text("traffic-sample-time", {"$path": "/sample_time"}),
            ],
        },
        "data": {},
    }


async def run(args: argparse.Namespace) -> None:
    metrics_path = Path(args.metrics).expanduser().resolve()
    async with Client(args.runtime, "python.trafficmonitor", args.ws_url) as client:
        created = await client.call(
            "world.create",
            {
                "window": {"title": "TrafficMonitor · WinCraft", "width": 420, "height": 300},
                "join_policy": "invite",
            },
        )
        world_id = created["world"]["id"]
        lease = created["lease"]
        if lease is None:
            raise RuntimeError("Host did not grant the new world a write lease")
        await client.mutate("scene.replace", world_id, lease, scene=scene())
        print(f"TrafficMonitor provider world ready: {world_id}", flush=True)

        latest: dict[str, Any] | None = None
        last_signature: tuple[Any, ...] | None = None
        source_error: str | None = None
        try:
            while True:
                try:
                    current = await asyncio.to_thread(read_metrics, metrics_path)
                    if current is not None:
                        latest = current
                        source_error = None
                    else:
                        source_error = "桥接文件不存在" if latest is not None else None
                except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                    source_error = "桥接文件无效"

                view_data = make_view_data(
                    latest,
                    source_error=source_error,
                    stale_after_seconds=args.stale_after,
                )
                signature = tuple(view_data.get(key) for key in (
                    "status", "app_version", "sample_time", *READINGS
                ))
                if signature != last_signature:
                    result = await client.mutate("data.replace", world_id, lease, data=view_data)
                    last_signature = signature
                    if args.verbose:
                        generation = latest.get("generation") if latest is not None else None
                        print(
                            "TrafficMonitor sync: "
                            f"status={view_data['status']} age={view_data['age_seconds']} "
                            f"generation={generation} version={view_data['app_version']} "
                            f"revision={result['revision']}",
                            flush=True,
                        )

                try:
                    event = await asyncio.wait_for(client.events.get(), timeout=args.interval)
                except TimeoutError:
                    continue
                if event.get("event") == "world.deleted" and event.get("data", {}).get("world_id") == world_id:
                    return
                if event.get("event") in ("connection.error", "connection.closed"):
                    raise ConnectionError(event.get("error", "WinCraft connection closed"))
        finally:
            if client.socket is not None:
                try:
                    await client.call("world.destroy", {"world_id": world_id, "lease": lease})
                except Exception:
                    pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument(
        "--metrics",
        default=os.environ.get("WINCRAFT_TRAFFICMONITOR_METRICS"),
        help="Explicit path written by the companion local TrafficMonitor plugin",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="Local polling interval in seconds")
    parser.add_argument("--stale-after", type=float, default=5.0, help="Mark source stale after this many seconds")
    parser.add_argument("--verbose", action="store_true", help="Log sync status without metric values")
    args = parser.parse_args()
    require_runtime(parser, args)
    if not args.metrics:
        parser.error("--metrics PATH or WINCRAFT_TRAFFICMONITOR_METRICS is required")
    if args.interval < 0.2 or args.interval > 30:
        parser.error("--interval must be between 0.2 and 30 seconds")
    if args.stale_after < 1 or args.stale_after > 300:
        parser.error("--stale-after must be between 1 and 300 seconds")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
