# 外心迁移与实际接入

## 来源快照

仓库：exomind-team/exomind。读取时 dev 指向 `ddb1ba1a6c1e0760af77b55d5659df44ad253b34`。来源索引见 reference/exomind/PROVENANCE.md。

## 实际复用/改造

- 将固定 now-workbench-overlay label 改为 `world-{UUID}`。
- 继续使用 WebviewWindowBuilder 创建应用资源页、无装饰、置顶、跳过任务栏、初始隐藏的模式。
- 提取屏幕矩形相交、右下角定位、Windows 隐藏坐标识别；增加 i64 中间算术和独立测试入口。
- 保留“先确认 runtime ready/实际端口，再启动业务交互”的教训：描述文件来自已绑定的真实监听地址；renderer 首先监听，再请求当前快照。
- 没有迁入 task/timeblock/profile/localStorage 服务；通用 Core 不依赖外心。

原型 renderer 没有搬入外心 React 组件树，而是重写一个受限通用组件 catalog。这是降低接入和包体复杂度的实施选择，不是宣称复用了整套外心 UI。

## 已核查的读取接口

`src/lib/adapters/timeblock-rt-adapter.ts` 使用 `GET /timeblocks/active` 读取活动时间块。

`src/lib/adapters/runtime-profile-scope.ts` 将当前 profile 作为 `user_id` 查询参数；无法取得 profile 时应该失败，而非降为 anonymous。

上游适配器将 404 当作空活动块。但外部桥接不能仅凭 404 区分“无活动块”和“端点/版本错误”，因此本原型明确标注需要核对，不把它当连接健康证明。

## 运行默认只读桥接

```powershell
python examples/python/exomind_readonly.py `
  --runtime "<实际 WinCraft 描述文件>" `
  --exomind "http://127.0.0.1:<实际外心 RT 端口>" `
  --profile "<明确选择的档案 ID>"
```

外心有鉴权时，由使用者根据实际部署提供 `EXOMIND_HEADERS_JSON` 环境变量（字符串到字符串的 JSON 对象）；不要把令牌写入命令行或证据。桥接没有猜测外心 auth 的具体格式。

此示例投影返回字段，不擅自解释全部 TimeBlockData，也不独立计算倒计时。HTTP 失败保留最后字段并标记来源失败。桥接进程仍在线不代表 RT 数据新鲜。

## 后续写入适配

上游文件确有 pause/resume 等路径，但本包没有运行这些接口，也没有接入写按钮。Codex 首先验证只读，再使用独立测试档案和用户授权扩展回执一致性。不能为演示而修改用户真实时间块。

理想长期接入是外心内部适配器直接使用其已知 runtime/profile/服务状态；这个 Python 示例用于快速跨进程验证，不是正式替代外心数据接入架构。
