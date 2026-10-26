# 证据目录

`assistant-run/`：原型制作环境实际执行的结果。浏览器图片使用实际编译renderer和明确的模拟provider，不能证明Rust或原生Windows。

`local/`：本地Codex后续证据，默认.gitignore。分享前脱敏，禁止加入`.runtime.json`、token、用户真实业务数据。

状态说明：PASS=实际检查通过；FAIL=实际检查失败；BLOCKED=某前提阻止检查；NOT_RUN=尚未执行。源码中存在测试不等于测试通过。
