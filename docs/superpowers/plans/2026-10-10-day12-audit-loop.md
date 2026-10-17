# Day 12 第二阶段：循环审计实施计划

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 每次循环共享运行 ID，每次工具执行后立即通过显式注入的保存函数持久化。

**Architecture:** run_agent_loop 新增可选 audit_writer，签名 Callable[[str, ToolExecutionRecord], object]；默认 None 保持离线。run_tool_turn 新增可选 on_execution 回调，工具执行后调用。循环通过闭包把 run_id 绑定给保存函数。AgentLoopResult 新增 run_id。

**Tech Stack:** Python、SQLAlchemy、pytest，沿用现有依赖。

## Global Constraints

- 按已批准 Day 12 设计；只完成第二阶段。
- 当前 codex/day12-tool-audit 学习分支内实施。
- 不请求真实模型、不修改应用数据库；测试使用隔离数据库。

## Task 1：回调接入与验证

Files: app/agent_loop.py、app/tool_calling.py；新增 tests/test_audit_loop.py；更新学习记录和 README。

- [x] 编写真实保存集成测试：多个调用跨多轮共用 UUID、不同运行不同 UUID、直接回答零记录、工具参数拒绝也保存、超时和轮数耗尽仍保留记录。
- [x] 注入写入失败和执行计数，验证首条保存失败后不执行同轮第二个工具；第二条保存失败时第一条仍保留。默认不注入回调时禁止数据库连接并验证离线计算。
- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/test_audit_loop.py`，预期缺少 audit_writer 参数或 run_id 字段。
- [x] 在循环前 `run_id = str(uuid4())`；两个返回分支都包含 run_id。回调逻辑为 `audit_writer(run_id, record)`，仅显式注入时使用。
- [x] run_tool_turn 在 `execute_tool` 后执行 `if on_execution is not None: on_execution(record)`，成功才继续；不捕获审计异常。
- [x] 运行新增测试、全套 pytest、Ruff 和格式检查；独立只读审查；记录学习进度并提交。

## 自查

工具调用仍通过原执行器，异常捕获边界不变。回调在逐个调用内部执行，避免同轮所有工具执行完才保存。现有 run_tool_turn 调用保持兼容；audit_writer=None 不创建审计会话。后续演示显式传入 save_tool_execution 即启用数据库审计。

验收：新增 7 项测试先失败后通过；全套 307 passed，Ruff、格式和 diff 检查通过。独立只读审查无可操作问题。第二阶段按计划完成，无范围偏离。

