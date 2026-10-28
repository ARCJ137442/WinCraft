# ADR-0004：通过显式 preview 协商子树租约

状态：Agent 实施取舍，限定在本地 preview；稳定协议采纳尚未裁决。日期：2026-10-28。

## 背景

用户已决定先使用窗口级独占写租约与不可变快照读者，再逐步扩展到组件子树和有类型的数据命名空间。当前稳定线协议为严格 `0.3`，其中 `component_leases=false`；未知结构会被拒绝。交接包把 `scope.claim` 等方法列为设计族，明确它们还不是可调用的 `0.3` API。

直接在 `0.3` 的世界租约上附加节点 ID 会留下两个危险漏洞：旧 `scene.replace` 可能覆盖其他子树；全世界快照会把其他提供者的数据泄露给只拥有一个子树的会话。

## 决定

1. `0.3` 保持现有整窗独占语义。采用组件租约的客户端必须在 hello 中显式协商精确版本 `0.4-preview.1`；不支持时 SDK 在发送 scope 写请求前失败关闭。preview 不代表稳定 `0.4` 或对旧 `0.3` 的追认。
2. 整窗租约只能通过一次原子 `scope.partition` 转为 scoped 模式。转换时必须校验当前 lease、world revision、唯一拥有者、组件根节点不相交及数据命名空间不相交；旧整窗 lease 立即 fencing。不得同时保留可改动同一场景的整窗 writer 与子树 writer。
3. 转换结果有独立的 root/world authority 和每个子树 scope。Scope 身份使用宿主生成的 `scope_id`，并带 `generation`、局部 `revision`、单一 writer lease 与可撤销邀请凭证。窗口属性属于 root authority；不能由子树 lease 派生。
4. Scope 读请求只返回该 scope 的根节点及其数据命名空间。普通 `world.snapshot` 对 scoped world 的外部会话失败关闭；只有可信本地操作员能读取用于渲染的完整聚合快照。
5. `scope.patch` 在 B07-01 只接受作用于本 scope 现有节点的属性更新，并以 `scope_revision` 检查冲突；`scope.data.replace` 只能替换本 scope 的命名空间。跨 scope 插入、删除、替换、移动、父级撤销与在途动作清理留给 B07-02 的结构事务。
6. Root authority 只管理布局边界、子 scope 授权及窗口 authority，不把子提供者的业务数据变成自己的权威事实。退出、过期、撤销与本机接管会撤销对应 scope lease 并推进 fencing generation/epoch。

## 影响与回滚

- 未加入 preview 的连接继续使用现有 `world.*` / `scene.*` 0.3 行为；不悄悄忽略未知字段，也不自动回退版本。
- Composition world 不能静默降级成整窗 writer。要回到旧模式，必须先销毁该运行时世界并以新 world ID 重建，或通过后续显式、无活动 scope 的转换流程完成；本 ADR 不实现合并回滚。
- Scope 快照过滤由 Core/Server 执行，不依赖 renderer 隐藏数据。不得用 `Arc<Mutex<Value>>`、共享根 JSON 写入或缓存的完整快照替代授权检查。
- 新增 API、Schema、Python SDK、能力表、正反例与错误语义必须同批实现；`component_leases` 只在明确支持相应 preview 的 Host 响应中声明。

## 验证门

B07-01 通过两个不相交子树并发更新、0.3/scoped 模式互斥、scope generation/lease fencing、reader 数据隔离和真实 Rust WebSocket probe 验证。原生窗口视觉、组件动作跨 owner 路由与结构迁移不属于本 ADR 的通过证据。
