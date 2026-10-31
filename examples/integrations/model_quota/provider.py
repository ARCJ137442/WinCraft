'''在 WinCraft 悬浮窗呈现本机 Codex、DeepSeek 与 MiniMax 额度。'''
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL_QUOTA_DIR = Path(__file__).resolve().parent
PYTHON_EXAMPLES = Path(__file__).resolve().parents[2] / "python"
for import_path in (str(PYTHON_EXAMPLES), str(MODEL_QUOTA_DIR)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from client import (  # noqa: E402
    Client,
    add_runtime_args,
    destroy_world_safely,
    event_world_id,
    require_runtime,
)
if __package__:
    from .codex_quota import refresh_codex_source, synthetic_codex_quota  # noqa: E402
    from .codex_rollout_quota import refresh_codex_rollout_source  # noqa: E402
    from .provider_sources import (  # noqa: E402
        DEEPSEEK_API_KEY_ENV,
        MINIMAX_API_KEY_ENV,
        refresh_local_sources,
    )
    from .quota_projection import (  # noqa: E402
        build_quota_scene,
        normalize_quota_snapshot,
        quota_window_spec,
        synthetic_demo_snapshot,
    )
else:
    from codex_quota import refresh_codex_source, synthetic_codex_quota  # noqa: E402
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


def show_source_configuration_dialog(
    current: dict[str, bool], *, focus: str | None = None
) -> dict[str, Any] | None:
    """Show a local add/remove form; credentials remain in memory only."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return None

    root = tk.Tk()
    root.title("模型额度来源")
    root.resizable(False, False)
    root.geometry("430x430")
    root.minsize(430, 360)
    root.grab_set()
    root.focus_force()
    result: dict[str, Any] | None = None
    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="添加或移除额度来源", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="只勾选要显示的来源。API Key 仅在当前进程内存中使用，不会保存到文件。",
        wraplength=390,
    ).pack(anchor="w", pady=(6, 12))

    flags = {
        key: tk.BooleanVar(value=bool(current.get(key, False)))
        for key in ("codex_rollout", "codex_live", "deepseek", "minimax")
    }
    if focus in flags:
        flags[focus].set(True)
    key_vars = {
        "deepseek": tk.StringVar(value=os.environ.get(DEEPSEEK_API_KEY_ENV, "")),
        "minimax": tk.StringVar(value=os.environ.get(MINIMAX_API_KEY_ENV, "")),
    }

    def select_codex_local() -> None:
        if flags["codex_rollout"].get():
            flags["codex_live"].set(False)

    def select_codex_live() -> None:
        if flags["codex_live"].get():
            flags["codex_rollout"].set(False)

    ttk.Checkbutton(
        frame,
        text="Codex 本机额度快照（不联网）",
        variable=flags["codex_rollout"],
        command=select_codex_local,
    ).pack(anchor="w", pady=3)
    ttk.Checkbutton(
        frame,
        text="Codex 在线额度（实验性只读）",
        variable=flags["codex_live"],
        command=select_codex_live,
    ).pack(anchor="w", pady=3)

    for source, label in (("deepseek", "DeepSeek API Key"), ("minimax", "MiniMax API Key")):
        ttk.Checkbutton(frame, text=label, variable=flags[source]).pack(anchor="w", pady=(8, 2))
        ttk.Entry(frame, textvariable=key_vars[source], show="•", width=50).pack(anchor="w")

    status = ttk.Label(frame, text="取消会关闭此对话框且不改变当前来源。", wraplength=390)
    status.pack(anchor="w", pady=(12, 8))
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", side="bottom")

    def apply() -> None:
        nonlocal result
        if flags["codex_rollout"].get() and flags["codex_live"].get():
            status.configure(text="Codex 请选择一个来源。")
            return
        result = {key: value.get() for key, value in flags.items()}
        result["deepseek_key"] = key_vars["deepseek"].get().strip()
        result["minimax_key"] = key_vars["minimax"].get().strip()
        root.destroy()

    ttk.Button(buttons, text="取消", command=root.destroy).pack(side="right")
    ttk.Button(buttons, text="应用", command=apply).pack(side="right", padx=(0, 8))
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return result


def apply_source_configuration(args: argparse.Namespace, configuration: dict[str, Any]) -> None:
    args.codex_rollout_quota = configuration.get("codex_rollout") is True
    args.codex_quota = configuration.get("codex_live") is True
    args.deepseek_quota = configuration.get("deepseek") is True
    args.minimax_quota = configuration.get("minimax") is True
    for enabled, key_name, env_name in (
        (args.deepseek_quota, "deepseek_key", DEEPSEEK_API_KEY_ENV),
        (args.minimax_quota, "minimax_key", MINIMAX_API_KEY_ENV),
    ):
        key = configuration.get(key_name, "") if enabled else ""
        if isinstance(key, str) and key.strip():
            os.environ[env_name] = key.strip()
        else:
            os.environ.pop(env_name, None)


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
    args.source_config_changed = asyncio.Event()
    args.source_config_open = False
    args.source_config_error = None
    args.source_config_task = None
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
            components=("stack", "row", "text", "badge", "metric", "progress", "divider", "button"),
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
                scene_projection = dict(last_projection)
                if args.source_config_error:
                    scene_projection["source_config_error"] = args.source_config_error
                scene = build_quota_scene(scene_projection)
                await client.mutate("scene.replace", world_id, lease, scene=scene)
                if not announced:
                    print(
                        "Model quota window ready; source identity and freshness remain separate. "
                        f"World: {world_id}",
                        flush=True,
                    )
                    announced = True
                wait_seconds = args.duration_seconds or args.refresh_seconds
                wait_result = await wait_for_world_or_timeout(
                    client, world_id, wait_seconds, args, lease
                )
                if wait_result == "deleted":
                    world_deleted = True
                    return
                if wait_result == "timeout" and (args.demo or args.duration_seconds is not None):
                    break
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
            task = args.source_config_task
            if task is not None and not task.done():
                task.cancel()
            if world_id is not None and lease is not None and not world_deleted:
                await destroy_world_safely(
                    client,
                    world_id,
                    lease,
                    provider_name="model quota dashboard",
                )


async def __configure_sources_in_background(
    args: argparse.Namespace, focus: str | None
) -> None:
    current = {
        "codex_rollout": args.codex_rollout_quota,
        "codex_live": args.codex_quota,
        "deepseek": args.deepseek_quota,
        "minimax": args.minimax_quota,
    }
    try:
        configuration = await asyncio.to_thread(
            show_source_configuration_dialog,
            current,
            focus=focus,
        )
        if configuration is not None:
            apply_source_configuration(args, configuration)
            args.source_config_error = None
            args.source_config_changed.set()
        elif not tkinter_available():
            args.source_config_error = "此 Python 安装没有 Tkinter，无法打开来源设置。"
            args.source_config_changed.set()
    except Exception:
        args.source_config_error = "来源设置无法打开；没有保存任何 API Key。"
        args.source_config_changed.set()
    finally:
        args.source_config_open = False


async def wait_for_world_or_timeout(
    client: Client,
    world_id: str,
    duration: float,
    args: argparse.Namespace,
    lease: dict[str, Any],
) -> str:
    deadline = asyncio.get_running_loop().time() + duration
    while True:
        if args.source_config_changed.is_set():
            args.source_config_changed.clear()
            return "changed"
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return "timeout"
        try:
            message = await asyncio.wait_for(client.events.get(), timeout=min(remaining, 0.5))
        except TimeoutError:
            continue
        if message.get("event") == "world.deleted" and event_world_id(message) == world_id:
            return "deleted"
        if message.get("event") in {"connection.error", "connection.closed", "provider.error"}:
            raise ConnectionError("WinCraft host connection ended")
        if message.get("event") != "interaction":
            continue
        interaction = message.get("data")
        if not isinstance(interaction, dict) or interaction.get("world_id") != world_id:
            continue
        action = interaction.get("action")
        if not isinstance(action, str):
            continue

        if action == "quota.sources.configure" or action.startswith("quota.source.configure:"):
            if args.source_config_open:
                await client.call("action.result", {
                    "world_id": world_id,
                    "lease": lease,
                    "event_id": interaction.get("id"),
                    "ok": False,
                    "message": "The source settings dialog is already open.",
                })
                continue
            args.source_config_open = True
            focus_key = action.partition(":")[2] if ":" in action else ""
            focus = {
                "deepseek_balance": "deepseek",
                "minimax_quota": "minimax",
                "codex_rollout": "codex_rollout",
                "codex_live": "codex_live",
            }.get(focus_key)
            task = asyncio.create_task(__configure_sources_in_background(args, focus))
            args.source_config_task = task

            def clear_config_task(completed: asyncio.Task[Any]) -> None:
                if args.source_config_task is completed:
                    args.source_config_task = None

            task.add_done_callback(clear_config_task)
            await client.call("action.result", {
                "world_id": world_id,
                "lease": lease,
                "event_id": interaction.get("id"),
                "ok": True,
                "message": None,
            })
            continue
        if action.startswith("quota.source.remove:"):
            try:
                remove_source(args, action.partition(":")[2])
                ok, error = True, None
                outcome = "changed"
            except Exception:
                ok, error, outcome = False, "The selected source could not be removed.", "continue"
        else:
            continue
        await client.call("action.result", {
            "world_id": world_id,
            "lease": lease,
            "event_id": interaction.get("id"),
            "ok": ok,
            "message": error,
        })
        if outcome == "changed" and ok:
            return "changed"


def tkinter_available() -> bool:
    try:
        import tkinter  # noqa: F401
    except Exception:
        return False
    return True


def remove_source(args: argparse.Namespace, source: str) -> None:
    if source == "codex_rollout":
        args.codex_rollout_quota = False
    elif source == "codex_live":
        args.codex_quota = False
    elif source == "deepseek_balance":
        args.deepseek_quota = False
        os.environ.pop(DEEPSEEK_API_KEY_ENV, None)
    elif source == "minimax_quota":
        args.minimax_quota = False
        os.environ.pop(MINIMAX_API_KEY_ENV, None)


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
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
