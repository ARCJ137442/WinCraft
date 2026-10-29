---
{
  "doc_id": "docs__08_DISCOVERY_ADAPTIVE_PACKS",
  "title": "自发现、自适应配置与整合包",
  "updated_at": "2026-10-29",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "proposal",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 自发现、自适应配置与整合包

## 用户决定

整合包主要封存配置，不适合也不保证封存提供者。用户可以附带适配程序，根据当前设备、来源与偏好制定配置。它像一张会根据参与者调整的地图，而不是整台电脑的镜像。[U-LATEST]

## 五类对象分开

| 对象 | 保存什么 | 不保存什么 |
|---|---|---|
| Blueprint | 组件/布局/主题引用 | 业务记录、活跃 lease |
| Recipe | 能力要求、绑定和行为策略 | 固定服务器密钥、私有 Cookie |
| Pack | 多份配置、兼容与依赖声明、资源摘要 | 提供者可执行环境的保证 |
| Environment inventory | 经授权发现的来源能力与平台状态 | 进程遍历/全盘扫描出来的隐私 |
| Resolution plan | 这次匹配、缺失、降级与待授权项 | 自动获得的授权或已执行安装 |

## 自发现不是扫描一切

本机 Provider 向 registry 注册短期身份与能力，携带实例 ID、版本、TTL、提供的状态/动作 schema、数据新鲜度和权限要求。registry 可从已授权 bridge 获取 inventory；不偷偷枚举私人 vault、浏览器 profile、运行时 token 或全部进程。跨机器发现经用户选定的隧道/配对 transport 提供，禁止无认证 LAN 广播敏感信息。

显示名不是身份；能力声明还要由授权与实际探针验证。来源 `connected` 不等于 `fresh`，未实现能力不能因名字匹配显示为可用。

## 自适应加载六步

1. 读 manifest，做结构、资源大小和路径校验；未知字段安全拒绝。
2. 取得已授权 inventory；区分必要/可选能力与 platform 限制。
3. 纯函数生成 resolution plan：已匹配、缺失、冲突、待授权和降级原因。
4. 显示变更预览；不得因缺失就自动下载、安装或申请新权限。
5. 用户接受后创建本次世界并绑定临时实例；必要配置失败则清理本次创建的资源。
6. 来源离线时保留明确 stale/offline；再次发现后按策略重新规划，不复用旧 lease。

有多个匹配时先按用户显式选择，否则稳定排序但标注候选，不能偷偷替用户选择一个更高权限来源。没有可用来源时仍可展示教程/缺失说明，不伪造业务数据。

## 适配程序的安全分级

默认 adapter 是受限声明式规则或纯输入→输出程序。本包示范的 Python planner 只接收合成 inventory/pack，输出计划，不读设备、不联网、不启动程序。

后续允许包引用/附带自定义适配代码，但必须在独立执行层：明确作者、内容哈希、权限、输入输出 schema、时间/内存限制和撤销方式；打开包不等于执行代码。不能把 adapter 脚本当主题 CSS、前端 JS 或宿主 Mod 注入。没有可靠沙箱时如实标记“受信任外部程序”，不可宣传已安全隔离。

## 依赖与迁移

声明宿主格式、必须能力、可选能力、适配器接口版本和资源哈希；配置锁文件锁的是配置/资源与匹配证据，不承诺在线服务仍可用。Provider 软件升级由其自己的生命周期管理，包最多给说明或供用户主动安装的链接。

导出必须剥离 token、lease、session、host UUID、设备路径、账户、真实通知/笔记、已授权能力和不可移植坐标；允许用户显式保存非敏感偏好。先导出匿名绑定占位，再在目标环境重新选择来源。旧格式迁移先计划/预览，保留原包和回退副本。

示例见 `examples/packs/`；格式见 `contracts/pack.schema.json`，均是提案而不是现有导入能力。

## 当前 0.3 世界发现边界

现有 `world.list` 不是完整 Provider inventory。它只返回当前 session 已加入的世界和显式 `open_authenticated` 的非系统世界；未加入的 invite-only 世界不暴露元数据。列表不会返回 token、lease 或 scene，加入与读取仍需独立调用 `world.join`。core/headless 验证覆盖同名实例身份、online/stale/vacant 状态以及 unauthorized invite 的拒绝。

Provider 类型、版本、能力声明、grants 与 freshness 的 inventory 仍是 draft 契约，未加入稳定线协议 0.3。B01-03 已以 `0.4-preview.1` 可选 capability 提供 endpoint-local register/list：只收已认证连接显式注册的有限元数据，Host 不接收自授 grants，返回的 grants 固定为空；stable `world.list` 仍只列 world。每个响应保留 `endpoint_id`，调用者要组合多个 endpoint 时必须逐个选定并鉴权；Host 不扫描进程、浏览器账户或网络。该 API 不授予加入世界、读取业务快照或执行来源动作的权限。整合包 planner 继续只消费经授权的 inventory 快照，不把发现结果当作批准或执行权限。
