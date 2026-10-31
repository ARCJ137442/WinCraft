"""Local Obsidian workspace metadata and focus timer Provider."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PYTHON_EXAMPLES = Path(__file__).resolve().parent
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import Client, add_runtime_args, destroy_world_safely, event_world_id, require_runtime  # noqa: E402

PLUGIN_ID = "wincraft-workspace-dashboard"
SNAPSHOT_SCHEMA = "wincraft.obsidian-workspace.v1"
COMMAND_SCHEMA = "wincraft.obsidian-workspace.command.v1"
MAX_SNAPSHOT_BYTES = 262_144
MAX_TABS = 16
MAX_WINDOWS = 8
INSTANCE_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
FOCUS_ACTIONS = {"focus.start", "focus.pause", "focus.resume", "focus.stop"}


def bridge_directory() -> Path:
    local_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_data) if local_data else Path.home() / ".local" / "share"
    return base / "WinCraft" / "ObsidianWorkspace" / "instances"


def _safe_title(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value if character.isprintable()).strip()[:120]


def _read_instance(path: Path, *, now: datetime) -> dict[str, Any]:
    metadata = path.lstat()
    if path.is_symlink() or not path.is_file() or metadata.st_size > MAX_SNAPSHOT_BYTES:
        raise ValueError("Obsidian instance snapshot is linked or exceeds the local size limit.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("kind") != SNAPSHOT_SCHEMA:
        raise ValueError("Obsidian workspace snapshot has an unsupported schema.")
    instance_id = value.get("instanceId")
    if not isinstance(instance_id, str) or not INSTANCE_ID.fullmatch(instance_id) or path.stem != instance_id:
        raise ValueError("Obsidian workspace snapshot identity does not match its file name.")
    for key in ("fileCount", "workspacePaneCount"):
        count = value.get(key)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0 or count > 10_000_000:
            raise ValueError("Obsidian workspace snapshot contains an invalid count.")
    tabs = value.get("tabs")
    if not isinstance(tabs, list) or len(tabs) > MAX_TABS:
        raise ValueError("Obsidian workspace snapshot contains too many tabs.")
    safe_tabs = [_safe_title(tab) for tab in tabs]
    if not all(isinstance(tab, str) and len(tab) <= 120 for tab in tabs):
        raise ValueError("Obsidian workspace snapshot contains invalid tab titles.")
    generated = value.get("generatedAt")
    try:
        observed = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("Obsidian workspace snapshot timestamp is invalid.") from None
    focus = value.get("focus")
    if not isinstance(focus, dict) or focus.get("state") not in {"idle", "running", "paused", "completed"}:
        raise ValueError("Obsidian focus timer state is invalid.")
    elapsed = focus.get("elapsedSeconds")
    duration = focus.get("durationSeconds")
    if not isinstance(elapsed, int) or isinstance(elapsed, bool) or not 0 <= elapsed <= 7200:
        raise ValueError("Obsidian focus timer elapsed duration is invalid.")
    if not isinstance(duration, int) or isinstance(duration, bool) or not 60 <= duration <= 7200:
        raise ValueError("Obsidian focus timer target duration is invalid.")
    latest_file = value.get("latestFileMtime")
    if latest_file is not None and not isinstance(latest_file, str):
        raise ValueError("Obsidian workspace modification time is invalid.")
    return {
        "instanceId": instance_id,
        "generatedAt": generated,
        "ageSeconds": max(0.0, (now - observed.astimezone(timezone.utc)).total_seconds()),
        "fileCount": value["fileCount"],
        "workspacePaneCount": value["workspacePaneCount"],
        "activeTitle": _safe_title(value.get("activeTitle")) or "Obsidian window",
        "latestFileMtime": latest_file,
        "tabs": safe_tabs,
        "focus": {"state": focus["state"], "elapsedSeconds": elapsed, "durationSeconds": duration},
    }


def read_snapshots(directory: Path | None = None, *, now: datetime | None = None) -> list[dict[str, Any]]:
    root = directory or bridge_directory()
    if not root.is_dir():
        return []
    observed = now or datetime.now(timezone.utc)
    snapshots: list[dict[str, Any]] = []
    for path in root.iterdir():
        if not path.name.endswith(".json") or not INSTANCE_ID.fullmatch(path.stem):
            continue
        try:
            snapshots.append(_read_instance(path, now=observed))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    snapshots.sort(key=lambda item: (item["ageSeconds"], item["instanceId"]))
    return snapshots[:MAX_WINDOWS]


def _format_time(value: Any) -> str:
    if not isinstance(value, str):
        return "暂无文件"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return "未知"


def build_scene(
    snapshots: list[dict[str, Any]],
    selected_instance_id: str | None = None,
    *,
    stale_after: float = 8.0,
) -> dict[str, Any]:
    """Render one selected workspace at a time with compact next/previous controls."""
    def node(node_id: str, kind: str, props: dict[str, Any], children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {"id": node_id, "kind": kind, "props": props, "children": children or []}

    ordered = list(snapshots[:MAX_WINDOWS])
    selected_index = next(
        (index for index, item in enumerate(ordered) if item["instanceId"] == selected_instance_id),
        0,
    )
    selected = ordered[selected_index] if ordered else None
    fresh_count = sum(item["ageSeconds"] <= stale_after for item in ordered)
    children = [
        node("obsidian-heading", "row", {"gap": 10, "align": "center"}, [
            node("obsidian-title", "button", {
                "label": "Obsidian",
                "action": "obsidian.activate",
                "appearance": "title",
                "native_window_action": {"application": "obsidian", "operation": "activate"},
            }),
            node("obsidian-window-count", "metric", {
                "label": "已启用插件的窗口",
                "value": fresh_count,
                "unit": "个",
                "caption": f"共发现 {len(ordered)} 个窗口快照",
            }),
            node("obsidian-stale-count", "badge", {
                "text": f"{len(ordered) - fresh_count} 个过期" if len(ordered) > fresh_count else "",
                "tone": "danger" if len(ordered) > fresh_count else "muted",
            }),
        ]),
    ]
    if selected is None:
        children.append(node("obsidian-no-instances", "text", {
            "text": "尚未发现启用 WinCraft Workspace Dashboard 的 Obsidian 窗口。",
            "size": "small",
        }))
    else:
        instance_id = selected["instanceId"]
        stale = selected["ageSeconds"] > stale_after
        active_title = selected["activeTitle"]
        title_action = {"application": "obsidian", "operation": "activate"}
        if active_title and active_title != "Obsidian window":
            title_action["title_contains"] = active_title[:128]
        children.extend([
            node("obsidian-selected-window", "row", {"gap": 8, "align": "center"}, [
                node("obsidian-window-previous", "button", {
                    "label": "←",
                    "action": "window.select.previous",
                    "disabled": len(ordered) < 2,
                }),
                node("obsidian-window-position", "text", {
                    "text": f"窗口 {selected_index + 1} / {len(ordered)}",
                    "size": "small",
                }),
                node("obsidian-window-next", "button", {
                    "label": "→",
                    "action": "window.select.next",
                    "disabled": len(ordered) < 2,
                }),
                node("obsidian-selected-stale", "badge", {
                    "text": "数据过期" if stale else "",
                    "tone": "danger" if stale else "muted",
                }),
            ]),
            node("obsidian-activate-selected", "button", {
                "label": active_title,
                "action": f"obsidian.activate:{instance_id}",
                "native_window_action": title_action,
            }),
            node("obsidian-window-details", "key_value", {"items": [
                {"key": "Vault 文件数", "value": selected["fileCount"]},
                {"key": "工作区面板", "value": selected["workspacePaneCount"]},
                {"key": "最近修改", "value": _format_time(selected["latestFileMtime"])},
                *({"key": f"标签 {index + 1}", "value": tab} for index, tab in enumerate(selected["tabs"][:5])),
                *([{"key": "其他标签", "value": len(selected["tabs"]) - 5}] if len(selected["tabs"]) > 5 else []),
            ]}),
        ])
        focus = selected["focus"]
        elapsed = min(focus["elapsedSeconds"], focus["durationSeconds"])
        remaining = max(0, focus["durationSeconds"] - elapsed)
        state_label = {"idle": "待开始", "running": "进行中", "paused": "已暂停", "completed": "已完成"}[focus["state"]]
        children.extend([
            node("obsidian-focus-divider", "divider", {}),
            node("obsidian-focus-heading", "text", {"text": "专注计时", "size": "heading"}),
            node("obsidian-focus-time", "metric", {
                "label": state_label,
                "value": f"{remaining // 60:02d}:{remaining % 60:02d}",
                "caption": f"专注时长 {focus['durationSeconds'] // 60} 分钟",
            }),
            node("obsidian-focus-progress", "progress", {
                "label": "已完成",
                "value": elapsed,
                "max": focus["durationSeconds"],
            }),
        ])
        if not stale:
            if focus["state"] in {"idle", "completed"}:
                action_pairs = [("开始专注", "focus.start")]
            elif focus["state"] == "running":
                action_pairs = [("暂停计时", "focus.pause"), ("重置计时", "focus.stop")]
            else:
                action_pairs = [("继续计时", "focus.resume"), ("重置计时", "focus.stop")]
            children.append(node("obsidian-focus-actions", "row", {"gap": 8}, [
                node(f"obsidian-focus-action-{action}", "button", {
                    "label": label,
                    "action": f"{action}:{instance_id}",
                })
                for label, action in action_pairs
            ]))
        children.append(node("obsidian-window-updated", "text", {
            "text": f"本地更新时间：{selected['generatedAt']}", "size": "small",
        }))
    children.append(node("obsidian-data-boundary", "text", {
        "text": "只读取本地文件与工作区元数据；不读取笔记正文。",
        "size": "small",
    }))
    return {
        "root": node("obsidian-root", "stack", {"gap": 10}, children),
        "data": {},
        "theme": {"background": "#1A1820", "foreground": "#F4EFFA", "accent": "#C4B5FD",
                  "font_scale": 1.0, "radius_px": 12, "spacing_px": 10},
    }


def write_command(directory: Path, instance_id: str, action: str) -> str:
    if not INSTANCE_ID.fullmatch(instance_id) or action not in FOCUS_ACTIONS:
        raise ValueError("Unsupported Obsidian focus request.")
    command_path = directory / f"{instance_id}.command.json"
    if command_path.exists():
        raise RuntimeError("This Obsidian window already has a focus timer request in progress.")
    request_id = str(uuid.uuid4())
    content = json.dumps({"kind": COMMAND_SCHEMA, "requestId": request_id, "action": action})
    temporary = directory / f"{instance_id}.{request_id}.tmp"
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, command_path)
    return request_id


async def wait_for_receipt(directory: Path, instance_id: str, request_id: str, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    path = directory / f"{instance_id}.receipt.json"
    while asyncio.get_running_loop().time() < deadline:
        try:
            metadata = path.lstat()
            if path.is_symlink() or not path.is_file() or metadata.st_size > 4096:
                raise RuntimeError("Obsidian focus timer receipt is invalid.")
            receipt = json.loads(path.read_text(encoding="utf-8"))
            if receipt.get("requestId") == request_id:
                path.unlink(missing_ok=True)
                if receipt.get("ok") is True:
                    return
                raise RuntimeError("Obsidian rejected the focus timer request.")
        except FileNotFoundError:
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError("Obsidian did not respond to the focus timer request.")


async def run(args: argparse.Namespace) -> None:
    directory = args.bridge_dir or bridge_directory()
    snapshots = read_snapshots(directory)
    if not snapshots:
        raise RuntimeError("No enabled WinCraft Workspace Dashboard instances were found.")
    selected_instance_id = snapshots[0]["instanceId"]
    world_id: str | None = None
    lease: dict[str, Any] | None = None
    deleted = False
    async with Client(args.runtime, "python.integration.obsidian-workspace", args.ws_url) as client:
        client.require_capabilities(
            components=("stack", "row", "text", "badge", "button", "metric", "progress", "key_value", "divider"),
            scene_features=("theme_tokens",),
            window_properties=("text_selectable", "surface_opacity", "background_drag_enabled"),
        )
        created = await client.call("world.create", {
            "window": {
                "title": "Obsidian Workspace",
                "width": 420,
                "height": 560,
                "always_on_top": True,
                "resizable": True,
                "title_bar_visible": False,
                "background_drag_enabled": True,
                "text_selectable": False,
                "surface_opacity": 0.8,
            },
            "join_policy": "invite",
            "claim": True,
        })
        world_id = created["world"]["id"]
        lease = created.get("lease")
        if not isinstance(lease, dict):
            raise RuntimeError("Host did not issue a writer lease for the Obsidian workspace window.")
        try:
            while True:
                await client.mutate(
                    "scene.replace",
                    world_id,
                    lease,
                    scene=build_scene(snapshots, selected_instance_id, stale_after=args.stale_after),
                )
                deadline = asyncio.get_running_loop().time() + args.refresh_seconds
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        event = await asyncio.wait_for(client.events.get(), timeout=remaining)
                    except TimeoutError:
                        break
                    if event.get("event") == "world.deleted" and event_world_id(event) == world_id:
                        deleted = True
                        return
                    if event.get("event") in {"connection.error", "connection.closed", "provider.error"}:
                        raise ConnectionError("WinCraft host connection ended")
                    if event.get("event") != "interaction":
                        continue
                    interaction = event.get("data")
                    if not isinstance(interaction, dict) or interaction.get("world_id") != world_id:
                        continue
                    action = interaction.get("action")
                    ok, message = True, None
                    try:
                        if action == "obsidian.activate" or (isinstance(action, str) and action.startswith("obsidian.activate:")):
                            pass  # Tauri has already activated the selected existing window.
                        elif action in {"window.select.next", "window.select.previous"}:
                            identifiers = [item["instanceId"] for item in snapshots]
                            current_index = identifiers.index(selected_instance_id) if selected_instance_id in identifiers else 0
                            delta = 1 if action == "window.select.next" else -1
                            selected_instance_id = identifiers[(current_index + delta) % len(identifiers)]
                        elif isinstance(action, str) and action.startswith("focus.") and ":" in action:
                            focus_action, instance_id = action.rsplit(":", 1)
                            request_id = write_command(directory, instance_id, focus_action)
                            await wait_for_receipt(directory, instance_id, request_id)
                        else:
                            raise ValueError("This action is not supported by the Obsidian Workspace Provider.")
                    except Exception as error:
                        ok, message = False, str(error)
                    await client.call("action.result", {
                        "world_id": world_id,
                        "lease": lease,
                        "event_id": interaction.get("id"),
                        "ok": ok,
                        "message": message,
                    })
                latest = read_snapshots(directory)
                if latest:
                    snapshots = latest
                    if selected_instance_id not in {item["instanceId"] for item in snapshots}:
                        selected_instance_id = snapshots[0]["instanceId"]
                else:
                    snapshots = [
                        {**item, "ageSeconds": item["ageSeconds"] + args.refresh_seconds}
                        for item in snapshots
                    ]
        finally:
            if world_id is not None and lease is not None and not deleted:
                await destroy_world_safely(client, world_id, lease, provider_name="Obsidian Workspace Dashboard")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument("--bridge-dir", type=Path, help="Optional local instance snapshot folder for testing")
    parser.add_argument("--refresh-seconds", type=float, default=2.0)
    parser.add_argument("--stale-after", type=float, default=8.0)
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 1 <= args.refresh_seconds <= 10:
        parser.error("--refresh-seconds must be between 1 and 10")
    if not 3 <= args.stale_after <= 60:
        parser.error("--stale-after must be between 3 and 60")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
