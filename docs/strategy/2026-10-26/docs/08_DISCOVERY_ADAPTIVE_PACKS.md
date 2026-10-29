---
{
  "doc_id": "docs__08_DISCOVERY_ADAPTIVE_PACKS",
  "title": "自发现、自适应配置与整合包",
  "updated_at": "2026-10-30",
  "last_verified_at": "2026-10-30",
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

本包示范的 Python planner 是纯输入→输出规划函数，只接收显式提供的 inventory/pack 并输出计划，不读设备、不联网、不启动程序。当前 `.wcp` 运行时导入器把 adapter 字段当作不执行的外部声明；任何未来 adapter 执行能力都必须位于独立执行层并另行授权，不能由打开/导入 pack 隐式触发。

后续允许包引用/附带自定义适配代码，但必须在独立执行层：明确作者、内容哈希、权限、输入输出 schema、时间/内存限制和撤销方式；打开包不等于执行代码。不能把 adapter 脚本当主题 CSS、前端 JS 或宿主 Mod 注入。没有可靠沙箱时如实标记“受信任外部程序”，不可宣传已安全隔离。

## 依赖与迁移

声明宿主格式、必须能力、可选能力、适配器接口版本和资源哈希；配置锁文件锁的是配置/资源与匹配证据，不承诺在线服务仍可用。Provider 软件升级由其自己的生命周期管理，包最多给说明或供用户主动安装的链接。

导出必须剥离 token、lease、session、host UUID、设备路径、账户、真实通知/笔记、已授权能力和不可移植坐标；允许用户显式保存非敏感偏好。先导出匿名绑定占位，再在目标环境重新选择来源。旧格式迁移先计划/预览，保留原包和回退副本。

示例见 `examples/packs/`；格式见 `contracts/pack.schema.json`。本机 draft exporter 的使用说明位于仓库根目录 `tools/pack/README.md`：它只校验并导出 pack JSON 与引用的 blueprint JSON，不含 Provider 二进制、descriptor、lease 或安装逻辑，也不连接 Host。导出器本身不执行 import/apply；WinCraft 的本地管理器另有用户确认的导入流程，但该提案仍不是 protocol 0.3 接口。

## 当前 0.3 世界发现边界

现有 `world.list` 不是完整 Provider inventory。它只返回当前 session 已加入的世界和显式 `open_authenticated` 的非系统世界；未加入的 invite-only 世界不暴露元数据。列表不会返回 token、lease 或 scene，加入与读取仍需独立调用 `world.join`。core/headless 验证覆盖同名实例身份、online/stale/vacant 状态以及 unauthorized invite 的拒绝。

Provider 类型、版本、能力声明、grants 与 freshness 的 inventory 仍是 draft 契约，未加入稳定线协议 0.3。B01-03 已以 `0.4-preview.1` 可选 capability 提供 endpoint-local register/list：只收已认证连接显式注册的有限元数据，Provider 不能提交自授 grants；未获本机批准时 grants 为空。`source_instance_id` 在一个 endpoint 内唯一，以便计划无歧义地回到注册 session。每个响应保留 `endpoint_id`，调用者要组合多个 endpoint 时必须逐个选定并鉴权；Host 不扫描进程、浏览器账户或网络。清单与注册本身不授予加入世界、读取业务快照或执行来源动作的权限。B06-03 的本机管理器可以针对一个已选提供者和当前 pack binding 明确批准已声明 capability；这会增加清单 generation、使旧预览失效，且不会跨 Host 重用。

## 2026-10-30 B06-03 本机导入实现边界

**Given** 用户选择一个通过 schema 校验的 `.wcp`，**When** 本机世界管理器显示计划，**Then** 预览只读当前 endpoint 的已授权 Provider inventory，明确列出窗口属性、来源匹配、缺失权限、清单 generation 和不超过 60 秒且不晚于来源新鲜度的有效期；它不创建窗口、不接入提供者，也不执行 adapter。

**When** 用户单独批准某个候选提供者声明过的缺失 capability，**Then** Host 更新当前内存内的 host grant、增加 inventory generation、使旧预览失效，并重新计算计划。发现或提供者自报永远不会生成 grant。

**When** 用户再次确认 Ready 或 Degraded 计划，**Then** Host 在内存中创建新的 Blueprint worlds；选定的 Provider 必须显式声明 `world.import.accept`，并先在 SDK 中调用 `client.require_provider_import(version=1)`。用户确认后，Host 才向该 session 定向发送 `world.import.joined` 和该窗口的 exclusive writer lease。事件采用 [`provider-import-event.schema.json`](../contracts/provider-import-event.schema.json)。一个窗口不能同时自动附着两个不同 writer；冲突阻塞计划。可选绑定缺失时，`explain_missing` 显示说明，`hide_optional` 只对单绑定蓝图世界隐藏整个窗口。业务数据、Scene.data、原机坐标、token、lease、session 及 adapter 二进制不会写入配置包。

取消预览不会触碰既有世界。提交失败时 Host 仅回收本次创建且仍未改动/加入的窗口并报告清理结果；已被用户或 Provider 修改、接入或接管的窗口会保留。回退按导入账本和当前 revision/epoch/window/scene/membership 核对，不能复原或覆盖后续用户修改。原生多窗口创建按窗口各自应用，未提供 OS 级事务原子性保证。

这是本机管理器实现，不是 protocol 0.3 的新方法。B06-03 的 Rust Host/manager 行为测试通过 L1–L2；当前 release 的真实 Tauri SDK hello/capability handshake 只证明 Host 宣告 `provider_import` 契约，不证明实际导入。Computer Use 两次读取 Manager 窗口状态均遇到 `GetCursorPos` 访问被拒绝，未发送 UI 输入；原生预览、授权重规划、apply、逐窗失败与恢复仍为 NOT_RUN，因此 B06-03 继续标 `IMPLEMENTED_UNVERIFIED`/PARTIAL。Host grants 与导入账本仅在运行期间保留，重启不重建旧计划。B06-04 的四类合成 inventory 与 `.wcp` 静态包检查已完成；两个独立用户环境的重新授权仍 NOT_RUN。
