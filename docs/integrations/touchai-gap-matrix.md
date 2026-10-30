---
title: TouchAI 窄用例差异矩阵
updated_at: 2026-10-30
last_verified_at: 2026-10-30
protocol_baseline: 0.3
status: source-reviewed-integration-blocked
audience: maintainer, provider-author
---

# TouchAI 窄用例差异矩阵

这是交接包 B04-04 的差异矩阵。用户指定的本机 TouchAI 检出为 `<touchai-checkout>`，本次只读核对固定 commit `cdc9b399d0ea6813be321b6a87e39d3532d1a7da`（`main`，工作树干净）、运行栈与相关源码；没有启动 TouchAI、打开用户会话或改动 TouchAI 文件。当前已知源码流程可以指导一个窄适配，但没有发现可供外部 Provider 调用的稳定 TouchAI bridge/API；真实来源返回与运行行为仍未实测，因此不宣称已接入或功能等价。

## 已核对的源码与权限边界

| 主题 | TouchAI 本机证据 | 对 WinCraft 的含义 |
|---|---|---|
| 运行栈与版本 | 根 `package.json`：`touchai-monorepo`，pnpm workspace；`apps/desktop/package.json`：`@touchai/desktop` 1.2.2、Vue 3、Tauri 2；Rust 依赖含 `tauri-plugin-global-shortcut` 2.3.2。 | 可以借鉴其 Tauri 搜索窗口与短流程设计；不能据此推断它暴露了可直接调用的集成 API。 |
| 召回与焦点 | `apps/desktop/src/stores/setting/general.ts` 默认快捷键为 `Alt+Space`；`apps/desktop/src-tauri/src/core/system/shortcut.rs` 注册系统快捷键；`useSearchPage.ts` 在激活后聚焦输入、加载模型、同步置顶与高度，快捷键路径还会执行来源自己的 auto-paste 处理。 | WinCraft 已有窗口级 `manager.show` 热键，不等于 TouchAI 搜索窗口召回、自动粘贴或焦点语义。首个候选闭环应显式区分这些动作。 |
| 输入与请求 | `apps/desktop/src/views/SearchView/composables/useSearchRequest.ts` 将文本、附件、input snapshot、模型和 provider 选择传给 `useAgent.sendRequest`；`apps/desktop/src/composables/agent/useAgent.ts` 以 `sessionTaskCenter.startTask` 启动前台任务。 | WinCraft 可以呈现声明式输入与 Provider 回执，但目前没有 TouchAI 任务/会话适配器；不能把一次按钮事件冒充完成模型请求。 |
| 流式与取消 | `useAgent.ts` 的启动阶段使用 `AbortController`；任务已创建后委托 `sessionTaskCenter.cancelTask`。 | 取消属于 TouchAI 任务所有者；WinCraft Provider 只能传递明确动作和观察到的结果，不能自行结束 TouchAI 任务或伪造取消成功。 |
| 上下文与工具 | README 声明文件/屏幕/剪贴板上下文与 MCP 工具；TouchAI 代码的 AgentService 与 built-in tools 管理这些能力。 | 文件、屏幕、剪贴板、MCP 与工具执行留在 TouchAI；WinCraft 不复制其上下文抓取或直接调用其内部数据库。 |
| 许可与修改权限 | 根 `COPYING` 与 package manifest 声明 GPL-3.0-or-later；`docs/legal/contributor-license-agreement.md` 约束提交到 TouchAI 的贡献。TouchAI 的 product rules 要求 DB schema 变更先取得用户明确批准，AgentService/对话运行时属于 RFC-first 高风险区。 | 本次只记录行为与边界，没有复制 TouchAI 源码进 WinCraft，也没有修改或执行 TouchAI。后续代码必须由独立 WinCraft Provider/应用持有，并先完成许可兼容和运行授权审查。 |

本次执行 `rg` 的静态检索范围覆盖 `apps/desktop/src`、`apps/desktop/src-tauri/src`、`packages/shared` 与 `docs`，未找到 TouchAI 到 WinCraft 的现成 bridge/native-messaging adapter。该检索不替代运行时或许可证审查。

