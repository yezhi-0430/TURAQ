# Day 12 第三阶段：审计查询与演示

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 按 run_id 分页读取持久化记录，通过固定测试数据库演示两次调用的保存与查询。

**Architecture:** repository 新增查询函数，返回独立 Pydantic 快照，按 ID 升序、after_id 游标分页，默认 20 条、最多 100 条。单独 audit_demo 模块强制假模型和 a_share_risk_agent_test 数据库，创建审计表但不清空记录；输出完整循环结果及从新会话分页查回的记录。

**Tech Stack:** Python、SQLAlchemy、Pydantic、pytest，沿用依赖。

## Global Constraints

- 沿用批准的 Day 12 设计，当前学习分支内完成。
- 不请求真实模型，不写实际应用数据库，不新增公开 HTTP 接口。
- 查询无结果返回空列表，参数校验发生在打开数据库会话之前。

## Task 1：查询仓储

Files: app/audit/repository.py；tests/test_audit_query.py。

接口：`list_tool_executions(run_id: str, *, after_id: int = 0, limit: int = 20, session_factory: Callable[[], Session] = SessionLocal) -> list[AuditRecord]`。

AuditRecord 继承 ToolExecutionRecord，增加 id、run_id、created_at；使用 ConfigDict(from_attributes=True) 从行生成快照。

- [x] 写测试：交错写入两个运行，按 run_id 隔离且 ID 升序；limit=1 游标翻页无重漏；无记录/超过末尾返回空；关闭会话后可 JSON 序列化；无效 limit/after_id（包括 bool）不打开会话。
- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/test_audit_query.py` 确认缺少查询入口失败。
- [x] 使用 `select(ToolAuditRecord).where(ToolAuditRecord.run_id == run_id, ToolAuditRecord.id > after_id).order_by(ToolAuditRecord.id).limit(limit)`，在会话内转换快照并返回。

## Task 2：假模型与真实测试数据库演示

Files: app/audit_demo.py；tests/test_audit_demo.py；README.md；docs/day-12-tool-audit.md。

- [x] 写测试：在 MODEL_PROVIDER=qwen 环境中禁止 HTTP 请求，main() 仍只用假模型；验证选择固定测试库，输出两轮、success/error 两条查回记录及相同 run_id；再次运行生成新 ID 且历史仍可查。
- [x] 运行新增测试确认缺少演示模块失败。
- [x] 演示固定使用 Settings().model_copy(update={"database_name": "a_share_risk_agent_test"}) 创建独立 engine/factory；只创建审计表；用 partial 绑定保存工厂。假模型预设两次计算（10→9 和 0→9），第二轮根据实际工具结果生成说明。以 limit=1 逐页读取本次记录；JSON 输出后 finally dispose engine。
- [x] 执行新增测试和全套 pytest、Ruff、格式检查；独立审查。
- [x] 执行 `.venv/Scripts/python.exe -X utf8 -m app.audit_demo`，核对两条记录、ID、状态及小数结果；记录证据并提交。

## 自查

演示使用原配置中的主机和凭据，但数据库名固定为测试库；输出只显示数据库名称而非连接信息。无清表操作，重复运行按新 run_id 隔离。时间戳来自仓储，JSON 数据来自新数据库会话，区别于内存执行记录。

验收：新增 14 项测试通过；全套 321 passed，Ruff、格式和 diff 检查通过；独立只读审查无可操作问题。实际演示查回两条记录，run_id=563a5eb2-b9fe-432f-ae47-c59618b3cd1e。无范围偏离。

