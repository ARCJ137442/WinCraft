"""Enable the WinCraft bridge item in a marked temporary TrafficMonitor copy."""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path


STAGE_MARKER = ".wincraft-trafficmonitor-stage"
STAGE_MARKER_CONTENT = b"wincraft-trafficmonitor-stage-v1\n"
BRIDGE_DLL = Path("plugins") / "wincraft_trafficmonitor_bridge.dll"
DISPLAY_ITEMS_KEY = b"plugin_display_item"
BRIDGE_ITEM_ID = b"wincraft.bridge"


def _line_parts(line: bytes) -> tuple[bytes, bytes]:
    if line.endswith(b"\r\n"):
        return line[:-2], b"\r\n"
    if line.endswith(b"\n"):
        return line[:-1], b"\n"
    if line.endswith(b"\r"):
        return line[:-1], b"\r"
    return line, b""


def enable_bridge_item(config_bytes: bytes) -> tuple[bytes, bool]:
    """Set only an empty plugin_display_item value, preserving all other bytes."""
    lines = config_bytes.splitlines(keepends=True)
    matches: list[tuple[int, bytes, bytes, int, bytes]] = []
    for index, line in enumerate(lines):
        body, newline = _line_parts(line)
        key, separator, value = body.partition(b"=")
        if separator and key.strip().lower() == DISPLAY_ITEMS_KEY:
            matches.append((index, body, newline, len(key) + 1, value.strip()))

    if len(matches) != 1:
        raise ValueError("config.ini must contain exactly one plugin_display_item key")

    index, body, newline, value_offset, current_value = matches[0]
    if current_value == BRIDGE_ITEM_ID:
        return config_bytes, False
    if current_value:
        existing_items = re.split(rb"[|,;\s]+", current_value)
        if BRIDGE_ITEM_ID in existing_items:
            return config_bytes, False
        raise ValueError(
            "plugin_display_item already contains other entries; enable the bridge in the staged UI"
        )

    lines[index] = body[:value_offset] + BRIDGE_ITEM_ID + newline
    return b"".join(lines), True


def configure_staged_copy(
    stage_directory: Path, *, create_config_if_missing: bool = False
) -> bool:
    stage = stage_directory.resolve(strict=True)
    marker = stage / STAGE_MARKER
    if not marker.is_file() or marker.read_bytes() != STAGE_MARKER_CONTENT:
        raise ValueError("directory is not marked as a WinCraft temporary stage")
    if not (stage / "TrafficMonitor.exe").is_file():
        raise ValueError("staged TrafficMonitor.exe is missing")
    if not (stage / BRIDGE_DLL).is_file():
        raise ValueError("staged WinCraft bridge DLL is missing")

    config = stage / "config.ini"
    if config.is_file():
        original_bytes = config.read_bytes()
    elif create_config_if_missing:
        original_bytes = (
            b"[config]\r\n"
            b"show_task_bar_wnd=true\r\n"
            b"plugin_disabled=\r\n"
            b"[task_bar]\r\n"
            b"plugin_display_item=\r\n"
        )
    else:
        raise ValueError("staged config.ini is missing")
    updated_bytes, changed = enable_bridge_item(original_bytes)
    if not changed:
        return False

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".wincraft-config-", suffix=".tmp", dir=stage, delete=False
        ) as temporary:
            temporary.write(updated_bytes)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, config)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-directory", required=True, type=Path)
    parser.add_argument("--create-config-if-missing", action="store_true")
    args = parser.parse_args()
    try:
        updated = configure_staged_copy(
            args.stage_directory, create_config_if_missing=args.create_config_if_missing
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {"status": "updated" if updated else "already_enabled", "item_id": "wincraft.bridge"},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
