import json
from copy import deepcopy

import httpx
import pytest

from app.llm_client import (
    ModelAuthenticationError,
    ModelConnectionError,
    ModelResponseError,
    ModelTimeoutError,
    QwenModelClient,
)
from app.llm_types import ToolReply


def calculation(call_id="calc_1", previous="10", current="9"):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "calculate_change",
            "arguments": json.dumps({"previous_close": previous, "current_close": current}),
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


def run(client, messages=None, **kwargs):
    from app import agent_loop

    return agent_loop.run_agent_loop(
        client,
        messages if messages is not None else [{"role": "user", "content": "计算"}],
        **kwargs,
    )


def test_http_loop_uses_actual_results_across_three_rounds():
    from app.tools.registry import tool_definitions

    messages = [{"role": "user", "content": "分别计算10到9，以及20到21的涨跌幅"}]
    saved = deepcopy(messages)
    calls = [calculation(), calculation("calc_2", "20", "21")]
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        history = payload["messages"]
        assert payload["tools"] == tool_definitions()
        assert payload["tool_choice"] == "auto"
        assert history[0] == saved[0]
        if len(requests) == 1:
            assert len(history) == 1
            reply = {"content": "先算第一项", "tool_calls": [calls[0]]}
        else:
            assert history[1]["tool_calls"] == [calls[0]]
            assert history[2]["tool_call_id"] == "calc_1"
            assert json.loads(history[2]["content"])["result"] == {"change_percent": "-10.0000"}
            if len(requests) == 2:
                assert len(history) == 3
                reply = {"content": None, "tool_calls": [calls[1]]}
            else:
                assert len(history) == 5
                assert history[3] == {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [calls[1]],
                }
                assert history[4]["tool_call_id"] == "calc_2"
                assert json.loads(history[4]["content"])["result"] == {"change_percent": "5.0000"}
                reply = {"content": "第一项跌10%，第二项涨5%", "tool_calls": []}
        return httpx.Response(200, json={"choices": [{"message": reply}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        result = run(QwenModelClient("test-only", http_client), messages)
    assert result.status == "completed"
    assert result.answer == "第一项跌10%，第二项涨5%"
    assert result.rounds == len(requests) == 3
    assert [record.tool_call_id for record in result.executions] == ["calc_1", "calc_2"]
    assert messages == saved


@pytest.mark.parametrize("answer_round", [1, 2, 3])
def test_answer_stops_early_or_on_limit(answer_round):
    client = ScriptedClient(
        *[{"tool_calls": [calculation(f"call_{i}")]} for i in range(1, answer_round)],
        {"content": "最终回答"},
    )
    result = run(client, max_rounds=3)
    assert result.status == "completed"
    assert result.answer == "最终回答"
    assert result.rounds == len(client.requests) == answer_round
    assert len(result.executions) == answer_round - 1


@pytest.mark.parametrize("max_rounds", [None, 1, 3])
def test_repeated_calls_stop_at_limit_and_keep_last_execution(max_rounds):
    limit = 5 if max_rounds is None else max_rounds
    client = ScriptedClient(
        *[
            {"content": "还需计算", "tool_calls": [calculation(f"call_{i}")]}
            for i in range(1, limit + 2)
        ]
    )
    result = run(client, **({} if max_rounds is None else {"max_rounds": max_rounds}))
    assert result.status == "max_rounds_exceeded"
    assert result.answer is None
    assert result.rounds == len(client.requests) == limit
    assert len(result.executions) == limit
    assert result.executions[-1].tool_call_id == f"call_{limit}"
    assert result.executions[-1].result == {"change_percent": "-10.0000"}


def test_multiple_calls_failure_feedback_and_recovery(monkeypatch, caplog):
    from app.tools import executor

    original = executor.calculate_change
    executed = []

    def track(arguments):
        executed.append(arguments)
        return original(arguments)

    monkeypatch.setattr(executor, "calculate_change", track)
    client = ScriptedClient(
        {"content": "计算中", "tool_calls": [calculation("bad", "0"), calculation("good")]},
        {"tool_calls": [calculation("fixed", "20", "21")]},
        {"content": "已修正，第二项上涨5%"},
    )
    with caplog.at_level("INFO", logger="app.tools.executor"):
        result = run(client, max_rounds=3)
    assert result.status == "completed"
    assert result.rounds == 3
    assert len(executed) == 2
    assert [record.tool_call_id for record in result.executions] == ["bad", "good", "fixed"]
    assert [record.status for record in result.executions] == ["error", "success", "success"]
    feedback = client.requests[1][-2:]
    assert [message["tool_call_id"] for message in feedback] == ["bad", "good"]
    assert json.loads(feedback[0]["content"])["error"]["kind"] == "invalid_arguments"
    assert json.loads(feedback[1]["content"])["result"] == {"change_percent": "-10.0000"}
    logs = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "app.tools.executor"
    ]
    assert [record["tool_call_id"] for record in logs] == ["bad", "good", "fixed"]


def test_database_calls_reuse_supplied_session(stock_session):
    calls = [
        {
            "id": "profile_1",
            "type": "function",
            "function": {"name": "get_stock_profile", "arguments": '{"stock_code":"000001.SZ"}'},
        },
        {
            "id": "profile_2",
            "type": "function",
            "function": {"name": "get_stock_profile", "arguments": '{"stock_code":"600000.SH"}'},
        },
    ]
    client = ScriptedClient(
        {"tool_calls": [calls[0]]}, {"tool_calls": [calls[1]]}, {"content": "查询完成"}
    )
    result = run(client, session=stock_session)
    assert [record.result["stock_code"] for record in result.executions] == [
        "000001.SZ",
        "600000.SH",
    ]
    assert all(record.status == "success" for record in result.executions)


@pytest.mark.parametrize("max_rounds", [0, -1, True, False, 1.5, "3", None])
def test_invalid_limit_does_not_call_model_or_tool(max_rounds, monkeypatch):
    from app import tool_calling

    def forbidden(*args, **kwargs):
        pytest.fail("非法上限不得执行工具")

    monkeypatch.setattr(tool_calling, "execute_tool", forbidden)
    client = ScriptedClient({"tool_calls": [calculation()]})
    with pytest.raises(ValueError, match="max_rounds"):
        run(client, max_rounds=max_rounds)
    assert client.requests == []


@pytest.mark.parametrize("content", [None, "", " \n"])
@pytest.mark.parametrize("empty_round", [1, 3])
def test_empty_model_reply_raises_instead_of_completing(content, empty_round):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        reply = (
            {"content": content, "tool_calls": []}
            if len(requests) == empty_round
            else {"tool_calls": [calculation(f"call_{len(requests)}")]}
        )
        return httpx.Response(200, json={"choices": [{"message": reply}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(ModelResponseError):
            run(QwenModelClient("test-only", http_client))
    assert len(requests) == empty_round


@pytest.mark.parametrize(
    "error_type",
    [ModelTimeoutError, ModelConnectionError, ModelAuthenticationError, ModelResponseError],
)
def test_model_failure_stops_loop_and_preserves_exception(error_type):
    error = error_type("模拟失败")
    client = ScriptedClient({"tool_calls": [calculation()]}, error, {"content": "不应请求"})
    with pytest.raises(error_type) as caught:
        run(client)
    assert caught.value is error
    assert len(client.requests) == 2


def test_internal_error_details_stay_in_records(monkeypatch):
    from app.tools import executor

    def crash(arguments):
        raise RuntimeError("private-connection-secret")

    monkeypatch.setattr(executor, "calculate_change", crash)
    client = ScriptedClient({"tool_calls": [calculation()]}, {"content": "计算失败"})
    result = run(client)
    assert "private-connection-secret" in result.executions[0].error.details
    assert "private-connection-secret" not in json.dumps(client.requests[1])
    assert json.loads(client.requests[1][-1]["content"])["error"] == {
        "kind": "execution_error",
        "message": "工具执行失败",
    }


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

    result = run(MutatingClient(), messages)
    assert result.status == "completed"
    assert messages == saved
