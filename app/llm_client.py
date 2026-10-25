from collections import deque
from collections.abc import Mapping, Sequence
from copy import copy, deepcopy
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.llm_types import ToolReply


class ModelTimeoutError(Exception):
    pass


class ModelConnectionError(Exception):
    pass


class ModelAuthenticationError(Exception):
    pass


class ModelAPIError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"模型接口返回 HTTP {status_code}")


class ModelResponseError(Exception):
    pass


class ModelOutputTruncatedError(ModelResponseError):
    pass


class ModelConfigurationError(Exception):
    pass


class ModelClient(Protocol):
    def chat(self, messages: Sequence[Mapping[str, object]]) -> str: ...

    def chat_with_tools(
        self, messages: Sequence[Mapping[str, object]], tools: list[dict[str, object]]
    ) -> ToolReply: ...


class FakeModelClient:
    def __init__(self, reply: str, tool_reply: ToolReply | None = None) -> None:
        self.reply = reply
        self.tool_reply = tool_reply

    def chat(self, messages: Sequence[Mapping[str, object]]) -> str:
        return self.reply

    def chat_with_tools(
        self, messages: Sequence[Mapping[str, object]], tools: list[dict[str, object]]
    ) -> ToolReply:
        if self.tool_reply is not None:
            return self.tool_reply
        return ToolReply(content=self.reply)


class QwenModelClient:
    def __init__(
        self,
        api_key: str,
        http_client: httpx.Client,
        model_name: str = "qwen-plus",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ) -> None:
        self.api_key = api_key
        self.http_client = http_client
        self.model_name = model_name
        self.chat_url = f"{base_url.rstrip('/')}/chat/completions"
        self.admission = None
        self.output_tokens = None
        self.attempt_usage = deque(maxlen=256)

    def with_admission(self, admission, *, purpose="default"):
        client = copy(self)
        if not hasattr(admission, "model_attempt_usage"):
            admission.model_attempt_usage = deque(maxlen=256)
        client.attempt_usage = admission.model_attempt_usage
        client.admission = admission
        client.output_tokens = {
            "agent": admission.settings.agent_max_output_tokens,
            "risk": admission.settings.risk_max_output_tokens,
            "risk_document": admission.settings.risk_document_output_tokens,
            "default": admission.settings.model_max_output_tokens,
        }[purpose]
        return client

    def chat(self, messages: Sequence[Mapping[str, object]]) -> str:
        message = self._request_message(messages)
        try:
            content = message["content"]
        except KeyError as exc:
            raise ModelResponseError("模型响应格式无效") from exc
        if not isinstance(content, str):
            raise ModelResponseError("模型回答不是文本")
        return content

    def chat_with_tools(
        self, messages: Sequence[Mapping[str, object]], tools: list[dict[str, object]]
    ) -> ToolReply:
        message = self._request_message(messages, tools)
        try:
            return ToolReply.model_validate(message)
        except ValidationError as exc:
            raise ModelResponseError("模型工具响应格式无效") from exc

    def _request_message(
        self, messages: Sequence[Mapping[str, object]], tools: list[dict[str, object]] | None = None
    ) -> dict[str, object]:
        payload: dict[str, object] = {"model": self.model_name, "messages": messages,
                                    "max_tokens": self.output_tokens or 1024}
        if tools is not None:
            payload.update({"tools": tools, "tool_choice": "auto"})
        from app.observability import emit

        for attempt in range(2):
            usage = None
            status = "error"
            sent = False
            try:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                if self.admission is not None:
                    from app.model_http import deadline_post

                    timeout = self.admission.before_attempt()
                    # MockTransport is an explicit isolated test transport, never live HTTP.
                    transport = self.http_client._transport
                    sent = True
                    response = getattr(self.admission, "post", deadline_post)(
                        self.chat_url, headers, payload, timeout,
                        deadline=self.admission.attempt_deadline,
                        transport=transport if isinstance(transport, httpx.MockTransport) else None,
                    )
                else:
                    sent = True
                    response = self.http_client.post(
                        self.chat_url, headers=headers, json=payload, timeout=10.0,
                    )
                try:
                    raw_usage = response.json().get("usage")
                    usage = deepcopy(raw_usage) if isinstance(raw_usage, dict) else None
                except (ValueError, AttributeError):
                    pass
                status = "ok" if not response.is_error else "error"
                break
            except httpx.ConnectError as exc:
                if attempt == 1:
                    raise ModelConnectionError("模型连接失败") from exc
            except httpx.TimeoutException as exc:
                raise ModelTimeoutError("模型请求超时") from exc
            finally:
                if sent:
                    record = dict(attempt=attempt + 1, status=status, usage=usage, cost=None)
                    self.attempt_usage.append(record)
                    emit("model_attempt", **record)

        if response.status_code == 401:
            raise ModelAuthenticationError("模型接口鉴权失败")
        if response.is_error:
            raise ModelAPIError(response.status_code)
        try:
            choice = response.json()["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelResponseError("模型响应格式无效") from exc
        if not isinstance(message, dict):
            raise ModelResponseError("模型响应格式无效")
        if choice.get("finish_reason") == "length":
            raise ModelOutputTruncatedError("模型输出达到长度上限，结果未完整生成")
        return {**message, "usage": usage}


def create_model_client(
    settings: Settings,
    http_client: httpx.Client,
    fake_reply: str = "离线测试回答",
    fake_tool_reply: ToolReply | None = None,
) -> ModelClient:
    if settings.model_provider == "fake":
        return FakeModelClient(reply=fake_reply, tool_reply=fake_tool_reply)
    if settings.dashscope_api_key is None:
        raise ModelConfigurationError("千问模式需要 DASHSCOPE_API_KEY")
    api_key = settings.dashscope_api_key.get_secret_value()
    if not api_key.strip():
        raise ModelConfigurationError("千问模式需要 DASHSCOPE_API_KEY")
    return QwenModelClient(
        api_key=api_key,
        http_client=http_client,
        model_name=settings.model_name,
        base_url=settings.model_base_url,
    )
