import json
import logging

import httpx
import pytest


def result_from_output(output):
    return json.JSONDecoder().raw_decode(output.split("\n", 1)[1])[0]


def test_demo_defaults_to_offline_even_with_qwen_environment(
    stock_session, monkeypatch, tmp_path, capsys
):
    from app import agent_loop_demo

    monkeypatch.setenv("MODEL_PROVIDER", "qwen")
    monkeypatch.chdir(tmp_path)
    original_client = httpx.Client

    def unexpected_request(request):
        pytest.fail("默认演示不应请求真实服务")

    monkeypatch.setattr(
        agent_loop_demo.httpx,
        "Client",
        lambda: original_client(transport=httpx.MockTransport(unexpected_request)),
    )

    agent_loop_demo.main([])

    output = capsys.readouterr().out
    assert "离线" in output
    result = result_from_output(output)
    assert result["status"] == "completed"
    assert result["rounds"] == 2
    assert "-10.0000" in result["answer"]
    assert result["executions"][0]["result"] == {"change_percent": "-10.0000"}
    path = tmp_path / "data/private/day11-tool-calls.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert records == result["executions"]
    # A second run appends records instead of overwriting the first one.
    agent_loop_demo.main([])
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_explicit_qwen_demo_returns_second_round_answer_and_logs_result(
    stock_session, monkeypatch, tmp_path, capsys
):
    from app import agent_loop_demo
    from app.tools.registry import tool_definitions

    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    monkeypatch.setenv("MODEL_NAME", "qwen-plus")
    monkeypatch.setenv("MODEL_BASE_URL", "https://example.test/compatible-mode/v1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-key")
    monkeypatch.chdir(tmp_path)
    original_client = httpx.Client
    requests = []
    call = {
        "id": "call_real_demo_test",
        "type": "function",
        "function": {
            "name": "calculate_change",
            "arguments": '{"previous_close":10,"current_close":9}',
        },
    }

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert str(request.url) == "https://example.test/compatible-mode/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-only-key"
        assert payload["model"] == "qwen-plus"
        assert payload["tools"] == tool_definitions()
        assert payload["tool_choice"] == "auto"
        if len(requests) == 1:
            assert "虚构" in payload["messages"][-1]["content"]
            assert "10" in payload["messages"][-1]["content"]
            assert "9" in payload["messages"][-1]["content"]
            reply = {"content": None, "tool_calls": [call]}
        else:
            assert len(payload["messages"]) == 4
            assert payload["messages"][-2]["tool_calls"] == [call]
            feedback = payload["messages"][-1]
            assert feedback["tool_call_id"] == call["id"]
            assert json.loads(feedback["content"])["result"] == {"change_percent": "-10.0000"}
            reply = {"content": "根据工具结果，虚构价格下跌10%。", "tool_calls": []}
        return httpx.Response(200, json={"choices": [{"message": reply}]})

    monkeypatch.setattr(
        agent_loop_demo.httpx,
        "Client",
        lambda: original_client(transport=httpx.MockTransport(respond)),
    )

    agent_loop_demo.main(["--provider", "qwen"])

    assert len(requests) == 2
    output = capsys.readouterr().out
    assert "千问" in output
    assert "test-only-key" not in output
    result = result_from_output(output)
    assert result["status"] == "completed"
    assert result["rounds"] == 2
    assert "下跌10%" in result["answer"]
    path = tmp_path / "data/private/day11-tool-calls.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert records == result["executions"]
    assert records[0]["tool_call_id"] == "call_real_demo_test"


def test_demo_failure_restores_logger_state(stock_session, monkeypatch, tmp_path):
    from app import agent_loop_demo
    from app.llm_client import ModelTimeoutError

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-key")
    monkeypatch.chdir(tmp_path)
    original_client = httpx.Client

    def timeout(request):
        raise httpx.ReadTimeout("模拟超时", request=request)

    monkeypatch.setattr(
        agent_loop_demo.httpx,
        "Client",
        lambda: original_client(transport=httpx.MockTransport(timeout)),
    )
    logger = logging.getLogger("app.tools.executor")
    previous = (logger.level, logger.propagate, list(logger.handlers))
    with pytest.raises(ModelTimeoutError):
        agent_loop_demo.main(["--provider", "qwen"])
    assert (logger.level, logger.propagate, logger.handlers) == previous
