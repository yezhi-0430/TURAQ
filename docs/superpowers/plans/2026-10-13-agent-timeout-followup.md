# 研究超时与旧状态修复

用户截图延续已授权的研究助手问题修复，保留工作区已有改动，当前会话直接执行。

证据：18:29 的历史调用返回本地空列表；18:31 的新调用已读取在线 98 条日线，耗时 413.2ms，API 随后 504。运行配置模型单次等待 10 秒、总研究 60 秒。前端失败分支未更新本次研究卡片，沿用上一轮“已完成”。

- [x] 为行情成功后模型超时、错误响应中的私有数据隔离、前端失败状态覆盖成功状态写失败回归测试。
- [x] 单次模型等待默认及本机配置调至 30 秒（现有允许最大值），总流程仍 60 秒、额度不变。模型超时不自动重试；504 可携带已经审计的工具结果与本次运行 ID，明确未完成。请求封装在账号修订校验后传递部分结果，前端安全显示，不将其加入助手答案历史。
- [x] 用相关权限/额度/模型/前端测试与生产构建验证，桌面和手机检查失败与恢复；确认运行配置生效。保留旧请求历史，更新研究跳转文案，日线未指定区间时使用最近 90 个自然日。

文件：`app/config.py`、`.env.example`、`app/agent_api.py`、`app/model_limits.py`、`app/agent_policy.py`、`frontend/api.js`、`frontend/index.html`；测试 `tests/unit/test_agent_market.py`、`tests/unit/test_model_config.py`、`tests/frontend/auth-ui.test.mjs`。不新增工具、权限或自动扫描。

完成：Python 600 项通过（排除原工作区旧导入模型的 `tests/test_invite_auth_integration.py`），前端 54 项通过，Ruff、Vite 构建及生产页面桌面/手机失败恢复验收通过。只读审查未发现明确重要问题，未额外使用付费模型。后端日志确认重载，新 Settings 单次 30 秒、总 60 秒；详见 `docs/agent-market-markdown.md`。
