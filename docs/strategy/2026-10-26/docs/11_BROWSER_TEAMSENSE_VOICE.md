---
{
  "doc_id": "docs__11_BROWSER_TEAMSENSE_VOICE",
  "title": "浏览器、TeamSense 与一次性语音",
  "updated_at": "2026-10-31",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "proposal",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "CHROME-NATIVE",
    "W-TRANSPORT"
  ]
}
---

# 浏览器、TeamSense 与一次性语音

## 四条路线分开

| 路线 | 用途 | 代价与边界 |
|---|---|---|
| 授权语义适配 | 从 API/DOM 取得状态，变成 WinCraft 组件 | 站点升级、权限、数据新鲜度；不是任意网页无损转换 |
| 像素裁剪/观察 | 临时看既有页面区域 | 无业务语义、有限交互；只能标为视觉视图 |
| 官方 API Provider | 可靠的业务协议 | 凭据、计费和会话可能不同，不等于复用网页版订阅 |
| 重新加载网页 WebView | 原样网页 | 新登录与资源成本、隔离设计，当前默认禁用 |

优先第一和第三条；不把第四条作为默认，以免违背调用方不用提交前端及当前可信渲染器边界。

## Native Messaging 桥接

浏览器扩展使用显式授权的标签/站点，content script 只能观察用户选定范围；扩展后台经 Native Messaging 向受信任 Rust bridge 发送结构化内容；bridge 再连接现有鉴权 WS。宿主令牌只在原生侧，不发送给页面。`allowed_origins` 固定扩展身份；单独验证消息 schema、大小、来源会话和配对状态。[CHROME-NATIVE]

不得直接关闭 `transport.rs` 的 Origin 拒绝来跑通演示。bridge 也不是安全万能药：扩展更新、内容脚本权限与原生程序安装本身需要审查。[W-TRANSPORT]

浏览器休眠、标签销毁、SPA 导航、DOM 改版和扩展重启都有独立失效路径。页面原文不当指令，注入来的文本不能触发工具批准、热键或系统操作。

## TeamSense 额度采集参考

TeamSense 的本机 Codex 用量 collector 与账号额度 collector 是两条独立实现路径；它们只作为 WinCraft 的源码参考，不代表 WinCraft 要连接 TeamSense 服务，也不要求 `data:read` token。

- Codex rollout collector 只从 `sessions/` 与 `archived_sessions/` 的 JSONL `event_msg.token_count` 事件提取 quota 字段；其会话 metadata/SQLite 读取属于另一种用途。WinCraft quota HUD 只需要 `rate_limits.primary` 和可选 `secondary`，不读取正文、Codex App、`auth.json` 或 state DB。
- TeamSense 的可选 Codex live quota collector 从本机 `auth.json` 读取必要字段后调用实验性 backend GET。WinCraft 将其保留为独立默认关闭的 `--codex-quota` 路径；Codex backend route 不是稳定公开 API。
- TeamSense Worker 中的 DeepSeek/MiniMax adapters 直接调用固定 vendor HTTPS GET。WinCraft 复用这些已定位的端点和字段语义，但必须各自显式 opt-in，只从本机环境读取对应 key；不经过 TeamSense cache API。

额度字段仍须按来源、账户作用域、窗口长度、重置时间、单位、来源时间与 freshness 分开呈现。不能把各会话 token 简单相加当订阅总额度，也不能将不同模型权重与计费机制当恒定。无数据是 unknown/stale，不是零；真实限流和花费控制仍归提供者与上游。

## ChatGPT / DeepSeek 网页

“原生界面”在这里指桌面窗口中的声明式对话投影，不保证网页所有功能等价。优先公开/受支持的接口；经用户授权的页面适配器保留来源标识和原会话链接；不得绕过认证、验证码、访问限制或把登录 Cookie 导出到宿主。正式实现前复核站点政策和本地版本。

发送消息/语音转写后提交是对外动作，应显示目标站点、会话与内容，先由用户确认。读屏幕的能力不自动允许发消息或确认购买、授权。

## 系统语音

TTS 与 ASR 分开：朗读只读已选文本，录音由本地用户主动开始，有明确录音状态、时限、取消与设备失败反馈。默认不保存音频、不常驻监听、不向任意 Provider 发送音频；优先把用户确认后的文本交给来源。所选系统服务可能在线或离线，必须实测与说明，不承诺所有语言都本地可用。

业务链路：按用户快捷键 → 明确来源 → 一次录音 → 可编辑转写 → 确认发送 → 来源返回 → 可选朗读。取消途中任何一步都不得残留麦克风会话或发送半成品。
