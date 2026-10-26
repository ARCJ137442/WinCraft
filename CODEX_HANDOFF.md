# WinCraft 原型工程交接

版本：0.1.0-alpha.1。目标平台：Windows 优先。正式名称尚未冻结。

## 交接目标

从**已经写好的源码**得到能够在用户 Windows 机器上真实运行并复验的开发版与 release 原型。第一目标不是扩组件市场或桌宠，而是让不懂前端的外部程序通过协议使用原生窗口，且所有权、断线、动作与救援都可靠。

最短入口是根目录 `CODEX_PROMPT.md`。产品约束见 `docs/product/DECISIONS.md`，协议细节见 `docs/protocol.md`，事实基线见 `docs/engineering/VALIDATION.md`。

## 初始交接状态，不能误读

| 对象 | 交接时状态 |
|---|---|
| TypeScript 共享 renderer | 严格构建和 Node 测试通过 |
| 浏览器交互 | Chromium 中使用实际编译模块 + 模拟提供者通过部分 DOM 测试 |
| Rust 内核、Axum 服务、Tauri 适配 | 有实现与测试源码；没有 Rust 编译或原生执行证据 |
| Python 提供者 | 语法检查通过；真实连接待运行 |
| 外心桥接 | 已核对源码接口；默认只读；真实 RT 未连接 |
| 依赖锁定 | 尚无 Cargo.lock/package-lock.json，必须实际解析生成 |
| 可执行文件 | 本包不含已构建 Windows EXE，不声称可直接安装 |

22 个 Rust 测试定义不等于 22 个通过；JSON schema 检查不等于服务实际按 schema 行为；截图不等于 Tauri 窗口通过。

## 本机验证状态（2026-10-26）

- 当前源码已在 Windows/MSVC 环境通过 `npm run check`（17 项 Node + 8 类离线契约）、15 项 Python provider 单测、Rust fmt、workspace Clippy 和 core/server/desktop 检查；完整 workspace optimized 测试 38 项通过。
- Edge 离线 renderer 检查 16 项通过，覆盖窗口默认文本可选、组件样式覆盖、标题栏不可选、滚动/溢出与动态 renderer 行为；它不替代真实 Tauri 像素验收。
- 最新协议为严格 `0.3`。当前 release WebSocket 的 `lease_probe.py` 19 项通过，包含拒绝旧版本、text_selectable 默认读写、租约过期、重连 epoch fencing、原子 patch 与慢消费者。
- 新 release 构建于 `E:\tmp\wincraft-target-text-selection-20261026\release\wincraft-desktop.exe`，SHA-256 记录在 `docs/engineering/VALIDATION.md`。它已独立运行；TrafficMonitor x64 Lite 与 Obsidian Workspace 0.14.7 只读 provider 均接入，Obsidian Workspace native report 为 applied。
- 用户此前确认托盘图标/菜单可打开管理器，悬浮窗可见且可拖动。最新 release 的文本选择手势、像素级滚动条、click-through 救援等仍留在人工验收矩阵。ExoMind 由用户暂缓，未读取配置或调用 API。
- WinCraft 原解压目录没有 `.git`，未丢失或恢复其他仓库历史。用户明确授权后，已在此目录新建私有 GitHub `ARCJ137442/WinCraft`，默认分支 `dev`，`origin` 指向该远端；首个源码快照提交为 `c70ba44`。新历史从该提交开始，不是外心仓库的 graft。
- 可提交摘要和当前产物哈希见 `docs/engineering/VALIDATION.md`；逐命令日志/截图留在默认忽略的 `evidence/local/`。不写入 `.runtime.json` 内容、token、笔记标题或遥测读数。

## 必须保留的设计不变量

1. 同一世界最多一个活跃写租约。所有远程写入验证会话、lease ID、epoch、单调时钟到期和预期版本。
2. 读取是权限受限的不可变快照，不是 Rust `&T` 与 `&mut T` 的跨进程复制。发现只返回摘要，场景读取仍需加入。
3. 批量组件 patch 全部成功或全部失败；不支持的组件/属性明确报错。
4. 业务真相不落入宿主数据库；运行中暂存、输入草稿、缓存和会话状态不冒充业务记录。
5. 正常动作回到当前写者；发送成功不是业务成功。动作有 pending/ok/error/timeout；拒绝来自旧 revision 的点击。
6. 窗口配置接受与原生属性应用分开；原生失败显示为错误，不谎报已应用。
7. 人类几何模式不被普通 provider 坐标更新覆盖；本地管理器接管设置 hold，需要显式解除，不能下一次 join 就夺回。
8. 一个窗口一个共享 renderer 实例，不按提供者另建 WebView；管理与设置也是组件声明。
9. 没有固定端口、没有匿名档案 fallback、没有跨重启永久绑定。
10. 保留 ExoMind 来源许可、固定 SHA 和修改说明。

## 实施顺序与命令

### A. 静态基线和依赖

使用 Node 22、Python 3.11+、当前可用的 Rust stable。先确认工作目录，不覆盖其他同名项目。保存初始文件清单与 SHA256；`MANIFEST.sha256` 是交接快照，不要求修改后仍匹配。

