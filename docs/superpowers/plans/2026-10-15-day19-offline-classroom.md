# Day19 离线课堂示例 Implementation Plan

> **For agentic workers:** Use inline execution for this small classroom artifact. Steps use checkbox syntax.

**Goal:** 将已讲解的工具执行、有限循环、轨迹和会话保存串成可运行的辅助示例。
**Architecture:** 一个独立模块 mini_agent.py，标准库 unittest 行为测试和 demo.py；不导入主项目或参考实现。假模型仅返回脚本回复。
**Tech Stack:** Python 标准库，现有虚拟环境解释器。

## Global Constraints
- 用户要求停止手写练习并继续 Day19；代码由助手整理，明确为辅助演示。
- 仅新增 learning/day19-minimal-agent 内文件及学习记录，不改业务代码。
- 不读取 Nanobot 或主项目同类实现，不请求真实模型。
- error/success 为工具状态，completed/max_rounds_exceeded 为整次运行状态。
- 保存仅用于本机单进程课堂，固定 JSON 消息格式，不宣称生产接口兼容或多进程并发写入安全。
- 综合复盘仍按用户要求延期，独立编码未验收。
- Ruling: 当前对话继续执行小示例；无新分支、无提交或上传，独立目录避免混入已有业务改动。

## Task 1: 行为测试、最小实现及演示
Files: learning/day19-minimal-agent/{mini_agent.py,test_mini_agent.py,demo.py,README.md}
Interfaces: execute_tool(tools, tool_name, arguments); run_agent(model, tools, messages, max_rounds=3, prior_executions=None); save_session(directory, session_id, state); load_session(directory, session_id).

- [x] RED: 创建测试与仅返回 None 的接口骨架。15 个测试产生 18 个预期断言失败（含子案例）。
- [x] GREEN: 替换骨架为下方实现，15 项测试通过。
- [x] DEMO: 用脚本模型执行一次 3+5，第二轮根据工具结果形成文字；保存到临时目录，再加载并给新脚本模型传入历史。
- [x] VERIFY: 运行演示、代码检查并核对差异；更新学习记录，不标记用户独立实现完成。