| 能力 | WinCraft 当前证据 | TouchAI 来源核对 | 状态 |
|---|---|---|---|
| 召回入口 | shortcut intent registry 已有 session 冲突/撤销回归；真实 OS hotkey 未验收 | `general.ts` 默认 `Alt+Space`；原生 shortcut 触发 SearchView，恢复输入焦点、模型与窗口测量；快捷键路径还会自动粘贴 | partial |
| 文本输入 | `input`/`textarea`、草稿、Ctrl+Enter 能力门和 Rust 回归 | SearchBar 经 `handleSubmit` 传入文本、附件、input snapshot、model/provider；WinCraft 可呈现声明式输入，但无真实 TouchAI request adapter | partial |
| 来源返回结果 | Provider 自有 scene/data/action 回执；Popup/focus demo 使用合成业务 | `useAgent.sendRequest` 通过 `sessionTaskCenter.startTask` 发起前台会话并观察完成结果；需独立 Provider/协议才能回传真实结果 | missing |
| 流式输出 | 通用 snapshot/data 更新可承载投影；未接 TouchAI 流 | TouchAI 的任务与流式生命周期由 AgentService/TaskCenter 管理；WinCraft 没有等价的源任务流接口 | missing |
| 取消/错误 | action pending/ok/error/timeout、断线 unknown 已验证 | TouchAI 在 task start 阶段通过 `AbortController` 取消，已启动任务通过 `cancelTask` 终止；WinCraft 不能替 TouchAI 作成功/取消裁决 | partial |
| 选区/文件/屏幕上下文 | Host 不读取文件、剪贴板或屏幕；权限边界明确 | 属于 TouchAI/来源提供者，不能复制进 Host | missing by design |
| 工具执行 | Host 只执行登记的有限 native action；不接 shell/任意代码 | TouchAI 工具和授权需独立核验 | missing by design |
| 模型切换 | 不属于 WinCraft Core；Provider 可自行维护业务状态 | 需要 TouchAI 运行时/模型配置证据 | missing |
| 回到来源窗口 | Obsidian/TrafficMonitor allowlist action 已实现，真实点击仍 NOT_RUN | 需要确认 TouchAI 来源窗口身份与激活语义 | partial |
| 主题 | 有限 theme tokens、可信 chrome 和能力门 | TouchAI 主题只能作为来源数据，不能覆盖 Host 权限区 | partial |
| 关闭/隐藏 | world visible、托盘全局 hide/show、manager rescue 已有自动回归；真实 UI 未验 | 需要 TouchAI 关闭/隐藏语义 | partial |

## 当前最小闭环

若未来要接入 TouchAI，需先由用户明确允许运行当前实例并指定不触碰真实历史数据的测试上下文，再定义独立 Provider contract；首个候选只实现只读/人工确认的：

```text
召回 → WinCraft 临时世界 → 文本输入 → Provider 返回结果 → 用户确认 → 隐藏/关闭
```

模型调用、文件/屏幕/剪贴板、工具执行和播放/系统操作继续留在 TouchAI 或来源提供者；WinCraft 只承载声明式界面、租约、动作回执和已登记的宿主能力。

## 阻塞条件与验收

- **BLOCKED（仅真实闭环）**：源代码/版本/许可与召唤→输入→任务返回→取消的静态路径已核对，但本轮授权只覆盖只读学习；没有获准的 TouchAI 运行时/测试账号，也没有可供 WinCraft Provider 使用的稳定 adapter contract。不得启动 TouchAI、调用模型、读写会话/数据库，或复制 GPL 源码来填补接口缺口。
- **NOT_RUN**：真实 TouchAI 召回、文本提交、流式、取消、来源返回和回到来源窗口。
- **不得宣称等价**：出现输入框、主题相似或热键意图层通过，都不能证明 TouchAI 功能迁移完成。
