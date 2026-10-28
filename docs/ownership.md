# 窗口所有权与借用

## 首版选择

Host 拥有 OS 窗口资源的生命周期；提供者通过有期限的独占写租约，取得该世界的构造/数据/窗口配置权限。多个观察会话读取不可变快照；它们不是 Rust 中与 `&mut` 并存的共享内存引用。

这是一种运行时能力/租约模型，不是把 Rust borrow checker 搬到网络上。稳定协议 0.3 仍只有整窗独占写租约；组件子树所有权现以独立协商的 `0.4-preview.1` 预览实现，尚未成为稳定协议。

## 主要状态转移

```text
空白 / 无写入者 ──申请写租约──> online(epoch=n)
       ▲                           │
       │               释放 / 断线 / 过期
       │                           ▼
       └────允许再次申请────── stale(epoch>n)

任意普通世界 ──本地接管──> operator_hold + 无写入者
                              │
                       本地解除接管
                              ▼
                        允许重新申请
```

创建者可在创建时取得租约，也可 claim=false 只创建空世界。托盘创建的是 open_authenticated 空世界；提供者创建默认 invite。read 加入不会自动获得 write；write 冲突返回明确错误。

## 为什么有 session、lease ID、epoch 三层

session 将消息绑定到实际连接，不信任提供者自报的名称。lease ID 表示这次授权；epoch 保证同一世界经历撤销和重新授权后，旧持有者即便收到晚到的回复，也不能再次写入。

身份名称相同不代表同一授权。世界 UUID 也不是写权限。host token 只允许接入宿主，不能绕过世界凭证或 lease。

## 过期与心跳

租约默认 15 秒。示例每 3 秒发送 session.ping，续期本会话仍然有效的租约；过期租约不会因迟到心跳复活。lease.renew 可以单独续租。写入时也会检查时限，不能等后台清扫器运行之后才拒绝过期写入。

正常断线即撤销。断网/失联按租约上限检测，而不是承诺零延迟发现。主机休眠恢复的具体时钟行为必须在 Windows 实机验证；现阶段未宣称满足严格跨休眠到期语义。

## 人类控制

human 模式允许本地拖动；提供者试图改位置/尺寸会收到 HUMAN_GEOMETRY，除非同时明确切回 provider。provider 模式禁用我们的拖动入口/普通调整大小；不是防止其他高权限软件移动窗口的 OS 安全保证。

“接管并找回”属于用户操作员动作，不受普通租约约束；它必须显式撤销旧写权，而不是与旧写入者竞速。operator hold 只在内存中，重启不保留。

## 组件子树借用的实施顺序

先保持稳定协议 0.3 的整窗独占语义；B07-01 只在显式 0.4 preview 协商后启用 root/window authority 与不相交子树写租约。组件租约不会隐式授予父容器删除权或窗口移动权。父节点移除时的子租约撤销、跨子树搬移、结构事务和按 owner 路由动作仍由 B07-02/B07-04 完成；仅把锁粒度改成 NodeId 不算完成。

## `0.4-preview.1` 当前边界

- Stable `0.3` 的 world lease 和既有客户端语义保持不变。Provider 必须在 `hello` 明确选择 `0.4-preview.1`，并验证 Host `component_leases` capability；无 capability 时 SDK 失败关闭。
- 当前 preview 允许 root authority 将一个独占世界原子分区成至少两个不相交子树；旧 world lease 被 fencing，root authority 与子树租约使用不同的 key 类型。
- 每个 scope 具有自己的 generation 和 revision，并绑定唯一顶层 `scene.data` namespace。scope snapshot 只返回本子树和本 namespace；普通读者不能通过 `world.snapshot` 取得完整组合场景。
- B07-01 目前只接受 scope 内现有节点的 props 更新和本 namespace 的数据替换。scope 根节点必须是只读展示组件；交互动作、插入/删除/移动、父子撤销、CAS 状态槽与跨 scope 结构事务尚未实现。
- Composition world 不会静默合回 0.3 整窗租约。当前回退方法是由本地管理器销毁该临时世界，再以新 world ID 重建 exclusive 模式。

可复现的真实 Rust WebSocket 验证入口：`examples/python/scope_probe.py`。它使用 synthetic 数据，不连接外部业务来源。
