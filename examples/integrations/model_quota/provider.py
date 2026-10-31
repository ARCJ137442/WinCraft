'''在 WinCraft 悬浮窗呈现本机 Codex、DeepSeek 与 MiniMax 额度。'''
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PYTHON_EXAMPLES = Path(__file__).resolve().parents[2] / "python"
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import (  # noqa: E402
    Client,
    add_runtime_args,
    destroy_world_safely,
    event_world_id,
    require_runtime,
)
from codex_quota import (  # noqa: E402
    refresh_codex_source,
    synthetic_codex_quota,
)
from codex_rollout_quota import refresh_codex_rollout_source  # noqa: E402
from provider_sources import (  # noqa: E402
    DEEPSEEK_API_KEY_ENV,
    MINIMAX_API_KEY_ENV,
    refresh_local_sources,
)
from quota_projection import (  # noqa: E402
    build_quota_scene,
    normalize_quota_snapshot,
    quota_window_spec,
    synthetic_demo_snapshot,
)


def __now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


async def __refresh_sources(
    *,
    codex_enabled: bool,
    codex_rollout_enabled: bool,
    codex_home: Path | None,
    deepseek_enabled: bool,
    minimax_enabled: bool,
    previous: dict[str, Any] | None,
    previous_source_snapshots: dict[str, Any] | None,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    observed = now or datetime.now(timezone.utc)
    observed_at = (
        observed.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    if previous is None:
        projection = normalize_quota_snapshot(
            {},
            observed_at=observed_at,
            enabled_sources=[],
        )
    else:
        projection = dict(previous)
    last_codex = projection.get("codex")
    if codex_rollout_enabled:
        codex_projection = await asyncio.to_thread(
            refresh_codex_rollout_source,
            enabled=True,
            explicit_home=codex_home,
            previous=last_codex,
            now=now,
        )
    else:
        codex_projection = await asyncio.to_thread(
            refresh_codex_source,
            enabled=codex_enabled,
            explicit_home=codex_home,
            previous=last_codex,
        )
    projection = await asyncio.to_thread(
        refresh_local_sources,
        deepseek_enabled=deepseek_enabled,
        minimax_enabled=minimax_enabled,
        previous=previous_source_snapshots,
        now=now,
    )
    projection["codex"] = codex_projection
    enabled_sources = [
        source
        for source, enabled in (
            ("codex_rollout", codex_rollout_enabled),
            ("codex_live", codex_enabled),
            ("deepseek_balance", deepseek_enabled),
            ("minimax_quota", minimax_enabled),
        )
        if enabled
    ]
    projected = normalize_quota_snapshot(
        projection,
        observed_at=observed_at,
        enabled_sources=enabled_sources,
    )
    projected["codex"] = codex_projection
    source_snapshots = {
        source: projection[source]
        for source, enabled in (("deepseek", deepseek_enabled), ("minimax", minimax_enabled))
        if enabled and isinstance(projection.get(source), dict)
    }
    return projected, source_snapshots


async def run(args: argparse.Namespace) -> None:
    last_projection: dict[str, Any]
    source_snapshots: dict[str, Any]
    if args.demo:
        last_projection = normalize_quota_snapshot(
            synthetic_demo_snapshot(),
            observed_at=__now(),
            enabled_sources=[],
            demo=True,
        )
        last_projection["codex"] = synthetic_codex_quota(observed_at=__now())
        source_snapshots = {}
    else:
        last_projection, source_snapshots = await __refresh_sources(
            codex_enabled=args.codex_quota,
            codex_rollout_enabled=args.codex_rollout_quota,
            codex_home=args.codex_home,
            deepseek_enabled=args.deepseek_quota,
            minimax_enabled=args.minimax_quota,
            previous=None,
            previous_source_snapshots=None,
        )

    world_id: str | None = None
    lease: dict[str, Any] | None = None
    world_deleted = False
    async with Client(args.runtime, "python.integration.model-quota", args.ws_url) as client:
        client.require_capabilities(
            components=("stack", "row", "text", "badge", "metric", "progress", "divider"),
            scene_features=("theme_tokens",),
            window_properties=("text_selectable", "surface_opacity"),
        )
        created = await client.call(
            "world.create",
            {
                "window": quota_window_spec(
                    demo=args.demo,
                    codex_enabled=args.codex_quota or args.codex_rollout_quota,
                    deepseek_enabled=args.deepseek_quota,
                    minimax_enabled=args.minimax_quota,
                ),
                "join_policy": "invite",
                "claim": True,
            },
        )
        world_id = created["world"]["id"]
        lease = created.get("lease")
        if not isinstance(lease, dict):
            raise RuntimeError("Host did not issue a writer lease for the quota window")
        try:
            announced = False
            while True:
                assert last_projection is not None
                scene = build_quota_scene(last_projection)
                await client.mutate("scene.replace", world_id, lease, scene=scene)
                if not announced:
                    print(
                        "Model quota window ready; source identity and freshness remain separate. "
                        f"World: {world_id}",
                        flush=True,
                    )
                    announced = True
                if args.demo:
                    if await __wait_for_world_or_timeout(client, world_id, args.duration_seconds):
                        world_deleted = True
                        return
                    break
                if args.duration_seconds is not None:
                    if await __wait_for_world_or_timeout(client, world_id, args.duration_seconds):
                        world_deleted = True
                        return
                    break
                if await __wait_for_world_or_timeout(client, world_id, args.refresh_seconds):
                    world_deleted = True
                    return
                last_projection, source_snapshots = await __refresh_sources(
                    codex_enabled=args.codex_quota,
                    codex_rollout_enabled=args.codex_rollout_quota,
                    codex_home=args.codex_home,
                    deepseek_enabled=args.deepseek_quota,
                    minimax_enabled=args.minimax_quota,
                    previous=last_projection,
                    previous_source_snapshots=source_snapshots,
                )
        finally:
            if world_id is not None and lease is not None and not world_deleted:
                await destroy_world_safely(
                    client,
                    world_id,
                    lease,
                    provider_name="model quota dashboard",
                )


async def __wait_for_world_or_timeout(client: Client, world_id: str, duration: float) -> bool:
    deadline = asyncio.get_running_loop().time() + duration
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return False
        try:
            message = await asyncio.wait_for(client.events.get(), timeout=remaining)
        except TimeoutError:
            return False
        if message.get("event") == "world.deleted" and event_world_id(message) == world_id:
            return True
        if message.get("event") in {"connection.error", "connection.closed", "provider.error"}:
            raise ConnectionError("WinCraft host connection ended")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument(
        "--codex-quota",
        action="store_true",
        help="Opt in to the experimental Codex HTTPS quota GET using local auth.json",
    )
    parser.add_argument(
        "--codex-rollout-quota",
        action="store_true",
        help="Read quota snapshots from bounded local Codex token_count rollout events; no network",
    )
    parser.add_argument(
        "--deepseek-quota",
        action="store_true",
        help=f"Opt in to DeepSeek fixed GET; reads {DEEPSEEK_API_KEY_ENV} only when enabled",
    )
    parser.add_argument(
        "--minimax-quota",
        action="store_true",
        help=f"Opt in to MiniMax fixed GET; reads {MINIMAX_API_KEY_ENV} only when enabled",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        help=(
            "Explicit Codex home containing sessions/ and/or auth.json "
            "(default: CODEX_HOME or ~/.codex)"
        ),
    )
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=60,
        help="How often to refresh enabled quota sources (10..300 seconds)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use synthetic data only; no credentials or network requests are used",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        help="Optional bounded Provider lifetime (1..600 seconds); --demo defaults to 120 seconds",
    )
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 10 <= args.refresh_seconds <= 300:
        parser.error("--refresh-seconds must be between 10 and 300")
    if args.demo and args.duration_seconds is None:
        args.duration_seconds = 120
    if args.duration_seconds is not None and not 1 <= args.duration_seconds <= 600:
        parser.error("--duration-seconds must be between 1 and 600")
    if args.codex_quota and args.codex_rollout_quota:
        parser.error("choose only one Codex quota source")
    if args.codex_home is not None and not (args.codex_quota or args.codex_rollout_quota):
        parser.error("--codex-home requires --codex-quota or --codex-rollout-quota")
    if not args.demo and not any(
        (args.codex_quota, args.codex_rollout_quota, args.deepseek_quota, args.minimax_quota)
    ):
        parser.error(
            "enable at least one quota source unless --demo is used"
        )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
