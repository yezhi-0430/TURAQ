# Day 13 工具来源 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 将真实工具来源、实际返回交易日期和执行时间传给模型、HTTP 和持久化审计。

**Architecture:** tools/provenance.py 定义 ToolSource 和来源构造；executor 在成功后生成来源；消息/API 传递来源，audit 使用新可空 JSON 列自动保存/读取。已有升级入口负责旧 PostgreSQL 列升级。

**Tech Stack:** Python、Pydantic、SQLAlchemy、FastAPI、Pytest；离线模型与内存 SQLite。

## Global Constraints

规格：`docs/superpowers/specs/2026-10-11-day13-tool-sources-design.md`。
result 字典/列表保持原格式；source 只由执行器生成，失败为 null。executed_at 是 UTC 完成时间，latest_trade_date 只取实际返回行最大日期。未知上游来源/采集时间为 null。计算 inputs_origin=tool_arguments，不当作行情证据。旧审计 source=null。正式数据库不自动升级，不包含其他工作目录的前端/行情/部署改动。

## Task 1: 来源贯通工具、模型、HTTP 和审计

**Files:** Create `app/tools/provenance.py`, `tests/unit/test_tool_sources.py`; Modify `app/tools/executor.py`, `app/tool_messages.py`, `app/agent_api.py`, `app/agent_policy.py`, `app/database.py`, `app/schema_upgrade.py`, `tests/unit/test_agent_safety.py`, `tests/unit/test_tool_feedback.py`, `tests/test_schema_upgrade.py`, `docs/day-13-safety-boundaries.md`, `README.md`（启动前升级命令）。

**Interfaces:** ToolSource(kind, executed_at, latest_trade_date=None, record_count, upstream_source=None, collected_at=None, inputs_origin=None)；`build_tool_source(tool_name: str, result: dict | list, executed_at: datetime) -> ToolSource`。ToolExecutionRecord/HTTP ToolExecution 新增 `source: ToolSource | None = None`；数据库同名可空 JSON 列，repository 继续按 model_dump 保存与 from_attributes 读取。

- [x] 写真实 SQLite 测试：成功资料/多日线/区间/空日线/计算来源；四类拒绝/失败无来源；执行时间在调用前后之间且 UTC；坏来源字段不能通过 tool arguments 注入。

```python
record = execute_tool('get_daily_prices', raw, session=stock_session)
source = record.model_dump(mode='json').get('source')
assert source is not None
assert source['kind'] == 'local_database'
assert source['latest_trade_date'] == '2026-10-09'
assert source['collected_at'] is None
```

- [x] 增加 HTTP 测试，真实循环和审计仓储配脚本模型：检查返回 source == 模型 tool payload source == 再次查到的审计 source；空 result 必须返回字符串 `[]` 而非 null。升级测试手工模拟旧审计表缺 source 列，插入旧记录，升级两次后原记录完整且 source 为 null。
- [x] 运行 `.venv/Scripts/python.exe -X utf8 -m pytest --confcutdir=tests/unit tests/unit/test_tool_sources.py tests/unit/test_agent_safety.py -q -o addopts=''`。Expected：来源与空结果测试因未实现字段失败，原入口测试通过。旧表升级测试 Expected：缺 source 列失败。
- [x] 实现 ToolSource 与真实来源构造；executor 仅成功后用 datetime.now(UTC) 构造来源；来源赋给记录，日志自动携带。消息 payload 追加 `source=record.source.model_dump(mode='json') if record.source else None`。
- [x] HTTP 同步 source，成功 result 使用 `is not None` 保留空数组；后端系统说明明确日期/来源/空结果和计算输入规则。数据库追加可空 source JSON；upgrade_database 在同一事务内执行 `ALTER TABLE tool_audit_records ADD COLUMN IF NOT EXISTS source JSON NULL`。升级输出说明增加来源列。
- [x] 更新旧消息契约测试检查来源而不是删除原有 result/error 断言。运行新增测试 Expected：全部通过；全部隔离 unit、schema_upgrade+审计 PostgreSQL 套件 Expected：全部通过；Ruff/格式/diff 检查 Expected：通过。
- [x] 更新学习笔记与旧库升级命令，技术完成与独立编码掌握分开记录；按本任务文件本地提交。一次独立只读审查，Important/Critical 按 TDD 修复后回归。

## Review Focus

检查旧库升级和旧审计 nullable 兼容；空列表不要变成缺失 result；不能把请求 end_date、审计创建时间、模型声称的来源或计算输入当成市场证据；来源在真实模型反馈/HTTP/持久化查询一致；保留错误 details 隐藏和原价格精度。检查时间语义及前端现有字符串 result 兼容。

## 执行记录

基线为 ac76354，codex/day13-safety。沿用已批准的直接执行方式，保留工作目录未提交的前端/行情改动，不创建或移动检出。
Pre-flight：单任务，无跨任务共享接口；source 在 Pydantic/JSON/消息/API 四处同名，result 不包裹。

Task 1：实现和回归完成，等待最终只读审查。初轮新增单元/HTTP 14 fail、既有 38 pass；旧 PostgreSQL 来源列升级 1 fail。实现后相关工具/循环/入口 113 pass，schema_upgrade+审计 33 pass，全部隔离 unit 320 pass。两个既有依赖警告保留；正式数据库未升级。

Task 1: complete (commits ac76354..863dbb6; tests: 隔离 unit 320 passed，schema_upgrade+audit 33 passed，Ruff/format/diff 通过)。正式数据库未升级，启动前须运行已记录命令。
Final review: 独立只读审查无 Critical/Important/Minor，未派发第二次审查。
Final: Ruling: 审查未重跑数据库测试 — 采信本会话实际 320/33 通过输出和隔离库测试，不声称 reviewer 独立重跑；成本若错为测试结论需复核。
Final: Ruling: 正式库未升级 — 保留显式部署步骤及启动前命令，不自动修改正式库；漏执行会导致新代码审计写入失败。
Final: Ruling: 真实模型遵循及行情真实性/新鲜度 — 仅承诺后端可查元数据，未知采集/上游来源为 null；成本是模型自然语言仍需核对工具证据。
Final: Ruling: 前端来源展示、实时 Agent 工具、建议执行类型、会话恢复 — 维持阶段范围，明确为后续，不能据此声称完整 Day 13 或 Day 12 会话闭环；成本为这些能力仍未交付。
Final: Ruling: 未提交行情/前端/部署和第一阶段 — 本次仅审查第二阶段提交及必要兼容，第一阶段已另审；成本为不能将本次结论用于无关改动。
