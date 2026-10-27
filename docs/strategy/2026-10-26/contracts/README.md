---
{
  "doc_id": "contracts__README",
  "title": "提案型契约的使用边界",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "draft-contract",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 提案型契约的使用边界

此目录是设计样例，不改变协议0.3。所有新信封采用 `draft-2026-10-26` 标记；实现后由维护者依据兼容ADR确定正式版本，不直接复制这些方法名到生产。

| Schema | 作用 | 不负责 |
|---|---|---|
| pack / blueprint | 配置、能力需求和布局引用 | 安装提供者、存凭据、执行脚本 |
| inventory | 已批准来源元数据 | 无界扫描、授权或真实身份认证 |
| resolution-plan | 解析结果与阻塞原因 | 调Host、提交操作、写系统配置 |
| theme | token边界 | 任意CSS、自动证明对比度 |
| ephemeral-request | 外层问题身份与过期；payload沿现有Popup契约 | 改写既有返回、永久保存人类选择 |
| activity | 来源状态归一与来源标签 | 业务存档、默认批准 |
| device-message | 传输无关摘要信封 | 提供加密、验证身份或通知权限 |

Schema只是结构约束。还要实现唯一ID、同题内容差异、推荐项仅第一项、Other自动注入、主题对比度、时间先后、路径安全、真实认证、权限与资源限制等语义校验。设备消息不包含可自行宣称“认证通过”的字段；真实实现由受信接收适配器把认证/权限写入独立 ingress context，不能信任消息正文自报身份。

`examples-index.json`列出正反样例。负样例中的token字样是故意用于拒绝测试的占位值，非真实凭据。不要将负样例导入Host。
