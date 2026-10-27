---
{
  "doc_id": "docs__06_OWNERSHIP",
  "title": "所有权与借用：窗口、组件、状态与高级共享",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "proposal",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "RUST-BORROW",
    "RUST-ARC",
    "RUST-MUTEX"
  ]
}
---

# 所有权与借用：窗口、组件、状态与高级共享

## 新手版

一个世界像一张桌面。第一阶段由一个程序负责编辑，别人只能看它发布的副本。以后可以把桌面分成区域：Codex 改自己的任务卡，手机摘要程序改通知卡，但不能覆盖别人。改变整个窗口位置与关闭它是另一组权限。你随时可以本地接管。

共享数据不是“大家同时随便写”。最简单的合作是一个程序负责值，其他人订阅副本；确需共同修改时，向专门的仲裁者提交操作，而不是共享一块远程内存。

## 专业版资源模型（PROPOSED）

资源地址分离：`world_id` / `scope_id` / `node_id + generation` / `state_slot_id`。根 scope 负责布局和创建子区域；子树 scope 负责内部节点；窗口 authority 负责几何、Shell 与生命周期；data scope 持有带 schema 的状态槽。读权限独立于写权，不默认让任何世界读者看到所有敏感子树。

每个写入必须验证会话、resource scope、租约 ID、epoch、有效期、预期资源版本及祖先撤销状态。**整世界 lease 与子树 lease 不可在同一可变资源上并存**：旧独占模式进入 composition 模式前必须事务式拆分授权、fence 旧根写租约。向后兼容适配不能让 0.3 writer 的 `scene.replace` 擦除新子租约区域。

## 版本与冲突

现有 `sequence` 是世界投影顺序，不能丢弃；增加 `scope_revision` 可避免 A 的进度更新使 B 的笔记更新全局冲突。跨 scope 布局变更需要 root/layout authority；数据写入必须限制 JSON Pointer 命名空间，禁止越过绑定读取未授权状态。

节点 ID 重用必须改变 generation，旧按钮事件不能命中新节点。删除父节点前撤销子租约与待处理事件；祖先撤销要立即失效，不等待子 TTL。重排、移入/移出子树边界是 authority 操作，不是普通节点移动。

## 不变量

- 同一可变资源同时只有一个有效 writer；读者拿不可变快照。
- 每个动作根据事件发出时的组件身份与 lease epoch 关联，处理时再检查有效性。
- 部分读者收到的是权限过滤后的投影，不能靠完整快照再由前端隐藏。
- 根布局拥有者只能撤销/移动其授权范围，不能把子提供者业务变成自己的事实。
- 本地接管升高 epoch 并设置 hold；自动重连不能绕开 hold。
- 同一 Provider 可拥有多个不相交 scope；相交写范围必须被拒绝或显式转移。

## Arc / Mutex 借鉴的限度

Rust 的共享引用和可变引用有借用规则；Arc 只管理共享所有权，不能单独保证内部可变数据的线程安全；Mutex 是进程内互斥原语。[RUST-BORROW][RUST-ARC][RUST-MUTEX]

网络对应物应是不可伪造的受限句柄、快照引用和可撤销 grant。高级共享优先使用 **单权威状态服务 + 类型化操作 + compare-and-set**。若引入互斥租约，要有租期、fencing、等待上限与死锁规约；不允许持锁等待人类回答或远程网络调用。多个 Host 之间的强一致锁不在本阶段范围。

“变量级”指命名且有 schema 的共享状态槽，不指地址/指针或任意表达式。先实现 subtree，再证明至少两个真实需求需要 state slot；共享事务是实验能力，默认关闭。

## 实施顺序

窗口单写保持稳定 → 注册可撤销子区域 → 子树动作路由 → 分区数据与过滤快照 → CAS 状态槽 → 有界共享状态服务。不要为了“Rust 风格”直接上 CRDT、分布式 Mutex 或多写者 UI 整树合并。

验收必须包括并发不相交写、祖先删除、ID 重用、断线重入、老 epoch、隐藏数据、布局越权、跨区域 move、操作员接管与慢消费者。
