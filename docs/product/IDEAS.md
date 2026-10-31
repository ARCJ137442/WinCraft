# 后续产品想法

此页记录尚未排期或尚未形成稳定接口承诺的方向，也保留已进入原型但仍未完成验收的开放门槛。进入实现前仍需检查来源 API、权限、协议能力和可验收性。

## 模型额度 HUD（本机来源适配）

**状态：用户提出方向 / prototype implemented / `IMPLEMENTED_UNVERIFIED`。** 额度 HUD 和只读 Provider 已实现；TeamSense 只作为采集实现的源码参考，不是 WinCraft 服务依赖，也不需要 `data:read` token。合成测试与 release headless Host smoke 已通过；真实用户来源和原生窗口像素仍为 `NOT_RUN`。

### 目标

把模型额度摘要放进 WinCraft 悬浮窗，作为随时可见的轻量入口。当前 Provider 展示 Codex、DeepSeek、MiniMax，各来源、币种、模型窗口、重置时间和新鲜度分别呈现。Codex rollout 模式只读有界 `event_msg.token_count.rate_limits` 字段；DeepSeek/MiniMax 固定 vendor GET 需显式启用且读取本机环境 key；Codex live backend GET 是另一个默认关闭的实验来源。只有来源明确给出百分比或可靠分子/分母时才画进度条；缺字段保持 unknown，不推算账户或剩余额度。运行入口见 [`examples/integrations/model_quota/README.md`](../../examples/integrations/model_quota/README.md)。

### TeamSense 本地采集器源码复核（历史记录：2026-10-30）

- Codex 历史用量库增量读取 `CODEX_HOME` 下的 `sessions/`、`archived_sessions/` JSONL 与 `state_*.sqlite` 元数据；从本机 `token_count` 事件提取用量及其中的 `rate_limits.primary` 快照，不连接或启动 Codex App，也不读取 `auth.json`。
- TeamSense 桌面 collector 另有独立的可选实时额度查询；默认关闭并单独授权。其提供商识别逻辑会有界读取 `auth.json` 来判定配置类型，所以不能把 TeamSense 的所有额度来源都描述为纯磁盘历史解析。2026-10-30 的 WinCraft 实现仍只接收 TeamSense 授权后的脱敏汇总，不复制这条凭据路径；2026-10-31 后续原型另加了独立、默认关闭的 Codex 实验源，见下方现行责任边界。
- TeamSense Agent 只读 API 的 `GET /v1/integrations/models` 从缓存返回 DeepSeek balance、MiniMax quota、Sub2API 管理摘要及各自的 `meta`；设计说明规定普通 GET 不访问上游。Codex 的 `/api/codex/usage` 位于既有 `/api` 身份边界，不在 Agent 只读 token 契约中，因此不能直接当成可用的 Provider endpoint。
- 额度快照与进程在线状态是不同数据：进程用于判断来源是否运行；本机历史/最近快照可在进程退出后继续展示，并需保留采样时间与 stale 状态。MiniMax、DeepSeek 的权威额度来源、窗口口径与刷新方式仍待逐个核验；token 用量或估算费用不能冒充真实额度余量。
- 2026-10-30 源码复核当时只完成设计记录，没有调用 TeamSense Agent API、供应商额度 API、读取用户凭据或连接真实数据。后续实现的合成验证也没有读取真实凭据或连接真实数据。2026-10-31 起，WinCraft 的数据源方案改为本机 Codex rollout + opt-in 的供应商 adapter，不调用 TeamSense cache API。

### 责任边界

- TeamSense 本身不是 WinCraft 的数据源；它的 rollout reader 与 provider adapters 仅供学习。WinCraft 不读取 TeamSense token，不请求其缓存接口、dashboard、admin 或刷新路由。
- Codex rollout source 由 Provider 在显式 `--codex-rollout-quota` 后扫描有界本机日志尾部，只投影 quota 事件，不访问 Codex App、auth.json、SQLite 或会话正文。快照来自事件时间，不代表实时 App 通信。
- Codex live quota 是另一条默认关闭的本机凭据适配器，只能在用户传入 `--codex-quota` 后使用本机 `auth.json` 中必要字段；Host 不读凭据。不得使用或保存 refresh token、刷新登录、写回或上传凭据、显示账户 ID、把令牌或账户 ID写入日志/证据/场景；请求期间账号切换或身份无法确认时清掉旧读数。ChatGPT backend route 未公开为稳定 API，若响应/授权改变就报未知或失败，不绕过登录或改走浏览器 Cookie。
- DeepSeek/MiniMax 各自使用固定供应商 HTTPS GET；只有用户显式启用并在本机提供对应 API key 才请求。key 只用于内存请求，不进入 scene、日志或 evidence；拒绝重定向并限制超时和响应大小。
- 首个原型只显示信息，不触发额度管理、服务控制或其他业务写入。
- WinCraft 侧使用协议 0.3 的声明式组件和数据绑定（例如 `Metric`、`Badge`、`Progress`、`Text`）；不注入 HTML、JavaScript、CSS 或任意代码。它们只是现有渲染原语，不是新业务组件承诺。

### 候选显示契约（待验证，不是已接受 schema）

```json
{
  "source": "codex_rollout",
  "metric_id": "quota_remaining",
  "value": 42,
  "unit": "requests",
  "window": {
    "starts_at": "2026-10-28T00:00:00Z",
    "ends_at": "2026-10-28T12:00:00Z",
    "resets_at": "2026-10-28T12:00:00Z"
  },
  "observed_at": "2026-10-28T10:30:00Z",
  "freshness": "fresh"
}
```

真实契约需按选定来源定义类型。健康卡应使用有界状态枚举而不是伪造数值；失败、陈旧、未接入和真实零必须可区分。没有可核对来源与观测时间时，不得显示为当前值。

### 最小可验收原型

1. 当前合成回归覆盖各来源边界与 freshness；Codex rollout 使用合成事件，不读真实用户日志。Codex live endpoint 保持 opt-in 实验状态。
2. 用本地合成 fixture 验证真实零、缺失、陈旧、来源失败、账号切换与未接入的显示差异；fixture 不得标成真实账户联调。
3. 对实时读数单独记录来源时间与错误状态；检查凭据不进入 scene、Host、日志、截图或仓库；更新失败时保留同一账号的最近成功值，身份不明时清除，不把未知替换为 `0`。
4. 原生截图与真实账号 freshness 仍需后续验证；首个额度 HUD 不执行额度修改或服务控制。后续来源增删与 key/login 配置属于本机数据源管理，不等于上游业务写操作。

### 进入真实日常使用前的缺项

仍待验证：真实 Codex rollout freshness、DeepSeek/MiniMax key/API 返回口径与账户归属、可配置额度窗口的当前 Windows 原生像素。自动化回归使用合成 auth/HTTP 不代表真实来源已经联调。

## 提供者手动启动体验（已实现，待原生实测）

- `examples/launchers/start-model-quota.cmd` 双击后询问 runtime descriptor 路径并打开来源选择器；Obsidian 通用 Provider 有独立双击配置窗口。真实双击流程仍需人工验收。
- 世界管理器的连接描述文件旁有“复制路径”按钮；仅内部管理器可触发 Host clipboard command，复制路径、不复制文件内容或 bearer token。原生剪贴板点击仍需实测。
- 模型额度视图支持本机来源增删；未配置的供应商来源显示 API Key CTA，未选来源不显示“未启用/无缓存”。当前没有 Mimo 等账号登录 adapter；不显示未实现来源的假入口。API Key 输入为遮蔽 UI、仅在 Provider 进程内存中使用、不写入设置文件或 scene。
