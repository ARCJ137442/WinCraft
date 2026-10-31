# 后续产品想法

此页记录尚未排期或尚未形成稳定接口承诺的方向，也保留已进入原型但仍未完成验收的开放门槛。进入实现前仍需检查来源 API、权限、协议能力和可验收性。

## 模型额度 HUD（原 TeamSense 只读状态卡）

**状态：用户提出方向 / prototype implemented / `IMPLEMENTED_UNVERIFIED`。** 合成额度 HUD 和只读 Provider 已实现；真实 TeamSense/Codex 账户请求与当前原生窗口像素仍为 `NOT_RUN`，不把合成场景称为真实额度验收。

### 目标

把模型额度摘要放进 WinCraft 悬浮窗，作为随时可见的轻量入口。当前 Provider 可合并 TeamSense 的 DeepSeek/MiniMax 缓存投影与可选 Codex 本机读取；不同来源、币种、模型窗口、重置时间和新鲜度分别呈现。只有来源明确给出分子/分母或明确百分比时才画进度条；缺字段保持 unknown，不推算账户或剩余额度。TeamSense 的 `GET /v1/integrations/models` 不包含 Codex；Codex 仅有默认关闭的本机实验源，详情和入口见 [`examples/integrations/model_quota/README.md`](../../examples/integrations/model_quota/README.md)。

### TeamSense 本地采集器源码复核（2026-10-30）

- Codex 历史用量库增量读取 `CODEX_HOME` 下的 `sessions/`、`archived_sessions/` JSONL 与 `state_*.sqlite` 元数据；从本机 `token_count` 事件提取用量及其中的 `rate_limits.primary` 快照，不连接或启动 Codex App，也不读取 `auth.json`。
- TeamSense 桌面 collector 另有独立的可选实时额度查询；默认关闭并单独授权。其提供商识别逻辑会有界读取 `auth.json` 来判定配置类型，所以不能把 TeamSense 的所有额度来源都描述为纯磁盘历史解析。2026-10-30 的 WinCraft 实现仍只接收 TeamSense 授权后的脱敏汇总，不复制这条凭据路径；2026-10-31 后续原型另加了独立、默认关闭的 Codex 实验源，见下方现行责任边界。
- TeamSense Agent 只读 API 的 `GET /v1/integrations/models` 从缓存返回 DeepSeek balance、MiniMax quota、Sub2API 管理摘要及各自的 `meta`；设计说明规定普通 GET 不访问上游。Codex 的 `/api/codex/usage` 位于既有 `/api` 身份边界，不在 Agent 只读 token 契约中，因此不能直接当成可用的 Provider endpoint。
- 额度快照与进程在线状态是不同数据：进程用于判断来源是否运行；本机历史/最近快照可在进程退出后继续展示，并需保留采样时间与 stale 状态。MiniMax、DeepSeek 的权威额度来源、窗口口径与刷新方式仍待逐个核验；token 用量或估算费用不能冒充真实额度余量。
- 2026-10-30 源码复核当时只完成设计记录，没有调用 TeamSense Agent API、供应商额度 API、读取用户凭据或连接真实数据。后续实现的合成验证也没有读取真实凭据或连接真实数据。

### 责任边界

- TeamSense 保留业务真相、来源授权和凭据管理；WinCraft 只消费提供者整理后的显示摘要。TeamSense 来源只使用现有 `data:read` 缓存 GET，不调用 refresh、admin、供应商 API 或宽泛 dashboard。
- Codex 是另一条明确 opt-in 的本机凭据适配器，只能由 Provider 在用户传入 `--codex-quota` 后使用本机 `auth.json` 中必要的两个字段；Host 不读凭据。不得使用或保存 refresh token、刷新登录、写回或上传凭据、显示账户 ID、把令牌或账户 ID写入日志/证据/场景；请求期间账号切换或身份无法确认时清掉旧读数。ChatGPT backend route 未公开为稳定 API，若响应/授权改变就报未知或失败，不绕过登录或改走浏览器 Cookie。
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

1. TeamSense live read 仍需用户提供有效 `data:read` 凭据；Codex live read 需显式运行 `--codex-quota`，且因 endpoint 未公开而继续标作实验集成。
2. 用本地合成 fixture 验证真实零、缺失、陈旧、来源失败、账号切换与未接入的显示差异；fixture 不得标成真实账户联调。
3. 对实时读数单独记录来源时间与错误状态；检查凭据不进入 scene、Host、日志、截图或仓库；更新失败时保留同一账号的最近成功值，身份不明时清除，不把未知替换为 `0`。
4. 原生截图与真实账号 freshness 仍需后续验证；不增加额度管理、服务控制或业务写动作。

### 进入开发前的缺项

仍待验证：有效 TeamSense `data:read` token 下的真实缓存 freshness/账号范围、显式 Codex opt-in 的真实账号返回口径与接口稳定性、当前 Windows 原生窗口像素。自动化回归使用合成 auth/HTTP 并不代表这些项目已 PASS。
