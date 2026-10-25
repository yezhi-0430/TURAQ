"""
FastAPI 路由：为前端提供 Agent 对话接口
"""

import json
import logging
from contextvars import ContextVar
from time import perf_counter

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, TypeAdapter
from pydantic_core import PydanticSerializationError

from app.agent_actions import (
    ExecutionRequest,
    ExecutionResult,
    InvalidSuggestionOutput,
    Suggestion,
    execute_watchlist_removal,
    parse_agent_answer,
)
from app.agent_loop import run_agent_loop
from app.agent_market import MarketHistoryReader
from app.agent_policy import ChatMessage as ChatMessage
from app.agent_policy import ChatRequest, build_agent_messages
from app.agent_research import ResearchMarketReader
from app.audit.repository import save_tool_execution
from app.auth.dependencies import Actor, require_actor
from app.config import Settings
from app.context_store import load_preference_message
from app.database import SessionLocal
from app.disclosures import DisclosureReader
from app.llm_client import ModelClient, ModelTimeoutError, create_model_client
from app.model_limits import (
    Admission,
    LimitsUnavailable,
    ModelDeadlineExceeded,
    RateLimited,
    bind_model,
    model_admission,
    public_error,
)
from app.tools.provenance import ToolSource

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])
logger = logging.getLogger(__name__)

# 全局 HTTP 客户端和模型客户端缓存
_http_client: httpx.Client | None = None
_model_client: ModelClient | None = None
_argument_serializer = TypeAdapter(dict)
_request_settings: ContextVar[Settings | None] = ContextVar("agent_settings", default=None)


def get_client() -> ModelClient:
    """获取或创建 ModelClient 实例（单例）"""
    global _http_client

    if _http_client is None:
        _http_client = httpx.Client()
    return create_model_client(_request_settings.get() or Settings(), _http_client)


class ToolExecution(BaseModel):
    tool_name: str
    arguments: dict | str
    result: str | None = None
    error: str | None = None
    status: str
    duration_ms: float
    source: ToolSource | None = None


class ChatResponse(BaseModel):
    run_id: str
    status: str
    answer: str | None
    rounds: int
    executions: list[ToolExecution]
    suggestions: list[Suggestion] = Field(default_factory=list)
    model_mode: str = "fake"


def display_tool_arguments(raw: str) -> dict | str:
    """Keep rejected malformed/non-object arguments visible in the response."""
    try:
        decoded = json.loads(raw)
        # Reject NaN/Infinity before Pydantic can turn non-finite floats into null.
        json.dumps(decoded, allow_nan=False)
        if isinstance(decoded, dict):
            # Match the response serializer's Unicode and nesting constraints.
            _argument_serializer.dump_json(decoded)
    except (ValueError, RecursionError, PydanticSerializationError):
        return raw
    return decoded if isinstance(decoded, dict) else raw


def display_executions(records) -> list[ToolExecution]:
    return [
        ToolExecution(
            tool_name=record.tool_name,
            arguments=display_tool_arguments(record.arguments),
            result=json.dumps(record.result)
            if record.status == "success" and record.result is not None
            else None,
            error=json.dumps(record.error.model_dump(exclude={"details"}))
            if record.status == "error" and record.error
            else None,
            status=record.status,
            duration_ms=record.duration_ms,
            source=record.source,
        )
        for record in records
    ]


@router.post("/chat")
def chat(
    request: ChatRequest,
    actor: Actor = Depends(require_actor),
    admission: Admission = Depends(model_admission),
) -> ChatResponse:
    """
    接收前端消息，运行 Agent 循环，返回结果和工具调用记录
    """
    # 转换为标准消息格式
    messages = build_agent_messages(request)
    started = perf_counter()
    audited = []
    current_run = None

    def save_progress(run_id, record):
        nonlocal current_run
        save_tool_execution(
            run_id,
            record,
            actor_id=actor.id,
            session_factory=SessionLocal,
            before_work=admission.bound_database_work,
        )
        current_run = run_id
        audited.append(record)

    def timeout_response(error):
        logger.warning(
            "agent_timeout run_id=%s elapsed_ms=%.0f audited_tools=%d reason=%s",
            current_run,
            (perf_counter() - started) * 1000,
            len(audited),
            error.detail,
        )
        if not audited:
            raise error
        return JSONResponse(
            status_code=504,
            content={
                "detail": error.detail,
                "partial": {
                    "run_id": current_run,
                    "status": "incomplete",
                    "model_mode": admission.settings.model_mode,
                    "executions": [
                        item.model_dump(mode="json") for item in display_executions(audited)
                    ],
                },
            },
        )

    try:
        preference = load_preference_message(
            admission.settings, actor.id, seconds=min(2, admission.remaining())
        )
        if preference:
            messages.insert(1, preference)
        admission.remaining()
        # 获取 LLM 客户端
        settings_token = _request_settings.set(admission.settings)
        try:
            client = bind_model(get_client(), admission, purpose="agent")
        finally:
            _request_settings.reset(settings_token)

        # 运行 Agent 循环
        with SessionLocal() as session:
            if admission.settings.model_mode == "qwen":
                session.info["daily_price_reader"] = MarketHistoryReader(admission.remaining)
                session.info["disclosure_reader"] = DisclosureReader(admission.remaining)
                session.info["research_reader"] = ResearchMarketReader(
                    session.info["daily_price_reader"]
                )
            result = run_agent_loop(
                client=client,
                messages=messages,
                session=session,
                max_rounds=request.max_rounds,
                audit_writer=save_progress,
                check_deadline=lambda: admission.bound_database_work(session),
            )
        admission.remaining()

        answer, suggestions = parse_agent_answer(result.answer)
        # 转换工具执行记录
        executions = display_executions(result.executions)

        return ChatResponse(
            run_id=result.run_id,
            status=result.status,
            answer=answer,
            rounds=result.rounds,
            executions=executions,
            suggestions=suggestions,
            model_mode=admission.settings.model_mode,
        )

    except (RateLimited, LimitsUnavailable) as e:
        raise public_error(e) from e
    except ModelDeadlineExceeded as e:
        return timeout_response(public_error(e))
    except ModelTimeoutError:
        return timeout_response(HTTPException(504, "模型生成超时，请稍后重试"))
    except InvalidSuggestionOutput as e:
        raise HTTPException(status_code=502, detail="模型建议格式无效") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Agent 执行失败，请稍后重试") from e


@router.post("/actions/remove-stock", response_model=ExecutionResult)
def execute_requested_removal(
    request: ExecutionRequest, actor: Actor = Depends(require_actor)
) -> JSONResponse:
    """Receive a separate client action; this handler is never exposed as a model tool."""
    result = execute_watchlist_removal(request, session_factory=SessionLocal, actor_id=actor.id)
    status_code = 200
    if result.error is not None:
        status_code = 500 if result.error.kind == "execution_error" else 404
    return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))
