---
{
  "doc_id": "docs__14_ANDROMORPH_TRANSPORT",
  "title": "AndroMorph 通知摘要与传输边界",
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
    "ANDROID-NOTIFY"
  ]
}
---

# AndroMorph 通知摘要与传输边界

## 目标与分工

Android 端经用户授权读取被选定应用的通知，由 AndroMorph 或独立摘要提供者生成最小摘要；通过用户选择的传输设施到达 PC，WinCraft 负责显示。蓝牙、WiFi 热点、USB、多跳、中转站、自部署服务器、飞书都是外部 transport adapter 的选择，不进入窗口内核。

Android 的 NotificationListenerService 是需专门授权的系统能力；可读取范围、工作资料、系统版本和厂商行为需真机验收。[ANDROID-NOTIFY] 前文的 fixture 测试不能证明外部真实通知与传输已完成。

## 消息信封（提案）

稳定 `message_id`、origin device/source/instance、source_seq、摘要版本、产生时间、TTL、内容分类、provenance、redaction 与可选 relay trace。加密/认证由选定通道保证，Host 仍验证来源与用途；经飞书转发不等于任何飞书账户都能下发批准。消息信封只描述来源内容，不把批准能力塞进通用传输对象。

时钟不能假定同步：携带来源时间、接收时间及 TTL 策略；严格顺序用每源序号，不把不同手机的序号拼成全局排序。摘要可更新/撤销，同一个 message_id 不能在多条路由重复出现成多条待办。

## 隐私最小化

应用 allowlist、通知内容级别、锁屏/屏幕共享策略由本机用户决定。默认转摘要而非完整消息、默认不在 WinCraft 持久化。日志只含合成 ID/状态，不记录人名、对话和 token。用户撤销后停止监听和路由，清除运行时投影；已送达外部系统的数据能否删除按各系统能力明确说明。

摘要不是事实替代：保留来源、生成时间与“机器摘要”标记；重要内容可由用户返回来源查看。模型处理不改变原通知已读/已回复状态。

## B09-01 仓库内提案原型边界

`protocol/device-message.schema.json` 是 `draft-2026-10-29` 草案。稳定身份由 `origin.device_id / origin.source_id / origin.source_instance_id / message_id` 组成；`relay_trace` 仅记录送达路径，不证明来源身份。消费端要求外部 adapter 提供 out-of-band `TransportReceipt`：直连时 peer 必须匹配 origin device；经中继时必须由外部 transport 额外证明 origin。草案本身不实现密钥、认证、网络监听或 relay。

TTL 取 origin `issued_at + ttl_seconds` 与本地接收 `received_at + ttl_seconds` 的较早者。重复 message ID 不增加待办数，重复 source sequence 拒绝；过期或被撤销的来源不再进入活动投影。只接受有 bounded summary 和 redaction 元数据的信封，不允许 raw body。`examples/integrations/device-inbox/` 只用 synthetic fixture 验证这些状态转换，不证明真实 Android 通知或任何真实 transport 已接入。

## 与 Agent 待办合并

可以呈现“3 个开发会话等待处理”和“1 条选定联系人的消息待查看”，但两类来源独立身份、状态与权限。聚合层只整理，不能擅自将“待查看”升级为必须回复，不能自动发出回复，更不能把收到通知的权限变成 Harness 审批权。

第一版为只读合并清单；后续回复/启动/批准通过各自原生授权和请求校验链路。完整跨设备路由先用受控模拟通道，再单台真机，再单一真实传输；不要同时声称所有 Bluetooth/WiFi/USB 链路成立。

## 失效场景

手机离线显示最后更新时间；重复包不重复通知；乱序旧摘要不覆盖新摘要；过期消息不作为新的批准请求；来源被撤销后拒绝重放；中转恢复不惊扰用户连续弹出旧消息。
