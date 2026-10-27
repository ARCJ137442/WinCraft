---
{
  "doc_id": "docs__audience__PROVIDER_GUIDE",
  "title": "提供者层：不用前端也能搭建",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "provider-design-guide",
  "audience": "provider-author",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 提供者层：不用前端也能搭建

从当前仓库`skills/wincraft-provider/SKILL.md`和`examples/python/client.py`开始，读取真实descriptor路径但不打印秘密。握手、发现、加入、租约、声明场景、接收动作、返回结果、断线重建依次执行。

不要将draft包/主题/活动信封直接当0.3方法。先查询能力，再选择兼容路径。来源状态、来源新鲜度和宿主连接状态分开；丢失数据不是数值0。你收到点击只证明请求到达，业务完成必须由自己的系统确认。

面向多提供者的后续设计中，申请你需要的子树和数据槽，不写他人的资源；不在共享槽里存真实凭据。超时结果未知时先读回，不能自动重发有外部副作用的动作。

主题只改变可允许的表现，不覆盖宿主权限和来源身份。包只保存配置；你自己的业务存档、安装与升级仍由你维护。
