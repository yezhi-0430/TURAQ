# Day 11 Agent Loop Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline, task-by-task.

**Goal:** 在已验证的消息回传基础上实现自动多轮工具调用与轮数上限。

**Architecture:** tool_messages 共享有效回答检查及结果消息生成；agent_loop 复用 run_tool_turn，维护独立历史和累计执行记录。第一阶段入口继续使用两轮协议，自动循环使用独立入口。

**Tech Stack:** Python 3.11、Pydantic、HTTPX、pytest、Ruff；无新增依赖。

## Global Constraints

依据 specs/2026-10-09-day11-agent-loop-design.md，默认 max_rounds=5，只接受正整数，拒绝布尔值。模型调用次数计轮数，同轮工具数不影响轮数。工具结果包含 status/result/error；内部 details 不发回模型。最终答案必须非空白，无调用且无答案抛 ModelResponseError。模型连接、超时、鉴权及解析异常保留原类型。上限轮有调用时执行并记录，随后停止；上限轮给出答案仍成功。

## Task 1: 完整循环与验收

Files: 新建 app/tool_messages.py、app/agent_loop.py、tests/unit/test_agent_loop.py；修改 app/tool_feedback.py 复用消息函数；更新 README.md 和 docs/day-11-agent-loop.md。

Interfaces:

- tool_result_messages(turn: ToolTurnResult) -> list[dict[str, object]]：返回一条 assistant 请求和各条 tool 结果。
- require_answer_or_calls(reply: ToolReply) -> None：无调用且没有非空白答案时抛 ModelResponseError。
- run_agent_loop(client: ModelClient, messages: Sequence[Mapping[str, object]], session: Session | None = None, *, max_rounds: int = 5) -> AgentLoopResult。
- AgentLoopResult：status 为 completed/max_rounds_exceeded，answer 为 str/None，rounds 为实际轮数，executions 为累计记录。

- [x] 先编写 tests/unit/test_agent_loop.py：首轮结束、两次工具再回答、上限轮回答、持续调用到默认/指定上限、多工具顺序和失败恢复、数据库工具 session 转交、空响应与模型异常、非法上限、历史深拷贝。模拟 HTTP 的第二/第三轮请求必须断言真实 Python 结果与完整历史。
- [x] 运行 `.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_agent_loop.py`，确认因缺少循环入口失败。
- [x] 从 tool_feedback 提取结果消息与有效响应检查，保持原测试通过。消息生成如下：

```python
messages = [{"role": "assistant", **turn.reply.model_dump()}]
for record in turn.executions:
    payload = {"status": record.status, "result": record.result,
               "error": record.error.model_dump(exclude={"details"}) if record.error else None}
    messages.append({"role": "tool", "tool_call_id": record.tool_call_id,
                     "content": json.dumps(payload, ensure_ascii=False)})
return messages
```

- [x] 实现循环：

```python
if type(max_rounds) is not int or max_rounds < 1:
    raise ValueError("max_rounds 必须为正整数")
history = deepcopy([dict(message) for message in messages])
executions = []
for round_number in range(1, max_rounds + 1):
    turn = run_tool_turn(client, history, session)
    executions.extend(turn.executions)
    require_answer_or_calls(turn.reply)
    if not turn.reply.tool_calls:
        return AgentLoopResult(status="completed", answer=turn.reply.content,
                               rounds=round_number, executions=executions)
    history.extend(tool_result_messages(turn))
return AgentLoopResult(status="max_rounds_exceeded", answer=None,
                       rounds=max_rounds, executions=executions)
```

- [x] 运行新测试和第一阶段测试，再运行全套 pytest、Ruff lint/相关文件 format check，检查 diff。
- [x] 按 requesting-code-review 技能进行独立只读审查，处理实际缺陷；记录学习与验证证据，提交本阶段。

## 执行记录

总体设计已由用户批准并审阅，第一阶段教学已进入结果状态判断；本阶段沿用当前目录和 codex/day11-tool-feedback 分支，不重复请求批准。真实模型验证不属于本轮，测试只使用假客户端及 MockTransport。

本计划作执行台账。首次实现前的基线为 b3e7a37、260 条通过；所有步骤完成后补充具体结果。

第二阶段验证：28 条先失败后通过，相关共 41 passed，全套 288 passed，Ruff 与格式检查通过，独立审查无阻断问题。代码提交后继续教学，真实验证待后续安排。
