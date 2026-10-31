# 原型验收用例

本表是待执行计划，不是通过报告。每项记录实际 PASS / FAIL / BLOCKED / NOT_RUN、环境、日志与复现步骤。

## L0：静态与构建

| 编号 | 操作 | 通过标准 |
|---|---|---|
| S01 | npm install，严格 TypeScript 构建 | 无 TS 错误；lockfile 由实际依赖解析生成 |
| S02 | Node 单测、check_contracts.py | 实际退出码为 0；schema 正反例通过 |
| S03 | cargo fmt/check/test/clippy | 先 core/server，后 desktop；不跳过错误，不隐藏失败用例 |
| S04 | 检查打包与许可 | 原始许可、来源 SHA、依赖许可与文件完整性可追踪 |

## L1：真实 Rust 服务，不依赖桌面

| 编号 | 操作 | 通过标准 |
|---|---|---|
| P01 | 启动 headless，读取实际描述文件 | 随机可用端口；host_id/token 只在本机；日志不打印 token |
| P02 | 无 bearer / 带未知 Origin 调 discovery 或 WS | 拒绝；不因 localhost 免鉴权 |
| P03 | 未加入者只 world.list，再 snapshot | 可见摘要，但私有场景读取被拒绝 |
| P04 | A 创建 invite 世界；B 无 key 再有 key 加入 | 无 key 拒绝，有 key 可读；不自动取得写权 |
| P05 | A 持写租约，B 请求写入 | WRITE_CONFLICT；B 读取快照不阻碍 A 写入 |
| P06 | A release 后 B 取得新租约；A 发旧请求 | epoch 或 lease ID 校验拒绝旧写 |
| P07 | 停 heartbeat 但保持底层连接，等待超过15s | 写租约失效；仅恢复 heartbeat 不复活旧租约 |
| P08 | 断开 A 的连接，再以同名重连 | 新 session；无永久绑定；必须重新加入/取得租约 |
| P09 | 一批 patch 首操作合法，次操作非法 | 整批不提交，scene/revision 不发生半更新 |
| P10 | 插入、删除、替换、移动、改属性 | 正常成功；重复 ID、移入自身、深度/数量超限被拒绝 |
| P11 | 旧 expected_revision 写入 | REVISION_CONFLICT；客户端先读取，不盲回放未知结果 |
| P12 | 慢读者、消息超限、超速 | 有限队列/报错/断开；不能静默丢交互后伪称完成 |
| P13 | 窗口销毁 | 已加入者收到删除；旧 ID 后续 NOT_FOUND |
| P14 | 0.4-preview scope writer 动态结构 | 同一 scope 内 insert/remove/replace/move/props 逐批原子提交；绑定路径仍限于本 namespace；交互节点、固定 scope root 修改与跨 scope move 被拒；混合批次失败后 scene 和 local revision 不变 |
| P15 | root authority 父结构事务与撤销 | `scope.structure.patch` 仅触及未归属布局；删除 scope root/祖先时同批移除子 scope/data namespace、发出 `scope.revoked`，旧子 lease 写被拒；parent release/disconnect/expiry/rescue 提升子 generation/epoch |
| P16 | scope-only 读者更新 | 读者实时收到本 scope 的 `scope.snapshot`；不得收到全量 `world.snapshot` 或其他 scope 的节点/数据；父撤销后仅收到 stale 的本 scope 最终快照 |

已有 `lease_probe.py` 覆盖其中一部分。探针成功不等于整表通过；P07/P12 等须补实际测试或注明待测。

## L2：Windows 真实窗口与管理器