Command from repository root:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s learning/day19-minimal-agent -p "test_*.py" -v
.\.venv\Scripts\python.exe -X utf8 learning/day19-minimal-agent/demo.py
```

### 完整行为测试
```python
"""Offline behavioral tests: no application, database, network, or reference imports."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import mini_agent as agent


def request(call_id="c1", name="add", arguments=None):
    return {"id": call_id, "name": name,
            "arguments": {"a": 3, "b": 5} if arguments is None else arguments}


def calls(*items):
    return {"content": None, "tool_calls": list(items)}


def answer(text="done"):
    return {"content": text, "tool_calls": []}


def add(a, b):
    return a + b


def fail():
    raise ValueError("fixture failure")


class AgentTests(unittest.TestCase):
    def test_tool_success_exactly_once(self):
        seen = []
        def echo(text):
            seen.append(text)
            return text
        self.assertEqual(agent.execute_tool({"echo": echo}, "echo", {"text": "sample"}),
                         {"status": "success", "result": "sample"})
        self.assertEqual(seen, ["sample"])

    def test_unknown_tool_does_not_execute(self):
        seen = []
        result = agent.execute_tool({"add": lambda: seen.append(1)}, "missing", {})
        self.assertEqual(result, {"status": "error", "error": "工具不存在"})
        self.assertEqual(seen, [])

    def test_tool_exception_is_error(self):
        self.assertEqual(agent.execute_tool({"fail": fail}, "fail", {}),
                         {"status": "error", "error": "fixture failure"})

    def test_invalid_arguments_are_errors(self):
        for arguments in ([], {"a": 3}):
            with self.subTest(arguments=arguments):
                result = agent.execute_tool({"add": add}, "add", arguments)
                self.assertIsInstance(result, dict)
                self.assertEqual(result["status"], "error")

    def test_non_json_result_is_error(self):
        result = agent.execute_tool({"bad": lambda: {1, 2}}, "bad", {})
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")

    def test_first_answer_stops(self):
        model = agent.ScriptedModel([answer("hello")])
        result = agent.run_agent(model, {}, [])
        self.assertIsInstance(result, dict)
        self.assertEqual((result["status"], result["rounds"], result["answer"]),
                         ("completed", 1, "hello"))
        self.assertEqual(len(model.requests), 1)
        self.assertEqual(result["executions"], [])

    def test_tool_result_sent_next_round_with_matching_id(self):
        model = agent.ScriptedModel([calls(request()), answer("8")])
        original = [{"role": "user", "content": "add 3 and 5"}]
        result = agent.run_agent(model, {"add": add}, original)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["rounds"], 2)
        self.assertEqual(len(original), 1)
        outgoing = model.requests[1]
        self.assertEqual(outgoing[-2]["tool_calls"][0]["id"], "c1")
        self.assertEqual(outgoing[-1]["role"], "tool")
        self.assertEqual(outgoing[-1]["tool_call_id"], "c1")
        self.assertEqual(json.loads(outgoing[-1]["content"])["result"], 8)

    def test_success_and_failure_both_recorded(self):
        model = agent.ScriptedModel([
            calls(request(), request("c2", "fail", {})), answer("one failure"),
        ])
        result = agent.run_agent(model, {"add": add, "fail": fail}, [])
        self.assertIsInstance(result, dict)
        self.assertEqual([r["status"] for r in result["executions"]], ["success", "error"])
        self.assertEqual(result["rounds"], 2)
        self.assertEqual(len([m for m in model.requests[1] if m["role"] == "tool"]), 2)

    def test_round_limit_has_no_extra_request(self):
        model = agent.ScriptedModel([calls(request(str(n))) for n in range(4)])
        result = agent.run_agent(model, {"add": add}, [], max_rounds=3)
        self.assertIsInstance(result, dict)
        self.assertEqual((result["status"], result["rounds"], result["answer"]),
                         ("max_rounds_exceeded", 3, None))
        self.assertEqual(len(model.requests), 3)
        self.assertEqual(len(result["executions"]), 3)

    def test_empty_reply_is_not_completion(self):
        result = agent.run_agent(agent.ScriptedModel([answer("")]), {}, [])
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "invalid_response")

    def test_model_failure_keeps_trace(self):
        model = agent.ScriptedModel([calls(request())])
        result = agent.run_agent(model, {"add": add}, [])
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "model_error")
        self.assertEqual(len(result["executions"]), 1)

    def test_invalid_round_limit(self):
        for limit in (0, -1, True):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    agent.run_agent(agent.ScriptedModel([]), {}, [], max_rounds=limit)

    def test_saved_history_survives_new_process_and_reaches_model(self):
        with TemporaryDirectory(prefix="day19-session-") as directory:
            original = {
                "messages": [{"role": "user", "content": "Meeting is Friday."}],
                "executions": [{"tool_call_id": "old", "status": "success"}],
            }
            agent.save_session(directory, "session-a", original)
            self.assertTrue((Path(directory) / "session-a.json").is_file())
            code = (
                "import json,sys; from mini_agent import load_session; "
                "print(json.dumps(load_session(sys.argv[1],sys.argv[2])))"
            )
            proc = subprocess.run(
                [sys.executable, "-c", code, directory, "session-a"],
                cwd=Path(__file__).parent, capture_output=True, text=True, check=True,
            )
            restored = json.loads(proc.stdout)
            self.assertEqual(restored, original)
            restored["messages"].append({"role": "user", "content": "Which day?"})
            model = agent.ScriptedModel([answer("Friday")])
            result = agent.run_agent(
                model, {}, restored["messages"], prior_executions=restored["executions"],
            )
            self.assertEqual(model.requests[0][0]["content"], "Meeting is Friday.")
            self.assertEqual(result["executions"], original["executions"])
            self.assertEqual(agent.load_session(directory, "session-b"),
                             {"messages": [], "executions": []})

    def test_corrupt_session_is_not_silently_reset(self):
        with TemporaryDirectory(prefix="day19-corrupt-") as directory:
            (Path(directory) / "broken.json").write_text("{broken", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                agent.load_session(directory, "broken")

    def test_session_id_cannot_escape_directory(self):
        with TemporaryDirectory(prefix="day19-boundary-") as directory:
            with self.assertRaises(ValueError):
                agent.save_session(directory, "../outside", {"messages": [], "executions": []})


if __name__ == "__main__":
    unittest.main()

```

### GREEN 实现
```python
"""Day19 classroom agent: local, synchronous, JSON-only; no model API."""
from copy import deepcopy
import json
from pathlib import Path
import re


class ScriptedModel:
    """Deterministic replies or callbacks for observing the loop offline."""

    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def chat(self, messages):
        self.requests.append(deepcopy(messages))
        reply = next(self.replies)
        return reply(deepcopy(messages)) if callable(reply) else deepcopy(reply)


def execute_tool(tools, tool_name, arguments):
    if not isinstance(tool_name, str) or tool_name not in tools:
        return {"status": "error", "error": "工具不存在"}
    if not isinstance(arguments, dict):
        return {"status": "error", "error": "参数必须是字典"}
    try:
        result = tools[tool_name](**arguments)
        json.dumps(result, allow_nan=False)
    except Exception as error:
        return {"status": "error", "error": str(error)}
    return {"status": "success", "result": result}


def run_agent(model, tools, messages, max_rounds=3, prior_executions=None):
    if type(max_rounds) is not int or max_rounds < 1:
        raise ValueError("max_rounds 必须是正整数")
    history = deepcopy(messages)
    executions = deepcopy(prior_executions or [])

    def finish(status, rounds, answer=None, error=None):
        return {
            "status": status, "rounds": rounds, "answer": answer,
            "messages": history, "executions": executions, "error": error,
        }

    for round_number in range(1, max_rounds + 1):
        try:
            reply = model.chat(deepcopy(history))
        except Exception as error:
            return finish("model_error", round_number, error=str(error))
        if not isinstance(reply, dict):
            return finish("invalid_response", round_number)
        calls = reply.get("tool_calls", [])
        if not isinstance(calls, list):
            return finish("invalid_response", round_number)
        if calls:
            valid = all(
                isinstance(call, dict)
                and isinstance(call.get("id"), str) and bool(call["id"])
                and isinstance(call.get("name"), str) and bool(call["name"])
                and "arguments" in call
                for call in calls
            )
            if not valid or len({call["id"] for call in calls}) != len(calls):
                return finish("invalid_response", round_number)
            history.append({
                "role": "assistant", "content": reply.get("content"),
                "tool_calls": deepcopy(calls),
            })
            for call in calls:
                record = execute_tool(tools, call["name"], call["arguments"])
                executions.append({
                    "round": round_number, "tool_call_id": call["id"],
                    "name": call["name"], "arguments": deepcopy(call["arguments"]),
                    **deepcopy(record),
                })
                history.append({
                    "role": "tool", "tool_call_id": call["id"],
                    "name": call["name"],
                    "content": json.dumps(record, ensure_ascii=False, allow_nan=False),
                })
            continue
        answer = reply.get("content")
        if not isinstance(answer, str) or not answer.strip():
            return finish("invalid_response", round_number)
        history.append({"role": "assistant", "content": answer})
        return finish("completed", round_number, answer=answer)
    return finish("max_rounds_exceeded", max_rounds)


def session_path(directory, session_id):
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
        raise ValueError("会话编号仅允许英文字母、数字、下划线和短横线")
    return Path(directory) / (session_id + ".json")


def save_session(directory, session_id, state):
    path = session_path(directory, session_id)
    payload = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def load_session(directory, session_id):
    path = session_path(directory, session_id)
    if not path.exists():
        return {"messages": [], "executions": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or not all(
        isinstance(state.get(key), list) for key in ("messages", "executions")
    ):
        raise ValueError("会话文件格式错误")
    return state

```

## Execution ledger
- Plan self-review: four learning components and required boundary tests covered; no reference implementation inspected.
- RED: 15 tests, 18 assertion failures, exit 1; expected stub behavior, no import errors.
- GREEN: 15 tests passed, exit 0. Includes a new subprocess loading the saved session.
- Formatting: corrected two import orders and one long output string; final Ruff check/format clean.
- Final verification: 15 tests passed after formatting; demo produced completed/2 rounds/1 tool, restored result 8, round limit 3, unknown tool error.
- Scope review: required classroom components covered; no production source, reference code, model service, or database used. Not an independent learner implementation assessment. No Git commit or upload.

