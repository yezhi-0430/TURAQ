"""Build model-facing tool messages without private execution details."""

import json

from app.llm_client import ModelResponseError
from app.llm_types import ToolReply
from app.tool_calling import ToolTurnResult


def require_answer_or_calls(reply: ToolReply) -> None:
    if not reply.tool_calls and (reply.content is None or not reply.content.strip()):
        raise ModelResponseError("模型未返回有效内容")


def tool_result_messages(turn: ToolTurnResult) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = [{"role": "assistant", **turn.reply.model_dump()}]
    for record in turn.executions:
        payload = {
            "status": record.status,
            "result": record.result,
            "error": record.error.model_dump(exclude={"details"}) if record.error else None,
            "source": record.source.model_dump(mode="json") if record.source else None,
        }
        messages.append(
            {
                "role": "tool",
                "tool_call_id": record.tool_call_id,
                "content": json.dumps(payload, ensure_ascii=False),
            }
        )
    return messages
