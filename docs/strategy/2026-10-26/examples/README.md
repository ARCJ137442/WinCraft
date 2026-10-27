---
{
  "doc_id": "examples__README",
  "title": "样例怎么用：先解释，再执行",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "example-guide",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 样例怎么用：先解释，再执行

所有数据都是合成数据。`draft`信封不能直接发送到协议0.3 Host。

## 体验自适应规划

在包根目录运行：

```text
python examples/adapter/adaptive_plan.py --pack examples/packs/workday.pack.json --inventory examples/inventory/full.json --now 2026-10-26T12:00:10Z
```

将inventory换为`optional-missing.json`得到degraded；换成`required-missing.json`得到blocked（进程退出码3，属于预期）。`ambiguous.json`要求用户指定实例，而不是偷偷选择第一个；`no-grant.json`说明发现能力不等于已获授权。

此日期是固定测试时钟，不是系统当前时钟。真实使用时由可信调用方传入当前时间，且apply前重查inventory/权限/租约。planner不连接网络、不访问用户文件目录、不安装提供者，不执行adapter。

返回计划仅包含来源绑定与原因，没有Host调用。`input_digest`保证输入可比对，不能证明身份或权限，也不是执行批准。计划提交属于后续B06-03，不在本辅助脚本中实现。

## 其他样例

`ephemeral/`演示外层问题身份，现有Popup兼容层仍须复用上游完整语义校验。`activity/`不冒充真实Harness事件。`device/`不包含真实通知，也不携带自报认证成功字段；认证属于独立接收上下文。`theme/`的结构有效不等于已通过WCAG对比度或Windows视觉验收。`invalid/`为应被拒绝的负用例。
