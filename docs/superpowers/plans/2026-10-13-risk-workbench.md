# 自选股风险工作台实施计划

目标：完成用户已指定的第一、二阶段，保留当前工作区全部已有修改。

架构：原生 index.html 接入独立 risk.js/risk.css；FastAPI 复用 risk-summary 服务、身份依赖与 model_admission。新增不可变分析版本、风险事件和结构化用户证据。模型来源仅为未核验文本。

约束：20,000 字；仅用户自己的自选股票可关联；处理状态独立于评级；不生成模拟扫描/情绪分数；所有私有响应受账号与请求版本保护；无关认证文件不改动。原地实施，因实际工作台已有未提交修改，不另建遗漏这些修改的工作树。依用户明确实施授权直接推进，不提交其他人的修改。

- [x] 1. tests/unit/test_risk_workbench.py：SQLite 隔离 API 测试，先见 404，再实现 app/risk_records.py、app/risk_workbench.py。验证用户隔离、分页排序、筛选统计、失败历史、假模型、输入与证据校验、请求幂等。
- [x] 2. tests/frontend/risk.test.mjs：先验证缺失脚本，再实现风险页面组件及 index.html 导航、Vite 打包。测试范围/详情迟到响应、重复提交、账号清理、安全来源、研究跳转。
- [x] 3. 全部 Python/前端测试、Vite build、浏览器桌面/手机 QA；复查 diff，记录验证和第三阶段边界到 docs/risk-workbench.md。

接口：POST /api/v1/risk/analyses 接受资料+request_id，GET /risk/analyses 返回生成历史；GET /risk/events 同时返回当前筛选事件、分页、统计与真实扫描能力状态；GET /risk/events/{id}、PATCH /risk/events/{id} 提供详情/状态。现有 POST /risk-summary 保持兼容。

第三阶段：动态数据适配器返回来源与发布日期/交易日，计算器输出数值事实，扫描任务保存范围快照、每项结果和重试记录，稳定事件键去重。当前能力接口明确返回未接通。静态知识和实时观测分别建模；引用保留作者/书名/版本/页码/市场/历史背景，检索文本不得变更执行权限。

验收：580 项 Python（明确排除原有过时邀请码测试）、51 项前端测试通过；Ruff、Vite 构建、桌面与手机生产构建浏览器检查通过。独立审查的两项问题均有失败回归并已修复。详见 docs/risk-workbench.md。
