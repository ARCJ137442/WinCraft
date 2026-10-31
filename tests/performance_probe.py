"""Synthetic-only request/lifecycle/reconnect probe; use a disposable local Host."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Sequence

PYTHON_EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "python"
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import Client, add_runtime_args, destroy_world_safely, require_runtime  # noqa: E402


def percentile(values: Sequence[float], quantile: float) -> float | None:
    if not math.isfinite(quantile) or not 0 <= quantile <= 1:
        raise ValueError("quantile must be finite and within 0..=1")
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 3)


def summarize(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "max_ms": None,
        }
    numbers = [float(value) for value in values]
    return {
        "count": len(numbers),
        "min_ms": round(min(numbers), 3),
        "p50_ms": percentile(numbers, 0.50),
        "p95_ms": percentile(numbers, 0.95),
        "p99_ms": percentile(numbers, 0.99),
        "max_ms": round(max(numbers), 3),
    }


async def create_synthetic_world(
    client: Client,
    sequence: int,
    *,
    visible: bool = False,
    title_prefix: str = "WinCraft B11-01 synthetic",
) -> tuple[str, dict[str, Any], str]:
    created = await client.call(
        "world.create",
        {
            "window": {
                "title": f"{title_prefix} {sequence}",
                "width": 320,
                "height": 200,
                "visible": visible,
                "always_on_top": False,
            },
            "join_policy": "open_authenticated",
            "claim": True,
        },
    )
    world = created.get("world")
    world_id = world.get("id") if isinstance(world, dict) else None
    lease = created.get("lease")
    join_key = created.get("join_key")
    if not isinstance(world_id, str) or not isinstance(lease, dict) or not isinstance(join_key, str):
        raise RuntimeError("Host did not return the synthetic world's identity and write lease")
    return world_id, lease, join_key


async def timed_call(
    client: Client,
    samples: list[float],
    method: str,
    params: dict[str, Any],
) -> Any:
    started = time.perf_counter()
    result = await client.call(method, params)
    samples.append((time.perf_counter() - started) * 1000)
    return result


async def quiet_destroy(client: Client, world_id: str, lease: dict[str, Any]) -> None:
    # The shared helper prints a human confirmation. Keep this probe's stdout as
    # exactly one machine-readable aggregate JSON document.
    with contextlib.redirect_stdout(io.StringIO()):
        await destroy_world_safely(
            client,
            world_id,
            lease,
            provider_name="WinCraft B11-01 synthetic perf probe",
        )


async def measure_world_lifecycle(
    client: Client,
    sequence: int,
    create_samples: list[float],
    destroy_samples: list[float],
    inter_call_interval_seconds: float,
) -> None:
    started = time.perf_counter()
    world_id, lease, _join_key = await create_synthetic_world(client, sequence)
    create_samples.append((time.perf_counter() - started) * 1000)
    await asyncio.sleep(inter_call_interval_seconds)
    # Send exactly one destroy request. If it times out, the outcome is unknown;
    # never replay it. The caller must stop the disposable Host before investigating.
    started = time.perf_counter()
    await client.call("world.destroy", {"world_id": world_id, "lease": lease})
    destroy_samples.append((time.perf_counter() - started) * 1000)
    await asyncio.sleep(inter_call_interval_seconds)


async def measure_data_round_trips(
    client: Client,
    world_id: str,
    lease: dict[str, Any],
    *,
    snapshot_iterations: int,
    data_iterations: int,
    payload_bytes: int,
    inter_call_interval_seconds: float,
) -> dict[str, list[float]]:
    snapshot_samples: list[float] = []
    data_replace_samples: list[float] = []
    for _ in range(snapshot_iterations):
        await timed_call(client, snapshot_samples, "world.snapshot", {"world_id": world_id})
        await asyncio.sleep(inter_call_interval_seconds)
    payload = "x" * payload_bytes
    snapshot = await client.call("world.snapshot", {"world_id": world_id})
    for counter in range(data_iterations):
        started = time.perf_counter()
        snapshot = await client.call(
            "data.replace",
            {
                "world_id": world_id,
                "lease": lease,
                "expected_revision": snapshot["revision"],
                "data": {"counter": counter, "payload": payload},
            },
        )
        data_replace_samples.append((time.perf_counter() - started) * 1000)
        await asyncio.sleep(inter_call_interval_seconds)
    return {
        "world_snapshot": snapshot_samples,
        "data_replace": data_replace_samples,
    }


async def measure_reconnect(runtime: str, sequence: int) -> float:
    async with Client(runtime, f"wincraft.perf.reconnect.owner.{sequence}") as owner:
        world_id, _owner_lease, join_key = await create_synthetic_world(owner, sequence)

    replacement = Client(runtime, f"wincraft.perf.reconnect.writer.{sequence}")
    started = time.perf_counter()
    async with replacement:
        joined = await replacement.call(
            "world.join",
            {"world_id": world_id, "join_key": join_key, "mode": "write"},
        )
        elapsed = (time.perf_counter() - started) * 1000
        lease = joined.get("lease")
        if not isinstance(lease, dict):
            raise RuntimeError("Host did not issue a new writer lease after reconnect")
        await quiet_destroy(replacement, world_id, lease)
    return elapsed


async def measure_refresh_soak(client: Client, args: argparse.Namespace) -> dict[str, Any]:
    world_id, lease, _join_key = await create_synthetic_world(
        client,
        args.world_cycles + 1,
        visible=args.soak_visible,
        title_prefix="WinCraft B11-01 synthetic refresh soak",
    )
    samples: list[float] = []
    updates = 0
    try:
        scene = {
            "root": {
                "id": "root",
                "kind": "stack",
                "props": {"gap": 8},
                "children": [
                    {"id": "title", "kind": "text", "props": {"text": "Synthetic refresh soak", "size": "heading"}},
                    {"id": "counter", "kind": "metric", "props": {
                        "label": "Synthetic refreshes",
                        "value": {"$path": "/counter"},
                    }},
                ],
            },
            "data": {"counter": 0},
        }
        await client.mutate("scene.replace", world_id, lease, scene=scene)
        deadline = time.monotonic() + args.soak_seconds
        payload = {"synthetic": "refresh", "sample": "x" * args.payload_bytes}
        while time.monotonic() < deadline:
            started = time.perf_counter()
            await client.mutate(
                "data.replace",
                world_id,
                lease,
                data={"counter": updates, **payload},
            )
            samples.append((time.perf_counter() - started) * 1000)
            updates += 1
            remaining = deadline - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(min(args.refresh_interval_seconds, remaining))
    finally:
        await quiet_destroy(client, world_id, lease)
    return {
        "duration_seconds_requested": args.soak_seconds,
        "refresh_interval_seconds": args.refresh_interval_seconds,
        "window_visible": args.soak_visible,
        "updates": updates,
        "cleanup_confirmed": True,
        "data_replace_transaction_latency_ms": summarize(samples),
    }


async def run(args: argparse.Namespace) -> None:
    timings: dict[str, list[float]] = {
        "world_create": [],
        "world_destroy": [],
        "world_snapshot": [],
        "data_replace": [],
        "reconnect_and_write_join": [],
    }
    async with Client(args.runtime, "wincraft.b11-01.synthetic-performance") as client:
        for sequence in range(args.world_cycles):
            await measure_world_lifecycle(
                client,
                sequence,
                timings["world_create"],
                timings["world_destroy"],
                args.inter_call_interval_ms / 1000,
            )

        world_id, lease, _join_key = await create_synthetic_world(client, args.world_cycles)
        try:
            data_timings = await measure_data_round_trips(
                client,
                world_id,
                lease,
                snapshot_iterations=args.snapshot_iterations,
                data_iterations=args.data_iterations,
                payload_bytes=args.payload_bytes,
                inter_call_interval_seconds=args.inter_call_interval_ms / 1000,
            )
            for name, samples in data_timings.items():
                timings[name].extend(samples)
        finally:
            await quiet_destroy(client, world_id, lease)

    for sequence in range(args.reconnect_cycles):
        timings["reconnect_and_write_join"].append(await measure_reconnect(args.runtime, sequence))

    refresh_soak = None
    if args.soak_seconds > 0:
        async with Client(args.runtime, "wincraft.b11-01.synthetic-refresh-soak") as client:
            refresh_soak = await measure_refresh_soak(client, args)

    print(json.dumps({
        "schema": "wincraft.synthetic-provider-latency.v1",
        "synthetic_only": True,
        "provider_type": "wincraft.performance-probe",
        "workload": {
            "world_cycles": args.world_cycles,
            "snapshot_iterations": args.snapshot_iterations,
            "data_iterations": args.data_iterations,
            "payload_bytes": args.payload_bytes,
            "inter_call_interval_ms": args.inter_call_interval_ms,
            "reconnect_cycles": args.reconnect_cycles,
            "soak_seconds": args.soak_seconds,
            "refresh_interval_seconds": args.refresh_interval_seconds,
            "soak_visible": args.soak_visible,
            "window_visible": False,
        },
        "latency_ms": {name: summarize(values) for name, values in timings.items()},
        "refresh_soak": refresh_soak,
        "identifiers_or_leases_recorded": False,
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument("--world-cycles", type=int, default=5)
    parser.add_argument("--snapshot-iterations", type=int, default=40)
    parser.add_argument("--data-iterations", type=int, default=20)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--reconnect-cycles", type=int, default=3)
    parser.add_argument("--inter-call-interval-ms", type=int, default=25)
    parser.add_argument("--soak-seconds", type=int, default=0)
    parser.add_argument("--refresh-interval-seconds", type=float, default=5)
    parser.add_argument("--soak-visible", action="store_true",
                        help="Show the small synthetic refresh window during the soak")
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 1 <= args.world_cycles <= 50:
        parser.error("--world-cycles must be between 1 and 50")
    if not 1 <= args.snapshot_iterations <= 500:
        parser.error("--snapshot-iterations must be between 1 and 500")
    if not 1 <= args.data_iterations <= 500:
        parser.error("--data-iterations must be between 1 and 500")
    if not 0 <= args.payload_bytes <= 32_768:
        parser.error("--payload-bytes must be between 0 and 32768")
    if not 1 <= args.reconnect_cycles <= 20:
        parser.error("--reconnect-cycles must be between 1 and 20")
    if not 10 <= args.inter_call_interval_ms <= 1000:
        parser.error("--inter-call-interval-ms must be between 10 and 1000")
    if not 0 <= args.soak_seconds <= 3600:
        parser.error("--soak-seconds must be between 0 and 3600")
    if not 1 <= args.refresh_interval_seconds <= 60:
        parser.error("--refresh-interval-seconds must be between 1 and 60")
    if args.soak_visible and args.soak_seconds == 0:
        parser.error("--soak-visible requires --soak-seconds")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
