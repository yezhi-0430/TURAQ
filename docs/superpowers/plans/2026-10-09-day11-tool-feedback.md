# Day 11 Tool Feedback Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline, task-by-task.

**Goal:** 完成一次工具结果回传，获取最终回答或明确的待继续状态。

**Architecture:** 新增 tool_feedback 模块组合 Day 10 单轮入口，复制历史，追加 assistant 调用和 tool 结果，再请求一次模型。使用 Mapping[str, object] 表达只读输入消息；ToolFeedbackResult 包含 reply、status、rounds、executions。

**Tech Stack:** Python 3.11、Pydantic、HTTPX、pytest、Ruff。

## Global Constraints

依据 specs/2026-10-09-day11-agent-loop-design.md，仅执行第一阶段。无新增依赖，无真实模型请求，保持 Day 10 入口语义。工具错误只回传 kind/message，不回传 details。第二轮继续请求工具时返回 needs_tools，暂不执行新调用。

## Task 1: 结果回传与离线验收

Files: 新建 app/tool_feedback.py、tests/unit/test_tool_feedback.py；修改 app/llm_client.py、app/tool_calling.py 的消息注解。

Interface: run_tool_feedback(client, messages, session=None) -> ToolFeedbackResult；status 为 completed 或 needs_tools，rounds 为 1 或 2。继续请求使用全部三个工具定义。

- [x] 编写测试：用 HTTPX MockTransport 捕获第二轮请求，断言 assistant 原始调用、tool_call_id、计算结果和工具定义；确认输入历史不变。
- [x] 编写多调用、拒绝参数、隐藏内部错误、首轮直接回答、第二轮待继续、空白响应及超时测试。
- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/unit/test_tool_feedback.py`，确认因缺少新入口失败。
- [x] 实现以下控制结构，并将客户端的消息注解改为 Sequence[Mapping[str, object]]：

```python
history = deepcopy(list(messages))
turn = run_tool_turn(client, history, session)
if not turn.reply.tool_calls:
    require_answer(turn.reply)
    return ToolFeedbackResult(status="completed", rounds=1,
                              reply=turn.reply, executions=[])
history.append({"role": "assistant", **turn.reply.model_dump()})
for record in turn.executions:
    payload = {"status": record.status, "result": record.result,
               "error": record.error.model_dump(exclude={"details"}) if record.error else None}
    history.append({"role": "tool", "tool_call_id": record.tool_call_id,
                    "content": json.dumps(payload, ensure_ascii=False)})
reply = client.chat_with_tools(history, tool_definitions())
require_answer(reply)
return ToolFeedbackResult(status="needs_tools" if reply.tool_calls else "completed",
                          rounds=2, reply=reply, executions=turn.executions)
```

require_answer 在无工具请求且 content 缺失或 strip 后为空时抛 ModelResponseError。有调用时允许空文本。HTTP 和模型异常保持原类型向上传递。

- [x] 运行新增测试及全套 pytest，运行 Ruff。阅读 diff 并审查消息关联、隐私和阶段边界。
- [x] 更新 README 和 docs/day-11-agent-loop.md，记录验证证据与未完成部分；提交本阶段代码。

## 执行记录

Ruling: 沿用当前教学项目目录，在 codex/day11-tool-feedback 分支实现；用户刚确认项目位置且此前教学均在此目录，避免额外目录导致找错代码。

本计划即进度台账；不另建临时执行目录。用户“继续”视为在当前对话执行已批准阶段，不再次要求选择执行模式。
