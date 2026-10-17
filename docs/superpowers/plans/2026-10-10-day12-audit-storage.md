# Day 12 第一阶段：审计存储实施计划

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 保存单次工具执行记录，跨会话读取验证，并明确传播保存失败。

**Architecture:** ToolAuditRecord 沿用现有 Base；save_tool_execution 使用独立 session factory 和事务，返回提交成功的整数 ID。第一阶段不连接 Agent 循环。

**Tech Stack:** Python 3.11+、SQLAlchemy、PostgreSQL、pytest；无新增依赖。

## Global Constraints

- 使用已批准设计 docs/superpowers/specs/2026-10-10-day12-tool-audit-design.md。
- 保留当前学习工作目录；使用 codex/day12-tool-audit 分支。
- 测试仅操作现有隔离测试数据库。

## Task 1：建表与保存

Files: app/database.py；新增 app/audit/__init__.py、app/audit/repository.py、tests/test_audit_storage.py；更新 tests/conftest.py。

接口：`save_tool_execution(run_id: str, record: ToolExecutionRecord, *, session_factory: Callable[[], Session] = SessionLocal) -> int`。

- [x] 编写参数化持久化测试：使用 execute_tool 产生成功、参数无效、未知工具记录，保存后新 Session 按 ID 查询并逐字段比较。验证 UTC 时间及小数字符串。
- [x] 编写原始 SQL 更新非法状态/负耗时的约束测试；用未提交 Stock 验证审计事务不提交业务事务；注入提交失败会话验证 rollback 后无残留，已有记录不丢失。
- [x] 执行 `.venv/Scripts/python.exe -m pytest tests/test_audit_storage.py`，确认失败源于缺少审计模块。
- [x] 增加模型字段和约束；新增独立事务保存函数：`with session_factory() as session, session.begin(): session.add(row); session.flush(); record_id = row.id`，退出事务后返回 record_id。
- [x] 将 tool_audit_records 纳入测试清理 SQL；执行新增测试、全套 pytest、Ruff。
- [x] 独立只读审查，处理阻断问题；更新学习记录及 README，提交代码。

## 验收记录

实施前检查：已有 ToolExecutionRecord.model_dump(mode="json") 可复用序列化；JSON 参数使用 Text；run_id 与 tool_call_id 不设联合唯一约束；返回 ID 避免 detached ORM 对象访问问题。事务失败原异常继续抛出，便于调用方判断实际存储故障。

执行结果：新增 9 项用例从缺少模块失败到通过；全套 300 passed，Ruff、格式与 diff 检查通过。独立只读审查无可操作问题。第一阶段按计划完成，无范围偏离。

