"""Run the Day19 classroom example without a model service."""

import json
from tempfile import TemporaryDirectory

from mini_agent import ScriptedModel, execute_tool, load_session, run_agent, save_session


def add(a, b):
    return a + b


def tool_request(call_id):
    return {
        "content": None,
        "tool_calls": [{"id": call_id, "name": "add", "arguments": {"a": 3, "b": 5}}],
    }


def summarize(messages):
    record = json.loads(messages[-1]["content"])
    return {"content": f"计算结果为 {record['result']}", "tool_calls": []}


def recall(messages):
    previous_result = next(
        json.loads(message["content"])["result"]
        for message in reversed(messages)
        if message["role"] == "tool"
    )
    return {"content": f"上次结果为 {previous_result}", "tool_calls": []}


def main():
    tools = {"add": add}
    model = ScriptedModel([tool_request("first"), summarize])
    state = run_agent(model, tools, [{"role": "user", "content": "计算 3 + 5"}])
    print(
        f"计算：{state['status']}；模型轮数 {state['rounds']}；工具记录 {len(state['executions'])}"
    )
    print(f"答案：{state['answer']}")

    with TemporaryDirectory(prefix="day19-demo-") as directory:
        save_session(directory, "classroom", state)
        restored = load_session(directory, "classroom")
        restored["messages"].append({"role": "user", "content": "上次结果是多少？"})
        next_model = ScriptedModel([recall])
        followup = run_agent(
            next_model,
            tools,
            restored["messages"],
            prior_executions=restored["executions"],
        )
        print(
            f"重新加载并发送历史：{followup['answer']}；保留工具记录 {len(followup['executions'])}"
        )

    limit_model = ScriptedModel([tool_request(f"limit-{n}") for n in range(4)])
    limited = run_agent(limit_model, tools, [], max_rounds=3)
    print(
        f"持续请求工具：{limited['status']}；"
        f"请求次数 {len(limit_model.requests)}；答案 {limited['answer']}"
    )
    missing = execute_tool(tools, "unknown_tool", {})
    print(f"未知工具：{missing['status']}；{missing['error']}")


if __name__ == "__main__":
    main()
