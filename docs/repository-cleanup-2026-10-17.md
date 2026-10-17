# 仓库整理与验证（2026-10-17）

## 整理范围

- 取消跟踪三处 Chroma 向量索引的 12 个生成文件；根目录的业务与测试索引保留在本机，知识文档继续提交。
- 将误嵌套的 `app/rag/crawlers/app/` 旧代码副本移至本地备份，正式 `app/analysis/` 实现保留。对应六份探索文档迁至 `docs/archive/rag-experiments/`。
- 归档 8 份 QA 日志、无效测试 PDF、生成的财报样例、无内容的根目录 npm 锁文件和失效爬虫原型脚本。保留 `frontend/package-lock.json`、现有依赖环境、有效源码和测试工具。
- 将 `test_plan.txt` 按其真实内容归档为管理员数据结构探索记录；保留尚未提交的 `scripts/generate_test_report.py` 生成器。
- 更新 `.gitignore`，排除本地工具设置、向量库、日志和财报样例。
- 将上级目录八周学习计划原样复制进仓库，补充 `learning/README.md` 入口；Day 19 独立复现及集中复盘仍未验收，未推进到 Day 20。

移出工作目录的资料位于本机 `.local-backups/cleanup-2026-10-17/`，该目录不会上传。运行日志与缓存不再进入发布内容。

## 测试目录与夹具

`test_paper_trading.py` 使用真实 PostgreSQL 与根级 `client` 夹具，故从 `tests/unit/` 归位到 `tests/`，文件内容不变。

既有无密码登录测试补齐公共 `post` 助手提供的 Origin/CSRF、样例用户必填的 `pending_expires_at`，并为未知邀请码使用符合长度约束的样例；保留原业务断言。应用功能代码未修改。

本机独立测试库 `a_share_risk_agent_test` 补齐了已有的 `migrations/add_registration_method.sql`；业务数据库未操作。

## 实际验证结果

| 检查 | 结果 |
| --- | --- |
| 单元测试，隔离根级夹具 | 469 通过 |
| 认证测试，隔离根级夹具 | 128 通过 |
| 原有根级集成测试 | 124 通过 |
| 归位的模拟交易测试 | 24 通过 |
| 前端 Node 测试 | 70 通过 |
| Day 19 离线课堂测试 | 15 通过 |
| Vite 生产构建 | 成功 |
| Day 19 演示 | 计算、恢复历史、轮数上限和未知工具输出符合预期 |
| 修改的认证测试 Ruff 检查、Git diff 空白检查 | 通过 |

后端合计 745 项通过。执行方式见根目录 README。第三方 Starlette/httpx/anyio 与 PyPDF2 仍有弃用提示。

已检查新增文档的本地链接、学习计划副本一致性、本地向量库保留和忽略规则；索引文件及待上传历史中，已配置的长密钥与常见令牌格式扫描未发现匹配。

验证使用现有本机虚拟环境与独立测试数据库；未进行全新环境安装或线上部署验收。RAG/财报模块尚未全部声明的额外依赖已在 README 标明。
