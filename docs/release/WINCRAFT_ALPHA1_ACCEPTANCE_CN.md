---
title: WinCraft 0.1.0-alpha.1 Windows 验收指南
updated_at: 2026-10-29
last_verified_at: 2026-10-29
status: local-release-acceptance-guide
audience: maintainer, Windows tester
---

# WinCraft 0.1.0-alpha.1 Windows 验收指南

## 本次构建

| 项目 | 值 |
|---|---|
| 源码提交 | `32c8eee63b107f5380d22c16dd26081886790ebd` |
| 程序路径 | `target/release/wincraft-desktop.exe` |
| 文件大小 | 12,429,312 bytes |
| SHA-256 | `77725D06515DAFFCBAAA7CFA928DDFF7D51B5B022DA8BA46A51D51547B68932E` |
| 产品文件版本 | `0.1.0-alpha.1` |

这是单个 Windows 可执行文件，不是安装器。可用资源管理器直接启动。该产物在提交 `32c8eee` 后由 `npm run desktop:build` 构建，退出码 0；当前工作树 `npm run check:local` 也退出码 0（28 Node UI、116 Rust、145 Python tests）。GitHub Actions run `40876095509` 对提交 `32c8eee` 的 `npm run check:local` 通过，用时 11m42s。该 workflow 不启动 Tauri 窗口；托盘菜单、窗口像素与 Windows 原生行为仍须按下方清单验收。

提交前的同一源码工作树曾用 Computer Use 启动独立 release，并以合成 Agent Activity snapshot 验证会话卡片的名称、状态、项目和输出字段；随后从已提交的 `32c8eee` 重建了本指南所列 EXE。最终这份 hash 尚未重新做像素验收，且真实 Codex App connector snapshot 尚未进入 release Provider；不要把合成字段 smoke 计作真实会话接入。

## 快速启动

1. 打开 `target/release/wincraft-desktop.exe`。普通启动预期只有托盘图标，不自动打开业务窗口。
2. 从 WinCraft 托盘菜单打开“世界管理器”。多次点击应聚焦同一个管理器实例。
3. 在管理器中新建空白世界；需要自动打开管理器时，可使用可选参数 `--open-manager`。这个参数是本机联调用入口，不代表默认启动行为。
4. 从管理器复制它显示的 runtime descriptor 路径给本机 Python 示例，例如：

   ```powershell
   python examples/python/focus_demo.py --runtime "<管理器显示的 runtime descriptor 路径>"
   ```

   descriptor 只在本机使用，不要复制到聊天、截图或提交记录。

5. 完成后从托盘选择“退出”。检查本次宿主进程退出、本次 descriptor 清理；不要结束其他应用的 WebView2 进程，也不要批量删除旧 runtime 文件。

## 人工验收清单

每项填写 `PASS`、`FAIL`、`BLOCKED` 或 `NOT_RUN`。失败时记录步骤、现象、Windows 缩放比例/显示器数，并附遮蔽本机路径和用户内容的截图。

| 检查 | 预期结果 | 结果 |
|---|---|---|
| 托盘启动与退出（W01） | 默认仅托盘；托盘打开管理器；最后关闭业务窗口后宿主仍运行；托盘“退出”正常结束宿主并清理本次 descriptor。 | ____ |
| 管理器复用（W02/W13） | 再次打开聚焦同一个管理器；隐藏的管理器可重新呈现；关闭普通世界与管理器遵循各自语义。 | ____ |
| 动态组件与动作回执（W04/W05/W06） | 在 Python focus demo 中点击“替换组件区”和一个按钮；结构实时更新，动作显示当前 provider 的实际回执；provider 断线不冒充成功。 | ____ |
| 自动尺寸与文本（W07/W15） | 调宽/调窄 Obsidian Workspace 或 TrafficMonitor；高度随内容布局收敛；长中文/长无空格文本在组件内换行；底部和右侧默认无窗口级滚动条。 | ____ |
| 折叠、拖动、隐藏（W18/W20） | 折叠后窗口只剩标题栏且宽度收紧；展开恢复；标题栏隐藏时普通背景仍可拖动；隐藏后可从管理器恢复同一 world。 | ____ |
| Agent Activity 会话卡片（B08-02/B08-03） | Codex App/CLI/Claude 来源卡片显示名称、状态、项目和来源文本；只有 Codex App `agent_message` 标为最近 Agent 输出，CLI 发言方未知的 preview 单独标识。当前真实 Codex App connector snapshot 仍 `BLOCKED`；不得用合成行替代真实会话验收。 | 合成 UIA：PASS；真实 Codex App：BLOCKED |
| 置顶与透明度（W12） | 默认置顶且默认透明度 80%；普通窗口不能覆盖；另一个置顶窗口遵循 Windows z-order；provider 配置后实际效果可见。 | ____ |
| 点击穿透救援（W09） | 启用穿透后仍能从托盘/管理器救援；窗口恢复可点击、可见、在屏幕内；旧写者失权。 | ____ |
| 多屏与缩放（W11/W28） | 在不同 DPI、负坐标副屏和显示器拔插后检查位置/尺寸，窗口仍可找回。 | ____ |
| Windows 虚拟桌面 | “显示在所有桌面”当前尚未实现；记录为 `NOT_IMPLEMENTED`，不能把无效果的开关算作通过。 | NOT_IMPLEMENTED |

完整分层用例见 [`docs/engineering/ACCEPTANCE.md`](../engineering/ACCEPTANCE.md)。当前源码的真实 Tauri-hosted `lease_probe.py` 共 41 项通过，B07-02 scope probe 也通过；这些探针不替代托盘点击、像素布局、真实 z-order、穿透救援及多显示器人工操作。Codex App connector 的真实快照尚未稳定送入 live Provider；该来源在无 Agent 桥接时显示“等待 Agent 桥接”，合成桥接样例不作为真实会话验收。

## 记录与复现

本次构建命令为 `npm run desktop:build`，产物位于 Cargo target release 目录。逐命令退出码、工具版本和脱敏探针结果保存在默认忽略的 `evidence/local/nextgen-2026-10-29/`。不要把 `.runtime.json`、令牌、Obsidian 笔记或 TrafficMonitor 遥测写入提交。
