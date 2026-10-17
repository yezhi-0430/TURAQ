# 自动风险与文档阅读 Implementation Plan

> 使用 executing-plans 在当前工作区逐步实施；保留所有既有修改。用户已授权开发，不提交或发布。

**Goal:** 选择自选范围或搜索股票后自动读取行情与披露材料、生成可追溯分析、保存进度和历史，并让研究助手读取相同文档。

**Architecture:** 独立公共披露适配器与有界PDF解析；DB任务领取与逐股处理；前端触发/轮询并保留账号版本。现有RiskAnalysis/RiskEvent与行情程序计算复用。报告文本只作材料，原文出处由服务端生成。

**Tech Stack:** FastAPI/SQLAlchemy/PostgreSQL，原生JS/Vite，pypdf隔离子进程。

## 约束

用户分析私有；公开文档不保存用户内容。既有模型额度/并发/60秒期限按逐股调用；固定披露源，PDF独立20MiB/500页/20秒解析边界。首次页面加载不自动分析，用户选择时触发，重复请求幂等。定时持续扫描/OCR/RAG不在本轮。

## Task 1 文档源与助手

Files: app/disclosures.py, app/document_parser.py, app/tools/documents.py, app/tools/{registry,executor,provenance}.py, app/agent_api.py, app/agent_policy.py, pyproject.toml。

- [x] 红色测试：真实形状目录/公告JSON，证券过滤，路径白名单、分页、报告期、文档页码检索、网络与解析超限，离线不联网。
- [x] 实现cninfo证券标识匹配与公告列表、固定附件下载、PDF子进程解析、文档缓存与原文证据。列表返回已披露材料而非推测。
- [x] 新增查询财报/公告、读页、检索原文、财务章节和报告对照能力；注册、审计与资料来源展示保持答案优先。

## Task 2 持久化任务

Files: app/risk_tasks.py, app/risk_task_records.py, app/risk_task_analysis.py, app/risk_schema.py, app/main.py, app/risk_workbench.py。

- [x] 红色测试：组所有权、组外股票、不重复执行、逐股部分失败、取消/恢复、账号隔离、领取锁、额度、过期领取不盲重放。
- [x] 建立RiskTask/RiskTaskItem，保留证券和范围快照；数据保存在新增表和现有context/evidence，不破坏旧表。
- [x] POST创建任务，GET查看，POST处理单个待执行项（服务端领取）；前端串行驱动、刷新可恢复。未打开页面时不自动执行新的项，明确提示等待继续；已开始请求完成后保存。保留后台worker未来接入边界。
- [x] 每项使用原model_admission。行情+文档采集后程序计算，模型结构化解读，缺失源不能当低风险。完成/失败均持久化并返回事实快照；保存RiskAnalysis/RiskEvent，非自选历史可见。

## Task 3 页面闭环

Files: frontend/risk-auto.js, frontend/risk.js, frontend/risk.css, frontend/index.html, frontend/vite.config.js。

- [x] 红色测试：范围触发防抖、搜索仅查候选、选中触发、组外视图、重复和晚响应、清理及恢复进度。
- [x] 搜索候选与自动范围入口、真实进度/覆盖、逐股结果、资料证据及历史；手动资料入口保留。
- [x] 将研究背景控制在4000字；来源安全渲染、手机布局及减少动画偏好。

## Task 4 验证与运行

- [x] 单元/认证/前端回归、Ruff、生产构建；独立只读审查及修复。
- [x] 桌面/手机生产包检查；公开财报源与PDF只读验证，无额外付费模型请求。
- [x] 备份后增量创建新表；确认无运行模型后重启本项目后端，复用前端；运行就绪检查。
- [x] 文档写明浏览器驱动任务、数据覆盖、OCR/RAG/定时扫描和未验证的自动财务表格识别边界。

执行记录：653项后端、66项前端、生产构建、桌面/手机检查、公开PDF读取、独立审查及数据库备份/增量启用完成。最后去重模式隔离与固定版本入口修复后19项风险回归再次通过。范围任务由浏览器推进、离开暂停未开始项；公开文档采用服务器文件缓存，未建设完整RAG或自动表格认证。完整差异见 docs/automatic-risk-analysis.md。
