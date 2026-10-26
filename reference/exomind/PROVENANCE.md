# 外心来源追溯与迁移说明

上游仓库：exomind-team/exomind
读取分支：dev
固定提交：ddb1ba1a6c1e0760af77b55d5659df44ad253b34
上游窗口文件：src-tauri/src/commands/now_workbench_overlay_commands.rs
上游 Git blob：8039b8c605e85b52a085b5efd2c1fa7fa9a4f60f
原许可：CCOPL-1.0，Copyright (c) 2026 ExoMind Collective。

## 本包不是完整上游快照

`window-builder.excerpt.rs.txt` 是便于审阅的上游摘录；其文件 hash 不应冒充整个上游 blob hash。

`crates/wincraft-core/src/geometry.rs` 改编原文件的右下角定位、相交判断和 Windows 隐藏坐标判断，移除 AppHandle 依赖并强化算术。`apps/desktop/src-tauri/src/windows.rs` 以原窗口构造/显示模式为起点，增加多世界、可配置属性、core 投影与执行回执。

没有原样迁移主窗口 profile broker、localStorage 偏好、任务/时间块 controller、PouchDB 或外心业务服务。通用协议、租约、事务、管理提供者与 renderer 是本轮新写原型代码。

## 获取和验证上游

由本地 Codex 在已有外心仓库内使用 `git show <commit>:<path>` 核验。可将本原型与用户本地更新的外心 dev 对比，但不得悄悄用新快照覆盖这份来源记录；若迁移到新版本，记录新的 commit/path/差异。

上游许可全文随根目录 LICENSE 保留。公开发行之前应复核来源与新增内容的许可安排；本包不做商标或商业授权批准。
