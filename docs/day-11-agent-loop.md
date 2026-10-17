# Day 11：工具结果回传与自动循环（技术验收与基础复盘完成）

## 第一阶段：一次结果回传

2026-10-09 已实现 `app/tool_feedback.py` 中的 `run_tool_feedback`。它先复用 Day 10 的 `run_tool_turn`，执行第一轮请求的工具，再将结果发回模型请求一次回答。

消息依次为：用户问题 → assistant 的工具调用请求 → 每个调用对应的 tool 结果。assistant 中的调用 ID 与 tool 消息中的 `tool_call_id` 一一对应；工具消息的 `content` 使用 JSON 字符串。

虚构价格 10 → 9 的执行结果回传为：

```json
{
  "role": "tool",
  "tool_call_id": "call_001",
  "content": "{\"status\": \"success\", \"result\": {\"change_percent\": \"-10.0000\"}, \"error\": null}"
}
```

`-10.0000` 来自真实 Python 计算；测试里的最终文字“跌幅为10%”来自预设的假模型响应，不证明真实模型能理解结果。

## 返回状态

- 第一轮直接回答：`completed`，`rounds=1`。
- 第一轮调用工具、第二轮给出最终回答：`completed`，`rounds=2`。
- 第二轮继续请求工具：`needs_tools`，保留第二轮调用请求，尚不执行它们。
- 无工具请求且没有有效文字：抛出 `ModelResponseError`；空串、纯空白均不算回答。
- 模型超时等异常继续抛出，不转换成成功；工具参数或业务失败可以作为结果回传。

工具错误只向模型发送 `kind` 和 `message`，内部异常 `details` 留在执行记录中。输入消息深拷贝后再追加，避免修改调用方的对话历史。

消息类型扩展为 `Sequence[Mapping[str, object]]`，用于描述包含嵌套调用列表、可空文本等字段的消息。这个类型注解不承担运行时消息校验。

## 验证证据

新增 `tests/unit/test_tool_feedback.py` 的 13 条案例先因缺少回传模块失败，实现后全部通过。覆盖模拟 HTTP 第二轮载荷、真实计算结果、多个调用及拒绝参数、内部错误不外发、首轮直接回答、第二轮待继续、两轮中的 null/空串/空白响应、第二轮超时及历史深拷贝。

2026-10-09 全套测试：260 passed，保留两条既有依赖弃用警告。全项目 Ruff 通过。测试使用假客户端和 HTTPX MockTransport，没有请求真实千问。原有 Day 10 入口仍只请求一次模型。

## 学习进度与后续

已通过口头问答确认工具结果需要显式回传、调用 ID 对应关系、有工具请求先处理工具、达到上限代表未完成。对“有回答且无调用”和“两者皆无”的判断曾混淆，解释后答对，仍需结合实际代码巩固。

第一阶段技术实现完成。第一阶段讲解中，用户能判断只追加消息不会发给模型、空列表循环零次、`json.dumps` 返回字符串，以及有效答案对应 `completed`。最初把两条消息追加一条后的数量答为两条，解释后在新例子中能判断四条追加一条为五条；列表结构仍需继续巩固。尚未验证独立编码能力。

## 第二阶段：自动循环与轮数上限

2026-10-09 新增 `app/agent_loop.py` 的 `run_agent_loop`，每轮复用既有执行器，累计工具记录，将调用请求与执行结果加入独立消息历史，再请求下一轮。消息生成与有效响应检查提取至 `app/tool_messages.py`，第一阶段入口也使用同一规则。

```python
for round_number in range(1, max_rounds + 1):
    turn = run_tool_turn(client, history, session)
    executions.extend(turn.executions)
    require_answer_or_calls(turn.reply)
    if not turn.reply.tool_calls:
        return AgentLoopResult(status="completed", ...)
    history.extend(tool_result_messages(turn))
```

`max_rounds` 默认 5，必须为正整数，拒绝布尔值、浮点数、字符串和 null；校验失败时不调用模型或工具。`range(1, max_rounds + 1)` 的终点不包含在内，因此最大轮数为 3 时，轮号是 1、2、3。

`return` 会结束整个函数，因此得到有效答案即成功结束，不需要用满轮数。若所有允许轮数都用于工具调用，循环结束后返回 `max_rounds_exceeded`，`answer=None`。上限轮的工具仍执行并记录；上限轮给出有效答案则返回 `completed`。

一轮可有多个工具调用，每个调用有自己的执行记录，但只计一次模型轮数。工具参数失败仍拒绝执行，可以回传模型供下一轮修正；无效模型响应或模型连接、鉴权、超时等异常停止并保留原异常。

第二阶段新增 28 条测试，先因缺少循环入口失败，实现后通过；加上第一阶段的 13 条，相关测试共 41 条通过。模拟 HTTP 验证三轮中完整的消息历史，真实 Python 计算得到 10 → 9 为 -10.0000、20 → 21 为 5.0000；最终文字回答仍是模拟响应。独立只读代码审查未发现阻断问题。

