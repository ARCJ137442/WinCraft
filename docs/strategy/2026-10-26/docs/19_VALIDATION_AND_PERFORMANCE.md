---
{
  "doc_id": "docs__19_VALIDATION_AND_PERFORMANCE",
  "title": "验证、性能与交付证据",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "execution-plan",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 验证、性能与交付证据

## 验证层级

L0：本交接包 Schema/计划/纯函数测试。L1：Rust 核心单元/性质测试。L2：真实 Headless Host + WS。L3：Tauri 开发构建。L4：独立 Windows release。L5：真实来源集成。L6：多设备/跨 OS。不同层结果不能代替。

仓库已有测试结果为 REPO_REPORTED，本轮新增能力没有实机证据。每批保存命令、退出码、环境、基线 commit、产物哈希、测试身份与是否真实数据；不能只贴截图。

## 必测失败路径

取消、超时、来源重启、宿主重启、租约过期/撤销、旧 ID 复用、重复动作、乱序消息、慢消费者、父子资源撤销、权限降级、缺少能力、禁用第三方、主题越界、翻译缺失、适配器崩溃、热键冲突、离屏恢复、输入法与跨 DPI。

任务内的 acceptance 条款转换为编号用例；生成矩阵见 [验收矩阵](../plan/ACCEPTANCE.md)。只把真实执行过的用例从 NOT_RUN 改为 PASS/FAIL。

## 当前仓库基线命令（执行前读 package/Cargo）

```text
npm ci
npm run check
python -m pip install -r examples/python/requirements.txt
python scripts/check_contracts.py
cargo fmt --all -- --check
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
npm run desktop:build
```

这些是已知工作流入口而非本轮执行结果。若当前脚本变化，记录实际替代命令。真实 probe 必须使用当前 Host 打印的 descriptor 路径；不猜端口，不打印内容。依赖锁文件保留既有真实解析结果。

## 性能预算先测后定

分别测托盘空闲、1/4/8 世界、20/100/256 节点、1/10/30 Hz 更新、多个快照读者、打开关闭100次、连续8小时等场景。记录全进程树工作集、CPU、GPU、句柄、唤醒、accept→render p50/p95、动作尾延迟和资源回收。

以上是测量场景，不是性能承诺。新增能力需与同机器基线比较；资源上限/失败阈值由首轮数据形成 ADR。没有证据不宣称 Tauri 优于任何具体实现。

## 自动检查与人工门

CI 检查 Schema、旧客户端 fixture、任务/文档时效、翻译占位符、链接、Rust/TS 测试和可构建性。原生焦点、IME、可访问性树、多屏、睡眠与用户救援留人工/专用环境门。发布前在干净机器或独立目录跑 release，不依赖开发服务器。
