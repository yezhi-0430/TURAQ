import json

import httpx
import pytest

from app.llm_client import (
    FakeModelClient,
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelResponseError,
    ModelTimeoutError,
    QwenModelClient,
)


def test_fake_model_returns_configured_reply() -> None:
    client = FakeModelClient(reply="这是一条测试回答")
    messages = [
        {"role": "user", "content": "什么是股票的日线数据？"},
    ]

    reply = client.chat(messages)

    assert reply == "这是一条测试回答"


def test_qwen_client_sends_messages_and_reads_reply() -> None:
    messages = [{"role": "user", "content": "什么是日线？"}]

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer test-only-key"
        assert json.loads(request.content) == {
            "model": "qwen-plus",
            "messages": messages,
            "max_tokens": 1024,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "一天的行情记录。"}}]},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        client = QwenModelClient(api_key="test-only-key", http_client=http_client)
        reply = client.chat(messages)

    assert reply == "一天的行情记录。"


def test_qwen_client_sets_read_timeout() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"]["read"] == 10.0
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "测试回答"}}]},
        )

    with httpx.Client(
        timeout=None,
        transport=httpx.MockTransport(respond),
    ) as http_client:
        client = QwenModelClient(api_key="test-only-key", http_client=http_client)
        client.chat([{"role": "user", "content": "你好"}])


def test_qwen_client_maps_read_timeout() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("模拟超时", request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        client = QwenModelClient(api_key="test-only-key", http_client=http_client)

        with pytest.raises(ModelTimeoutError):
            client.chat([{"role": "user", "content": "你好"}])


def test_qwen_client_retries_one_connection_failure() -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            raise httpx.ConnectError("模拟连接失败", request=request)

        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "连接成功"}}]},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        client = QwenModelClient(api_key="test-only-key", http_client=http_client)
        reply = client.chat([{"role": "user", "content": "你好"}])

    assert reply == "连接成功"
    assert attempts == 2


def test_qwen_client_stops_after_two_connection_failures() -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("模拟连接失败", request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        client = QwenModelClient(api_key="test-only-key", http_client=http_client)

        with pytest.raises(ModelConnectionError):
            client.chat([{"role": "user", "content": "你好"}])

    assert attempts == 2


def test_qwen_client_maps_401_without_retry() -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"code": "InvalidApiKey"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        client = QwenModelClient(api_key="test-only-key", http_client=http_client)

        with pytest.raises(ModelAuthenticationError):
            client.chat([{"role": "user", "content": "你好"}])

    assert attempts == 1


@pytest.mark.parametrize("status_code", [400, 403, 429, 500])
def test_qwen_client_maps_other_http_errors_without_retry(status_code: int) -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code, json={"message": "provider error"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        client = QwenModelClient(api_key="test-only-key", http_client=http_client)
        with pytest.raises(ModelAPIError) as caught:
            client.chat([{"role": "user", "content": "你好"}])

    assert caught.value.status_code == status_code
    assert attempts == 1


@pytest.mark.parametrize(
    "payload",
    [{"choices": []}, {"choices": [{"message": {"content": None}}]}],
)
def test_qwen_client_rejects_invalid_answer_shape(payload: dict) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as http_client:
        client = QwenModelClient(api_key="test-only-key", http_client=http_client)
        with pytest.raises(ModelResponseError):
            client.chat([{"role": "user", "content": "你好"}])


def test_qwen_client_rejects_invalid_json() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="{broken"))
    with httpx.Client(transport=transport) as http_client:
        client = QwenModelClient(api_key="test-only-key", http_client=http_client)
        with pytest.raises(ModelResponseError):
            client.chat([{"role": "user", "content": "你好"}])