| 编号 | 操作 | 通过标准 |
|---|---|---|
| W01 | 启动 desktop | 只有托盘；所有业务世界关闭后宿主不退出；托盘“退出”能结束 |
| W02 | 打开管理器 | 管理/设置由内部 provider 的同一种 scene 渲染，没有特殊 manager HTML |
| W03 | 托盘建白板，Python --world 加入 | 一个空白世界被填充；没有新启动一套应用 |
| W04 | Python 创建世界并持续改数据、组件 | 动态结构更新，不重建整个 WebView；文本不作为 HTML 执行 |
| W05 | 点击按钮、提交中文输入 | 事件含源节点/场景版本/epoch，发给当前写者；pending 到真实 ack；IME 不被刷新打断 |
| W06 | UI发动作后让 provider 断线或不 ack | 显示失败/超时；不显示虚假的业务成功；旧动作不能落到新提供者 |
| W07 | human 模式拖动/resize，同时 provider 更新业务；单独只调整宽度 | 默认可调整宽度；用户宽度在数据更新后保留，内容高度随新宽度重新测量；仅竖向人工改高可接管高度；修改后的真实坐标可观察；跨 DPI 不持续抖动 |
| W08 | provider尺寸/人类位置分权 | 旧 provider geometry（省略 `position_control`）仍禁止人类移动；显式设 `geometry_control=provider`、`position_control=human`、`resizable=false`、`background_drag_enabled=true` 后可移动但不能手动改尺寸；用户移动只更新 position，provider size 保持，provider 的 position/anchor 写入返回 `HUMAN_GEOMETRY` |
| W09 | 设置click_through后从托盘救援 | 可恢复可点击、可见、屏幕内；原写者失权且被hold，反复join也不能夺回 |
| W10 | 本地解除hold，提供者重新申请写 | 新epoch；没有永久封禁或隐藏关联 |
| W11 | 负坐标副屏、125/150/200%DPI、拔插显示器 | 看得见可找回；位置与尺寸单位正确；重试失败不伪成功 |
| W28 | provider 工作区语义锚点 | 四角/边距按目标显示器 DPI 换算并在工作区内夹取；human 模式拒绝设置；本地 rescue 清除锚点；显示器拔除迁移单独实机验收 |
| W12 | 隐藏/显示、默认置顶、边框、任务栏开关 | 新世界默认 `always_on_top=true`；provider 可显式关闭/恢复；普通窗口不能覆盖，其他置顶窗口按 Windows z-order 排列；检查 native report 和真实窗口，失败记录平台/版本 |
| W13 | 关闭普通世界，再关闭管理器 | 普通世界销毁；管理器隐藏；托盘能重开 |
| W14 | 连续输入时其他组件刷新 | 草稿、选区、焦点及IME尽量保留；不得整页替换 DOM |
| W15 | 内容自动适配、长文本与窗口滚动条 | 窄/宽窗口中的长中文和长无空格文本均在组件内换行、不横向溢出；静止数据下连续测量收敛；原生窗口高度按实际布局调整并受当前显示器工作区约束；默认不显示底部/右侧窗口级滚动条；受工作区限制时内容仍可访问 |
| W16 | 实时更新期间动作版本冲突 | 旧快照动作被拒后不得自动重放；刷新本世界快照并明确显示“本次未执行”；不得保留前一动作的成功回执冒充当前结果 |
| W17 | 右键菜单与注册动作 | 普通组件右键不弹原生浏览器菜单且不发送动作；注册 `context_action` 的按钮/输入只发送该静态动作并等待提供者回执，不显示原生菜单 |
| W18 | 最小化、世界保留与管理器恢复 | 标题栏最小化只隐藏、不销毁世界、不撤销租约；provider snapshot 观察到 `visible=false` 后可用 `window.configure` 显示；管理器对隐藏世界显示“显示窗口”，恢复后同一 world_id 和 provider 继续工作；X 关闭仍按普通世界关闭语义执行 |
| W19 | 管理器超高内容 | 当世界列表超过显示器工作区时，窗口外壳仍在工作区内；标题栏/状态栏/页脚保持固定，管理工作区内部滚动，工具栏粘在顶部并可键盘聚焦；无窗口级横纵滚动条 |
| W20 | 固定/隐藏标题栏与 click-through 配置 | 滚动场景后标题栏仍固定；默认标题栏显示、click-through 关闭；provider 可分别切换两项并从 snapshot 观察；标题栏隐藏或穿透启用时，管理器接管恢复本地操作 |
| W21 | 窗口文本选取默认值 | provider 可从 snapshot 读取 `text_selectable=true`，通过 `window.configure` 关闭/恢复；窗口内容遵循默认值，组件样式可覆盖，标题栏始终不可选；旧协议版本被严格拒绝 |
| W22 | 托盘全局临时隐藏/显示 | 隐藏当前逻辑可见的窗口但不销毁 world、不改变 lease/`window.visible`；提供者在隐藏期间创建的窗口也保持隐藏；“显示全部”只恢复仍逻辑可见的窗口；再次打开管理器能聚焦已有 manager |
| W23 | 标题栏图标、折叠与拖动 | 标题栏品牌/最小化/关闭图标为 SVG 并与标题共用垂直中轴；单击标题区域（移动小于 5px）只折叠/展开；折叠后原生窗口收敛到标题栏所需宽高，不留大块空白；展开恢复折叠前宽度并继续按内容适配高度；拖动超过阈值才移动窗口 |
| W24 | 健康状态降噪与恢复提示 | `online` host 行与空的健康 provider badge 隐藏；`stale`、`vacant`、来源暂停/过期/错误仍可见且可访问 |
| W25 | 无标题栏 HUD | 合成 provider 以无标题栏、`position_control=human`、`background_drag_enabled=true` 创建窗口；未配置动作的非文本背景可拖动，文本/按钮/输入与选中内容不启动移动；穿透恢复和托盘全局隐藏/显示仍可用 |
| W26 | Windows 虚拟桌面范围 | 默认只在当前桌面；provider 可显式请求所有桌面；若平台未实现请求必须明确报告 unsupported，不能把 Tauri no-op 记作通过。当前 Windows 公共 Tauri/tao API 不支持，整体保持未实现 |
| W27 | 提供者原生窗口动作 | Obsidian/TrafficMonitor 仍只对已存在、可见的 allowlisted 窗口执行枚举操作；另验证 Codex App `codex_thread_navigation` 只接受 UUID thread_id 并构造固定 `codex://threads/<UUID>`，仅响应用户点击；无 protocol handler 时动作失败且不误报会话已打开。禁止任意 URL、shell、进程路径和会话正文。|
| W28 | `.wcp` 提供者代码包 | 拖入合成包只产生有界预览；安装只解包、不运行/装依赖/覆盖同版本；未执行最终确认时启动器调用次数必须为 0；确认后启动无 shell 子进程，并验证归档与入口 SHA-256；宿主退出时只回收本 Host 启动的 child |