```powershell
npm install
python -m pip install -r requirements-dev.txt
python -m pip install -r examples/python/requirements.txt
npm run test:ui
python scripts/check_contracts.py
cargo fmt --all -- --check
cargo check -p wincraft-core -p wincraft-server
cargo test -p wincraft-core -p wincraft-server
cargo clippy -p wincraft-core -p wincraft-server --all-targets -- -D warnings
```

初次 `cargo fmt --check` 很可能要求格式化，因为制作环境没有 rustfmt。执行 `cargo fmt --all`、审阅差异后继续；不得把格式化替代编译测试。第一次 npm install 后才可以在后续 CI 使用 npm ci。锁文件只来自真实解析。

### B. 无界面真实协议

终端 A：

```powershell
cargo run -p wincraft-server --bin wincraft-headless
```

终端 B（复制实际输出的描述文件路径）：

```powershell
python examples/python/lease_probe.py --runtime "<实际描述文件>"
python examples/python/focus_demo.py --runtime "<实际描述文件>"
```

headless 不画窗口；它只证明真实 Rust 状态机和 WebSocket 行为。给 `lease_probe.py` 扩充断网/超时场景时，使用不同连接，不模拟成同一 session。不要让客户端提供 host 时钟。

### C. Windows 桌面

按 Tauri 官方 prerequisites 安装 Windows C++ 工具链与 WebView2；不要安装 Electron。

```powershell
npm run desktop:dev
```

预期：主进程常驻托盘，无默认主窗口；托盘打开“世界管理器”。为本机自动化联调，构建后的 EXE 也接受显式 `--open-manager` 参数，启动时打开管理器；不带参数仍保持 tray-only。管理器显示实际描述文件路径。启动 Python 示例，检查是否出现真正可置顶、可移动的窗口，而非浏览器卡片。

检查 Tauri `beforeDevCommand` / `beforeBuildCommand` 工作目录、应用自定义命令 ACL、动态 `world-*` labels 的 capability、`WebviewWindow` 调用者注入、`Image::from_bytes`、tray 回调和原生窗口 setter 的精确版本签名。这里是优先定位区，不是预先断言必然有错误。

### D. 独立 release

```powershell
npm run desktop:build
```

实际产物通常位于 Cargo target 的 release 子目录，但必须先确认真实路径再报告。关闭仅用于本项目的 dev 实例后，直接启动生成 EXE；不要通过 Vite 代理声称 release 成功。也要测试两个宿主实例同时运行：不同 host_id、端口、描述文件，不互删对方令牌文件。

### E. 外心只读集成

```powershell
python examples/python/exomind_readonly.py --runtime "<WinCraft 实际描述文件>" --exomind "http://127.0.0.1:<实际 RT 端口>" --profile "<明确档案 ID>"
```

详细边界见 `docs/integration-exomind.md`。已有源码支持 `GET /timeblocks/active?user_id=...`，但真实返回结构/鉴权/运行端口都需要当前现场核验。不得把 404 直接当成“用户没有时间块”；它也可能是端点不匹配。

## 代码地图与优先审查点

| 入口 | 最该看什么 |
|---|---|
| core/model.rs、engine.rs | 写租约、防旧写 fencing、revision/sequence 区分、operator hold |
| core/scene.rs | 克隆候选再提交、ID 唯一、移入自身拒绝、资源上限 |
| server/hub.rs | 所有外部 method 与内部 provider 共用 dispatch；锁不得跨 await |
| server/transport.rs | Upgrade 前鉴权、Origin 拒绝、握手/限流/断线处理、描述文件权限 |
| server/self_provider.rs | 内部管理器不能暗建第二套 UI；受信本地管理权限与普通 lease 区分 |
| desktop/src-tauri/src/windows.rs | UI 线程与回调、DPI 坐标、关闭拦截、应用回执、拖动回声抑制 |
| desktop/src/main.ts、renderer.ts | 先订阅后快照、sequence fencing、键控节点、IME、原生/预览分离 |
| Python client.py | 并发请求回包匹配、心跳、超时不盲重试、lease epoch、host_id 校验 |

已知工程债：50ms 全快照扫描与完整快照通知不是最终性能架构；内核锁中克隆场景；组件级租约暂缺；没有 origin 白名单/TLS 和生产级跨用户鉴权；Windows descriptor ACL、多屏/DPI、click-through 救援、IME 原生路径和休眠恢复仍需专门验收。它们不应被隐瞒，也不要求本地 Codex 一口气实现所有后续愿景。

## 验收、回滚与交付

执行 `docs/engineering/ACCEPTANCE.md` 的分层用例。某层失败时保留可独立完成的其他层结果，不能把“不具备 Windows 环境”写成全部成功。修改后重新运行与变更相关的回归。

不要改用户外心的安装/数据库；试验世界可由托盘关闭或退出本宿主清理。需要重置时关闭本项目的宿主，只清理本项目生成的运行描述文件。不要全盘删除 AppData、不要结束全部 WebView2 进程。

本地最终报告必须包含：环境及依赖版本、真实命令/退出码、修复摘要、三层测试矩阵、脱敏截图、实际构建路径、已知问题。记录保存在 `evidence/local/`；源证据不可覆盖。未明确授权时，不远程发布或推送。