2026-10-09 本阶段代码验证：288 passed，保留两条既有依赖弃用警告；全项目 Ruff 通过，相关 Python 文件格式检查通过。自动循环技术实现及本轮基础口头复盘已完成。本阶段尚未请求真实千问，后续真实验证见下文；尚未验证独立编码能力。

## 第二阶段口头复盘（2026-10-09）

- 能判断第 2 轮已有有效答案且无工具请求时，`return` 结束函数，不再请求第 3 轮。
- 能判断第 1 轮请求三个工具、第 2 轮给出答案，共两轮；轮数按模型请求次数计算。
- 能判断已有两条消息、用 `extend` 加入三条消息后共有五条。
- 能判断最大轮数为五时，第五轮给出有效答案且无工具请求，应返回 `completed`。
- 能判断最大轮数为三时，第三轮工具执行成功但仍未获得最终答案，应返回 `max_rounds_exceeded`。

本轮已能在上述例子中区分成功完成、等待工具和轮数耗尽。初次出现的空响应判断与列表追加数量错误已如实保留在前文，后续仍需通过独立练习巩固。

本次收尾仅更新学习记录和 README，未修改业务代码、未重复运行代码测试、未请求真实模型。

## 第三阶段：完整演示与真实千问验证（2026-10-09）

新增 `app/agent_loop_demo.py`，可运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.agent_loop_demo
.\.venv\Scripts\python.exe -X utf8 -m app.agent_loop_demo --provider qwen
```

第一条默认离线，即使 `.env` 中的 provider 为 qwen 也不发请求。离线客户端预设首轮计算调用，第二轮使用实际工具结果生成文字。第二条才经现有客户端工厂读取本地配置请求千问。两种模式均使用虚构价格 10 和 9，复用自动循环，默认上限五轮。

三个新测试先因缺少演示模块失败，实现后通过，覆盖默认离线、显式 qwen 的模拟 HTTP 两轮及模型失败时日志状态恢复。全套 291 passed，保留两条既有依赖警告；Ruff 与相关格式检查通过。独立审查未发现阻断问题。日志追加至忽略提交的 `data/private/day11-tool-calls.jsonl`。

离线演示运行一次后，真实命令也只运行一次，使用本地配置的 qwen-plus 成功完成两轮：

1. 模型提出 `calculate_change`，调用 ID 为 `call_24b17725d85745c6a54f92`，参数为 `{"current_close": 9, "previous_close": 10}`。
2. Python 参数校验通过，实际计算得到 `{"change_percent": "-10.0000"}`，执行耗时记录为 0.107 ms。
3. 程序将对应工具调用和结果加入消息历史，再发起第二轮模型请求。
4. 千问返回“涨跌幅为 -10.0000%。”，循环返回 `status="completed"`、`rounds=2`。

已核验追加 JSONL 的调用 ID、参数、成功状态及 Python 结果。此证据验证一个虚构价格问题的两轮流程，不代表所有模型输出稳定或真实行情分析正确。未查询或写入真实行情、未修改密钥。

Day 11 技术验收包含离线边界测试和一次真实两轮验证；基础口头复盘已完成。用户随后亲自运行真实演示，体验及基础编码练习见下文。

## 用户真实调用体验与基础编码练习（2026-10-09）

用户在 VS Code 终端运行 `app.agent_loop_demo --provider qwen` 并提供输出截图。截图显示 qwen-plus、`completed`、两轮、一次成功的 `calculate_change`、Python 结果 -10.0000 和最终文字“涨跌幅为 -10.0000%。”；已结合截图解释整体完成状态与单次工具成功状态，以及 Python 计算和模型组织回答的分工。这是用户亲自运行的额外一次调用，与上一节由助手执行的一次验证分开记录。

用户暂停编码练习体验真实调用后，主动要求恢复练习：

- 正向状态填空顺序正确，最初拼写为 `need_tools`，说明正确字段值为 `needs_tools`。
- `if not reply.tool_calls` 的反向填空能正确回答 `completed`、`needs_tools`。
- 独立尝试两行条件返回时写出 `if reply.tools_calls = None`，第二行为正确的 `return reply.content`。已说明属性拼写、赋值与判断、空列表与 None、条件末尾冒号的区别。
- 改用 response 的练习中，仍混用 `reply.tool_calls` 和 `response.content`；已说明条件与返回应使用同一个响应对象。能判断响应中有工具请求时，`if not response.tool_calls` 内的 return 不执行。
- 要求独立写 `history.extend(new_messages)` 时回答不知道；提供示例后，能在新的变量名场景中写出 `executions.extend(new_records)` 的方法与变量关系，但对 new_records 加了 Markdown 反引号，已说明实际 Python 代码需去掉反引号。

本轮结果表明，概念判断比独立写出语法更熟悉；基础编码仍需提示。后续优先练习属性名称、变量一致性、if/return 语法及 append/extend 的区别，不标记为能独立实现完整 Agent。本轮归档仅修改文档，未更改业务代码或重复请求模型。
