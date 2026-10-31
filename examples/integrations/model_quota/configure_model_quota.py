"""Interactive Windows launcher for the model quota Provider."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .provider import (
        DEEPSEEK_API_KEY_ENV,
        MINIMAX_API_KEY_ENV,
        show_source_configuration_dialog,
        tkinter_available,
    )
else:
    from provider import (
        DEEPSEEK_API_KEY_ENV,
        MINIMAX_API_KEY_ENV,
        show_source_configuration_dialog,
        tkinter_available,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROVIDER_SCRIPT = Path(__file__).resolve().with_name("provider.py")


def build_provider_command(runtime_path: str | Path, sources: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        str(PROVIDER_SCRIPT),
        "--runtime",
        str(runtime_path),
    ]
    for source, argument in (
        ("codex_rollout", "--codex-rollout-quota"),
        ("codex_live", "--codex-quota"),
        ("deepseek", "--deepseek-quota"),
        ("minimax", "--minimax-quota"),
    ):
        if sources.get(source) is True:
            command.append(argument)
    return command


def build_provider_environment(
    base: dict[str, str], sources: dict[str, Any]
) -> dict[str, str]:
    environment = dict(base)
    for source, key_name, env_name in (
        ("deepseek", "deepseek_key", DEEPSEEK_API_KEY_ENV),
        ("minimax", "minimax_key", MINIMAX_API_KEY_ENV),
    ):
        key = sources.get(key_name, "") if sources.get(source) is True else ""
        if isinstance(key, str) and key.strip():
            environment[env_name] = key.strip()
        else:
            environment.pop(env_name, None)
    return environment


def prompt_runtime_path() -> Path | None:
    raw_path = input(
        "粘贴 WinCraft 世界管理器中的连接描述文件路径（只输入路径，不要打开或分享文件内容）：\n> "
    ).strip().strip('"')
    if not raw_path:
        try:
            from tkinter import Tk, filedialog

            root = Tk()
            root.withdraw()
            raw_path = filedialog.askopenfilename(
                title="选择 WinCraft 连接描述文件",
                filetypes=[("WinCraft runtime descriptor", "*.json"), ("All files", "*.*")],
            )
            root.destroy()
        except Exception:
            return None
    path = Path(raw_path).expanduser()
    if path.is_file():
        return path
    return None


def main() -> int:
    runtime_path = prompt_runtime_path()
    if runtime_path is None:
        print("没有选择有效的连接描述文件。请从世界管理器复制路径后重试。")
        return 2
    configuration = show_source_configuration_dialog(
        {
            "codex_rollout": True,
            "codex_live": False,
            "deepseek": False,
            "minimax": False,
        },
        focus="codex_rollout",
    )
    if configuration is None:
        if not tkinter_available():
            print("This Python installation does not include Tkinter; reinstall Python with Tcl/Tk support.")
            return 2
        print("来源设置已取消，没有启动提供者。")
        return 0
    command = build_provider_command(runtime_path, configuration)
    environment = build_provider_environment(dict(os.environ), configuration)
    try:
        subprocess.Popen(command, cwd=REPOSITORY_ROOT, env=environment, shell=False)
    except OSError as error:
        print(f"提供者无法启动：{error}")
        return 1
    print("额度悬浮窗提供者已启动。此终端关闭后，提供者也会停止。API Key 不会写入磁盘。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