首版未提供鼠标跟随或外部窗口附着；不要把它们列为“验证失败”，应列为未实现。

## L3：独立 release、远程和真实来源

| 编号 | 操作 | 通过标准 |
|---|---|---|
| R01 | 构建后独立启动release，不运行Vite | 同样托盘/manager/provider链路；实际记录产物路径 |
| R02 | 两个宿主并存，端口变化 | 不读错实例，不互删描述文件；客户端校验host_id |
| R03 | 休眠/唤醒、源程序崩溃、宿主重启 | 旧数据标记过期；新host需要重新初始化，不冒充恢复业务 |
| R04 | SSH隧道从另一台电脑接入 | 仅回环监听，隧道端点与host_id明确；密钥/令牌不进仓库 |
| R05 | 外心只读桥接，真实URL与profile | 数据来自明确档案；源断开诚实标记；没有调用外心写API |
| R06 | Windows运行目录ACL | 仅合适本机身份可读令牌；未验证前不得宣传生产级隔离 |
| R07 | 1/4/8/16世界资源观察 | 记录整个相关进程树CPU/内存、更新频率、交互延迟，不以EXE大小代替占用 |

## 故障报告模板

```text
用例：
状态：PASS / FAIL / BLOCKED / NOT_RUN
环境与 commit / 文件清单哈希：
实际命令、退出码：
预期：
实际：
复现步骤：
脱敏证据：
最小修复与回归：
仍未验证：
```
