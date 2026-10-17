import json

import httpx
import pytest

from app import llm_types
from app.config import Settings
from app.llm_client import (
    FakeModelClient,
    ModelAPIError,
    ModelAuthenticationError,
    ModelResponseError,
    ModelTimeoutError,
    QwenModelClient,
    create_model_client,
)

MESSAGES = [{"role": "user", "content": "昨日 10 元，今日 9 元，请计算涨跌幅。"}]
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate_change",
            "description": "计算涨跌幅百分数",
            "parameters": {
                "type": "object",
                "properties": {
                    "previous_close": {"type": "number", "exclusiveMinimum": 0},
                    "current_close": {"type": "number", "exclusiveMinimum": 0},
                },
                "required": ["previous_close", "current_close"],
                "additionalProperties": False,
            },
        },
    }
]


def call_message(arguments: object = '{"previous_close":10,"current_close":9}') -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_change_1",
                "type": "function",
                "function": {"name": "calculate_change", "arguments": arguments},
            }
        ],
    }


def test_qwen_sends_native_tools_and_reads_call_without_text() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {
            "model": "qwen-plus",
            "messages": MESSAGES,
            "tools": TOOLS,
            "tool_choice": "auto",
            "max_tokens": 1024,
        }
        assert request.headers["authorization"] == "Bearer test-only-key"
        assert request.extensions["timeout"]["read"] == 10.0
        return httpx.Response(200, json={"choices": [{"message": call_message()}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        model = QwenModelClient("test-only-key", http_client)
        reply = model.chat_with_tools(MESSAGES, TOOLS)

    assert reply.content is None
    assert len(reply.tool_calls) == 1
    call = reply.tool_calls[0]
    assert call.id == "call_change_1"
    assert call.type == "function"
    assert call.function.name == "calculate_change"
    assert call.function.arguments == '{"previous_close":10,"current_close":9}'


@pytest.mark.parametrize(
    "message", [{"content": "无需调用工具"}, {"content": "无需调用工具", "tool_calls": None}]
)
def test_qwen_accepts_text_without_tool_calls(message: dict) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": [{"message": message}]})
    )
    with httpx.Client(transport=transport) as http_client:
        reply = QwenModelClient("test-only-key", http_client).chat_with_tools(MESSAGES, TOOLS)

    assert reply.content == "无需调用工具"
    assert reply.tool_calls == []


def test_qwen_preserves_invalid_json_arguments_for_executor() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"choices": [{"message": call_message("{broken")}]}
        )
    )
    with httpx.Client(transport=transport) as http_client:
        reply = QwenModelClient("test-only-key", http_client).chat_with_tools(MESSAGES, TOOLS)

    assert reply.tool_calls[0].function.arguments == "{broken"


@pytest.mark.parametrize(
    "message",
    [
        {"content": None, "tool_calls": None},
        {"content": 42},
        {"content": None, "tool_calls": {}},
        {
            "content": None,
            "tool_calls": [{"type": "function", "function": {"name": "x", "arguments": "{}"}}],
        },
        {
            "content": None,
            "tool_calls": [
                {"id": "x", "type": "other", "function": {"name": "x", "arguments": "{}"}}
            ],
        },
        call_message({"previous_close": 10, "current_close": 9}),
        {
            "content": None,
            "tool_calls": [
                {"id": "x", "type": "function", "function": {"name": "", "arguments": "{}"}}
            ],
        },
    ],
)
def test_qwen_rejects_invalid_tool_protocol(message: dict) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": [{"message": message}]})
    )
    with httpx.Client(transport=transport) as http_client:
        with pytest.raises(ModelResponseError):
            QwenModelClient("test-only-key", http_client).chat_with_tools(MESSAGES, TOOLS)


@pytest.mark.parametrize(
    "response", [httpx.Response(200, text="{broken"), httpx.Response(200, json={"choices": []})]
)
def test_qwen_rejects_invalid_response_envelope(response: httpx.Response) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as http_client:
        with pytest.raises(ModelResponseError):
            QwenModelClient("test-only-key", http_client).chat_with_tools(MESSAGES, TOOLS)


@pytest.mark.parametrize("failure", ["timeout", "auth", "api"])
def test_native_tools_preserve_transport_error_mapping(failure: str) -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if failure == "timeout":
            raise httpx.ReadTimeout("模拟超时", request=request)
        return httpx.Response(401 if failure == "auth" else 500)

    error_type = {
        "timeout": ModelTimeoutError,
        "auth": ModelAuthenticationError,
        "api": ModelAPIError,
    }[failure]
    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(error_type):
            QwenModelClient("test-only-key", http_client).chat_with_tools(MESSAGES, TOOLS)
    assert attempts == 1


def test_native_tools_retry_one_connection_failure() -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("模拟连接失败", request=request)
        assert json.loads(request.content)["tools"] == TOOLS
        return httpx.Response(200, json={"choices": [{"message": call_message()}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        reply = QwenModelClient("test-only-key", http_client).chat_with_tools(MESSAGES, TOOLS)
    assert len(reply.tool_calls) == 1
    assert attempts == 2


def test_fake_model_returns_text_when_no_tool_reply_configured() -> None:
    reply = FakeModelClient("离线文本").chat_with_tools(MESSAGES, TOOLS)
    assert reply.content == "离线文本"
    assert reply.tool_calls == []


def test_factory_passes_offline_tool_reply_without_http() -> None:
    settings = Settings(
        _env_file=None,
        database_host="localhost",
        database_port=5432,
        database_name="test_db",
        database_user="test_user",
        database_password="test-password",
        model_provider="fake",
    )
    configured_reply = llm_types.ToolReply.model_validate(call_message())

    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError("假模型不应发送 HTTP 请求")

    with httpx.Client(transport=httpx.MockTransport(unexpected_request)) as http_client:
        model = create_model_client(
            settings, http_client, fake_reply="原有文本", fake_tool_reply=configured_reply
        )
        reply = model.chat_with_tools(MESSAGES, TOOLS)
        assert model.chat(MESSAGES) == "原有文本"

    assert reply == configured_reply
