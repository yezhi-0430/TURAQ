import json
from copy import deepcopy

import httpx
import pytest

from app.llm_client import ModelResponseError, ModelTimeoutError, QwenModelClient
from app.llm_types import ToolReply


def calculation(call_id="call_001", previous="10"):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "calculate_change",
            "arguments": json.dumps({"previous_close": previous, "current_close": "9"}),
        },
    }


class ScriptedClient:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.requests = []

    def chat_with_tools(self, messages, tools):
        self.requests.append(deepcopy(list(messages)))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return ToolReply.model_validate(reply)


def run(client, messages=None):
    from app import tool_feedback

    return tool_feedback.run_tool_feedback(
        client, messages if messages is not None else [{"role": "user", "content": "计算跌幅"}]
    )


def test_http_feedback_contains_real_result_and_original_call():
    from app.tools.registry import tool_definitions

    call = calculation()
    initial = {"content": "我来计算", "tool_calls": [call]}
    messages = [{"role": "user", "content": "昨日10元，今日9元"}]
    saved = deepcopy(messages)
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["tools"] == tool_definitions()
        assert payload["tool_choice"] == "auto"
        if len(requests) == 1:
            assert payload["messages"] == messages
            reply = initial
        else:
            history = payload["messages"]
            assert history[:-2] == saved
            assert history[-2] == {"role": "assistant", **initial}
            assert history[-1]["role"] == "tool"
            assert history[-1]["tool_call_id"] == call["id"]
            feedback = json.loads(history[-1]["content"])
            source = feedback.pop("source")
            assert source["kind"] == "python_calculation"
            assert source["inputs_origin"] == "tool_arguments"
            assert feedback == {
                "status": "success",
                "result": {"change_percent": "-10.0000"},
                "error": None,
            }
            reply = {"content": "跌幅为10%"}
        return httpx.Response(200, json={"choices": [{"message": reply}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        result = run(QwenModelClient("test-only", http_client), messages)
    assert result.status == "completed"
    assert result.reply.content == "跌幅为10%"
    assert result.rounds == len(requests) == 2
    assert result.executions[0].result == {"change_percent": "-10.0000"}
    assert messages == saved


def test_multiple_results_keep_ids_and_rejected_call_does_not_calculate(monkeypatch):
    from app.tools import executor

    original = executor.calculate_change
    executed = []

    def track(arguments):
        executed.append(arguments)
        return original(arguments)

    monkeypatch.setattr(executor, "calculate_change", track)
    client = ScriptedClient(
        {"tool_calls": [calculation("bad", "0"), calculation("good")]},
        {"content": "第一项参数无效，第二项跌幅10%"},
    )
    result = run(client)
    assert len(executed) == 1
    feedback = client.requests[1][-2:]
    assert [message["tool_call_id"] for message in feedback] == ["bad", "good"]
    assert json.loads(feedback[0]["content"])["error"]["kind"] == "invalid_arguments"
    assert json.loads(feedback[1]["content"])["result"] == {"change_percent": "-10.0000"}
    assert [record.status for record in result.executions] == ["error", "success"]


def test_internal_exception_details_are_not_sent_to_model(monkeypatch):
    from app.tools import executor

    def crash(arguments):
        raise RuntimeError("private-connection-secret")

    monkeypatch.setattr(executor, "calculate_change", crash)
    client = ScriptedClient({"tool_calls": [calculation()]}, {"content": "计算失败"})
    result = run(client)
    assert "private-connection-secret" in result.executions[0].error.details
    assert "private-connection-secret" not in json.dumps(client.requests[1])
    error = json.loads(client.requests[1][-1]["content"])["error"]
    assert error == {"kind": "execution_error", "message": "工具执行失败"}


def test_direct_answer_needs_only_one_request():
    client = ScriptedClient({"content": "请提供两个价格"})
    result = run(client)
    assert result.status == "completed"
    assert result.rounds == len(client.requests) == 1
    assert result.executions == []


def test_second_tool_request_is_pending_not_executed(monkeypatch):
    from app.tools import executor

    original = executor.calculate_change
    executed = []

    def track(arguments):
        executed.append(arguments)
        return original(arguments)

    monkeypatch.setattr(executor, "calculate_change", track)
    client = ScriptedClient(
        {"tool_calls": [calculation()]},
        {"content": "继续计算", "tool_calls": [calculation("call_002", "20")]},
    )
    result = run(client)
    assert result.status == "needs_tools"
    assert result.rounds == len(client.requests) == 2
    assert result.reply.tool_calls[0].id == "call_002"
    assert len(executed) == len(result.executions) == 1


@pytest.mark.parametrize("content", ["", "  \n", None])
@pytest.mark.parametrize("round_number", [1, 2])
def test_empty_answer_is_an_error(content, round_number):
    def respond(request):
        history = json.loads(request.content)["messages"]
        reply = (
            {"tool_calls": [calculation()]}
            if round_number == 2 and len(history) == 1
            else {"content": content, "tool_calls": []}
        )
        return httpx.Response(200, json={"choices": [{"message": reply}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ModelResponseError):
            run(QwenModelClient("test-only", http_client))


def test_second_request_failure_propagates():
    client = ScriptedClient({"tool_calls": [calculation()]}, ModelTimeoutError("超时"))
    with pytest.raises(ModelTimeoutError):
        run(client)
    assert len(client.requests) == 2


def test_nested_input_history_is_copied():
    messages = [
        {"role": "assistant", "content": None, "tool_calls": [calculation("old")]},
        {"role": "tool", "tool_call_id": "old", "content": "{}"},
        {"role": "user", "content": "继续"},
    ]
    saved = deepcopy(messages)

    class MutatingClient:
        def chat_with_tools(self, history, tools):
            history[0]["tool_calls"][0]["id"] = "changed"
            return ToolReply(content="回答")

    run(MutatingClient(), messages)
    assert messages == saved
