"""Small desktop setup form for the generic Obsidian Workspace Provider."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


ROOT = Path(__file__).resolve().parents[3]
PROVIDER = ROOT / "examples" / "python" / "obsidian_workspace.py"
REQUIREMENTS = ROOT / "examples" / "python" / "requirements.txt"
sys.path.insert(0, str(ROOT / "examples" / "python"))
from obsidian_workspace import read_snapshots  # noqa: E402


def main() -> int:
    root = tk.Tk()
    root.title("WinCraft · Obsidian 工作区")
    root.geometry("620x300")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="连接 Obsidian 工作区", font=("Segoe UI", 16, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="先在要监控的 Obsidian Vault 中启用 WinCraft Workspace Dashboard 插件。多个已启用窗口会合并显示。",
        wraplength=570,
    ).pack(anchor="w", pady=(6, 16))

    runtime = tk.StringVar()
    for row, label, variable, picker in ((0, "连接描述文件路径", runtime, pick_runtime),):
        ttk.Label(frame, text=label).grid(row=row * 2, column=0, sticky="w", pady=(4, 2))
        line = ttk.Frame(frame)
        line.grid(row=row * 2 + 1, column=0, sticky="ew")
        ttk.Entry(line, textvariable=variable, width=66).pack(side="left", fill="x", expand=True)
        ttk.Button(line, text="浏览…", command=lambda v=variable, p=picker: v.set(p())).pack(side="left", padx=(8, 0))
    frame.columnconfigure(0, weight=1)

    status = ttk.Label(frame, text="连接路径只会传给本机 Provider 进程；运行数据不会复制进仓库。", wraplength=570)
    status.grid(row=4, column=0, sticky="w", pady=(14, 10))

    def start() -> None:
        runtime_path = Path(runtime.get().strip().strip('"')).expanduser()
        if not runtime_path.is_file():
            messagebox.showerror("需要连接描述文件", "请复制世界管理器显示的连接描述文件路径。")
            return
        snapshots = read_snapshots()
        if not snapshots:
            messagebox.showerror(
                "尚未发现插件快照",
                "请先把 examples/obsidian-plugin 安装到至少一个 Obsidian Vault 并启用，再重试。",
            )
            return
        if importlib.util.find_spec("websockets") is None:
            accepted = messagebox.askyesno(
                "需要 Python 依赖",
                "WinCraft Provider 需要 websockets Python 包。现在通过 pip 安装 examples/python/requirements.txt 吗？",
            )
            if not accepted:
                return
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
                    cwd=ROOT,
                    check=True,
                    shell=False,
                )
            except (OSError, subprocess.CalledProcessError) as error:
                messagebox.showerror("安装失败", f"Python 依赖未安装：{error}")
                return
        try:
            subprocess.Popen(
                [sys.executable, str(PROVIDER), "--runtime", str(runtime_path)],
                cwd=ROOT,
                shell=False,
            )
        except OSError as error:
            messagebox.showerror("启动失败", f"Provider 无法启动：{error}")
            return
        messagebox.showinfo("已启动", "Obsidian Workspace 悬浮窗提供者已启动。关闭随附终端即可停止。")
        root.destroy()

    ttk.Button(frame, text="启动悬浮窗", command=start).grid(row=5, column=0, sticky="e", pady=(8, 0))
    root.mainloop()
    return 0


def pick_runtime() -> str:
    return filedialog.askopenfilename(
        title="选择 WinCraft 连接描述文件",
        filetypes=[("WinCraft descriptor", "*.json"), ("All files", "*.*")],
    )


if __name__ == "__main__":
    raise SystemExit(main())
