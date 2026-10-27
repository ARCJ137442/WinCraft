---
title: TouchAI 窄用例差异矩阵
updated_at: 2026-10-27
last_verified_at: 2026-10-27
protocol_baseline: 0.3
status: blocked-external-source
audience: maintainer, provider-author
---

# TouchAI 窄用例差异矩阵

这是交接包 B04-04 的待决材料。当前本机只核对了 TouchAI README 参考，没有获得目标仓库的固定 commit、运行时、配置或许可证授权。因此矩阵描述 WinCraft 已实测能力与待核对能力，不声称 TouchAI 已接入或功能等价。

| 能力 | WinCraft 当前证据 | TouchAI 来源核对 | 状态 |
|---|---|---|---|
| 召回入口 | shortcut intent registry 已有 session 冲突/撤销回归；真实 OS hotkey 未注册 | 需要确认目标仓库、快捷键和用户改绑规则 | partial |
| 文本输入 | `input`/`textarea`、草稿、Ctrl+Enter 能力门和 Rust 回归 | 需要确认 TouchAI 输入法、取消和提交语义 | partial |
| 来源返回结果 | Provider 自有 scene/data/action 回执；Popup/focus demo 使用合成业务 | 需要真实 TouchAI adapter 和来源回执 | missing |
| 流式输出 | 通用 snapshot/data 更新可承载投影；未接 TouchAI 流 | 需要确认流式协议、取消和背压 | missing |
| 取消/错误 | action pending/ok/error/timeout、断线 unknown 已验证 | 需要来源错误和取消契约 | partial |
| 选区/文件/屏幕上下文 | Host 不读取文件、剪贴板或屏幕；权限边界明确 | 属于 TouchAI/来源提供者，不能复制进 Host | missing by design |
| 工具执行 | Host 只执行登记的有限 native action；不接 shell/任意代码 | TouchAI 工具和授权需独立核验 | missing by design |
| 模型切换 | 不属于 WinCraft Core；Provider 可自行维护业务状态 | 需要 TouchAI 运行时/模型配置证据 | missing |
| 回到来源窗口 | Obsidian/TrafficMonitor allowlist action 已实现，真实点击仍 NOT_RUN | 需要确认 TouchAI 来源窗口身份与激活语义 | partial |
| 主题 | 有限 theme tokens、可信 chrome 和能力门 | TouchAI 主题只能作为来源数据，不能覆盖 Host 权限区 | partial |
| 关闭/隐藏 | world visible、托盘全局 hide/show、manager rescue 已有自动回归；真实 UI 未验 | 需要 TouchAI 关闭/隐藏语义 | partial |

## 当前最小闭环

在获得明确的 TouchAI 仓库 commit、运行入口、许可证边界和用户授权后，先实现一个只读/人工确认的：

```text
召回 → WinCraft 临时世界 → 文本输入 → Provider 返回结果 → 用户确认 → 隐藏/关闭
```

模型调用、文件/屏幕/剪贴板、工具执行和播放/系统操作继续留在 TouchAI 或来源提供者；WinCraft 只承载声明式界面、租约、动作回执和已登记的宿主能力。

## 阻塞条件与验收

- **BLOCKED**：没有固定 TouchAI source/commit、运行时凭据和许可证/权限确认。
- **NOT_RUN**：真实 TouchAI 召回、文本提交、流式、取消、来源返回和回到来源窗口。
- **不得宣称等价**：出现输入框、主题相似或热键意图层通过，都不能证明 TouchAI 功能迁移完成。
