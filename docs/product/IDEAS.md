# 后续产品想法

此页记录尚未排期、未形成接口承诺的候选想法。进入实现前仍需检查来源 API、权限、协议能力和可验收性。

## TeamSense 只读状态卡

**状态：用户提出方向 / NOT_PLANNED。** 额度悬浮窗尚未实现、排期或连接真实数据源；这不是当前窗口修复或阶段性交付的范围。

### 目标

评估把 TeamSense 的关键摘要放进 WinCraft 悬浮窗，作为随时可见的轻量入口。候选首屏包括 Codex、MiniMax、DeepSeek 的额度余量/周期/重置时间，以及必要的服务器健康摘要；视觉上可用服务卡片、数值和有来源依据的进度条快速对比。只有来源明确给出同一额度窗口的单位与分母时才画百分比；数据必须带来源、采样时间、单位与陈旧状态。源码核对发现 TeamSense Agent 只读接口已有 DeepSeek、MiniMax 与 Sub2API 缓存摘要，但不包含 Codex；Codex 读取需要另行确认只读授权边界。先用授权汇总做小原型；当前不假设 Codex 端点或字段已存在。

### TeamSense 本地采集器源码复核（2026-10-30）

- Codex 历史用量库增量读取 `CODEX_HOME` 下的 `sessions/`、`archived_sessions/` JSONL 与 `state_*.sqlite` 元数据；从本机 `token_count` 事件提取用量及其中的 `rate_limits.primary` 快照，不连接或启动 Codex App，也不读取 `auth.json`。
- TeamSense 桌面 collector 另有独立的可选实时额度查询；默认关闭并单独授权。其提供商识别逻辑会有界读取 `auth.json` 来判定配置类型，所以不能把 TeamSense 的所有额度来源都描述为纯磁盘历史解析。WinCraft 仍只接收 TeamSense 授权后的脱敏汇总，不复制这条凭据路径。
- TeamSense Agent 只读 API 的 `GET /v1/integrations/models` 从缓存返回 DeepSeek balance、MiniMax quota、Sub2API 管理摘要及各自的 `meta`；设计说明规定普通 GET 不访问上游。Codex 的 `/api/codex/usage` 位于既有 `/api` 身份边界，不在 Agent 只读 token 契约中，因此不能直接当成可用的 Provider endpoint。
- 额度快照与进程在线状态是不同数据：进程用于判断来源是否运行；本机历史/最近快照可在进程退出后继续展示，并需保留采样时间与 stale 状态。MiniMax、DeepSeek 的权威额度来源、窗口口径与刷新方式仍待逐个核验；token 用量或估算费用不能冒充真实额度余量。
- 本轮只完成源码核验与设计记录，没有调用 TeamSense Agent API、供应商额度 API、读取用户凭据或连接真实数据。

### 责任边界

- TeamSense 保留业务真相、来源授权和凭据管理；WinCraft 只消费提供者整理后的显示摘要。
- 提供者优先经由获准且有文档的 TeamSense 汇总接口读取。不得让 WinCraft Host 持有 TeamSense/供应商密钥、读取 `auth.json`、借用 ChatGPT 凭据或把原始日志/账户标识送入场景；若 TeamSense 的本机汇总尚无合适接口，需先单独设计本地只读桥接与授权。
- 首个原型只显示信息，不触发额度管理、服务控制或其他业务写入。
- WinCraft 侧使用协议 0.3 的声明式组件和数据绑定（例如 `Metric`、`Badge`、`Progress`、`Text`）；不注入 HTML、JavaScript、CSS 或任意代码。它们只是现有渲染原语，不是新业务组件承诺。

### 候选显示契约（待验证，不是已接受 schema）

```json
{
  "source": "teamsense",
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

1. 先从 TeamSense 源码和官方/项目内文档核实一条获准的读取路径、授权归属、数据单位、时间窗口和错误语义；若只能依赖私有网页接口或读取凭据文件，则停止该路线。
2. 用本地合成 fixture 验证正常、真实零、陈旧、来源失败与未接入的显示差异；fixture 不能标成真实 TeamSense 联调。
3. 若来源读 API 与权限都已明确，再单独授权只读 live 联调。验证凭据不进入 scene、宿主日志、截图或仓库；更新失败时保留最后一次有效值并标记陈旧，不能用 `0` 代替。
4. 由用户确认这个摘要能否帮助完成当前任务，再决定是否排期、扩字段或加入操作入口。

### 进入开发前的缺项

TeamSense 可用读取 API 与认证方式、字段来源和刷新语义、允许显示的数据范围、第一张卡的明确选择，以及真实数据与 fixture 的隔离方式。目前均为 `NOT_RUN`，没有实现或连接状态。
