"""Show TeamSense cached model quotas in a read-only WinCraft floating window."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PYTHON_EXAMPLES = Path(__file__).resolve().parents[2] / "python"
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import Client, add_runtime_args, destroy_world_safely, event_world_id, require_runtime  # noqa: E402
from team_sense_quota import (  # noqa: E402
    TeamSenseApiError,
    build_quota_scene,
    fetch_team_sense_models,
    normalize_models_snapshot,
    quota_window_spec,
    synthetic_demo_snapshot,
    validate_base_url,
    with_api_read_state,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _team_sense_token() -> str:
    token = os.environ.get("TEAM_SENSE_API_TOKEN")
    if token:
        return token
    if not sys.stdin.isatty():
        raise RuntimeError("TEAM_SENSE_API_TOKEN is required in a non-interactive session")
    return getpass.getpass("TeamSense data:read token (input hidden): ")


async def run(args: argparse.Namespace) -> None:
    base_url: str | None = None
    token: str | None = None
    last_projection: dict[str, Any] | None = None
    api_error_code: str | None = None
    last_attempt_at = _now()
    if args.demo:
        last_projection = normalize_models_snapshot(
            synthetic_demo_snapshot(),
            api_connected=True,
            api_observed_at=last_attempt_at,
            demo=True,
        )
    else:
        raw_base_url = args.api_base_url or os.environ.get("TEAM_SENSE_BASE_URL")
        if not raw_base_url:
            raise RuntimeError("--api-base-url or TEAM_SENSE_BASE_URL is required")
        base_url = validate_base_url(raw_base_url)
        token = _team_sense_token()
        try:
            last_projection = normalize_models_snapshot(
                await asyncio.to_thread(fetch_team_sense_models, base_url, token),
                api_connected=True,
                api_observed_at=last_attempt_at,
            )
        except TeamSenseApiError as exc:
            api_error_code = exc.code
            last_attempt_at = _now()
            last_projection = normalize_models_snapshot(
                {},
                api_connected=False,
                api_observed_at=last_attempt_at,
                api_error_code=api_error_code,
            )

    world_id: str | None = None
    lease: dict[str, Any] | None = None
    world_deleted = False
    async with Client(args.runtime, "python.integration.model-quota.teamsense", args.ws_url) as client:
        client.require_capabilities(
            components=("stack", "row", "text", "badge", "metric", "progress", "divider"),
            scene_features=("theme_tokens",),
            window_properties=("text_selectable", "surface_opacity"),
        )
        created = await client.call(
            "world.create",
            {
                "window": quota_window_spec(demo=args.demo),
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
                    if await _wait_for_world_or_timeout(client, world_id, args.duration_seconds):
                        world_deleted = True
                        return
                    break
                if await _wait_for_world_or_timeout(client, world_id, args.refresh_seconds):
                    world_deleted = True
                    return
                last_attempt_at = _now()
                try:
                    assert base_url is not None and token is not None
                    last_projection = normalize_models_snapshot(
                        await asyncio.to_thread(fetch_team_sense_models, base_url, token),
                        api_connected=True,
                        api_observed_at=last_attempt_at,
                    )
                except TeamSenseApiError as exc:
                    # Keep the last successful in-memory snapshot and show API disconnect separately.
                    api_error_code = exc.code
                    last_projection = with_api_read_state(
                        last_projection,
                        api_connected=False,
                        api_observed_at=last_attempt_at,
                        api_error_code=api_error_code,
                    )
        finally:
            if world_id is not None and lease is not None and not world_deleted:
                await destroy_world_safely(
                    client,
                    world_id,
                    lease,
                    provider_name="TeamSense model quota",
                )


async def _wait_for_world_or_timeout(client: Client, world_id: str, duration: float) -> bool:
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
        "--api-base-url",
        default=os.environ.get("TEAM_SENSE_BASE_URL"),
        help="Explicit TeamSense API origin; remote origins must use HTTPS",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=60,
        help="How often to read the cache-backed GET endpoint (10..300 seconds)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use synthetic data only; no TeamSense network request or token is used",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=120,
        help="Demo window lifetime (1..600 seconds)",
    )
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 10 <= args.refresh_seconds <= 300:
        parser.error("--refresh-seconds must be between 10 and 300")
    if not 1 <= args.duration_seconds <= 600:
        parser.error("--duration-seconds must be between 1 and 600")
    if not args.demo and not args.api_base_url:
        parser.error("--api-base-url or TEAM_SENSE_BASE_URL is required unless --demo is used")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
