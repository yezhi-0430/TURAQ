"""Day19 classroom agent: local, synchronous, JSON-only; no model API."""

import json
import re
from copy import deepcopy
from pathlib import Path


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
            "status": status,
            "rounds": rounds,
            "answer": answer,
            "messages": history,
            "executions": executions,
            "error": error,
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
                and isinstance(call.get("id"), str)
                and bool(call["id"])
                and isinstance(call.get("name"), str)
                and bool(call["name"])
                and "arguments" in call
                for call in calls
            )
            if not valid or len({call["id"] for call in calls}) != len(calls):
                return finish("invalid_response", round_number)
            history.append(
                {
                    "role": "assistant",
                    "content": reply.get("content"),
                    "tool_calls": deepcopy(calls),
                }
            )
            for call in calls:
                record = execute_tool(tools, call["name"], call["arguments"])
                executions.append(
                    {
                        "round": round_number,
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "arguments": deepcopy(call["arguments"]),
                        **deepcopy(record),
                    }
                )
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "content": json.dumps(record, ensure_ascii=False, allow_nan=False),
                    }
                )
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
