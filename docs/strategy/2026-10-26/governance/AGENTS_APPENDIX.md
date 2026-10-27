---
{
  "doc_id": "governance__AGENTS_APPENDIX",
  "title": "供合并进 AGENTS.md 的演进规则",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "normative-plan",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 供合并进 AGENTS.md 的演进规则

本段是增补，不覆盖现有项目合同。先核对当前 HEAD 和用户授权，按 `INTEGRATION.md` 审阅合并。

1. 用户最新反馈优先于历史建议；已确认不再问。无法核实第三方接口时暂停对应 adapter，不暂停独立工作，不用同名项目代替。
2. 执行前读本包基线、requirements/tasks/decisions/status 与现有 `skills/wincraft-provider/SKILL.md`。按可执行依赖选一个纵向批次，不能同时改所有模块。
3. 保持 Rust/Tauri、可信组件渲染器、业务真相外置、租约/fencing、本机接管。普通 Provider 不要求前端源码，不为其功能修改宿主专用分支。
4. 允许新增公共 API/内核/通用原生适配所必要的最小变更；不重写宿主、不引入 Electron/Go、任意网页/脚本加载或 Mod 系统。
5. 整合包存配置与适配需求，不承诺封存提供者。导入先计划再确认，不自动安装/运行代码或把导出里的授权继承到新机器。
6. 国际化从第一批开始；用户可见文案、主题、权限说明与教程中英入口保持一致，稳定 ID 不翻译。文档带更新日期、核验日期、基线、状态和来源。
7. 每次代码改动同步契约/Schema/SDK/fixture/文档；翻译源变更标 stale。严格区分规划、静态观察、仓库报告、模拟与实机证据。
8. 临时提问保持调用/返回/取消语义；普通动作 ack 与问题等待分开。观察 Agent 状态不自动获得批准权限。
9. 对主题保持真实来源与可信授权条；对权限保持请求/授予/撤销闭环。安全模式不是沙箱，哈希签名不是安全认证。
10. 保持既有许可与上游署名；不擅自定名、改仓库归属、开市场、操作他人设备或发布私有资料。提交/推送/发版按用户当轮授权。
11. 每批更新任务状态、运行命令/退出码/证据级别/产物哈希与未测项。无环境标 NOT_RUN，不用浏览器 mock 代替 Rust/Windows 验收。
12. 新功能失败须能回退本批次，不覆盖用户未提交改动；不使用 destructive reset。单文件单写者；需多 Agent 时分配不相交改动并集成回归。
