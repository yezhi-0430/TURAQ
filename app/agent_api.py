"""
FastAPI 路由：为前端提供 Agent 对话接口
"""
import json
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent_loop import run_agent_loop
from app.config import Settings
from app.database import SessionLocal
from app.llm_client import create_model_client, ModelClient
from app.audit.repository import save_tool_execution

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

# 全局 HTTP 客户端和模型客户端缓存
_http_client: httpx.Client | None = None
_model_client: ModelClient | None = None


def get_client() -> ModelClient:
    """获取或创建 ModelClient 实例（单例）"""
    global _http_client, _model_client

    if _model_client is None:
        settings = Settings()
        if _http_client is None:
            _http_client = httpx.Client()
        _model_client = create_model_client(settings, _http_client)

    return _model_client


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    max_rounds: int = 5


class ToolExecution(BaseModel):
    tool_name: str
    arguments: dict
    result: str | None = None
    error: str | None = None
    status: str
    duration_ms: float


class ChatResponse(BaseModel):
    run_id: str
    status: str
    answer: str | None
    rounds: int
    executions: list[ToolExecution]


@router.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """
    接收前端消息，运行 Agent 循环，返回结果和工具调用记录
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="消息列表不能为空")

    # 转换为标准消息格式
    messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

    try:
        # 获取 LLM 客户端
        client = get_client()

        # 运行 Agent 循环
        with SessionLocal() as session:
            result = run_agent_loop(
                client=client,
                messages=messages,
                session=session,
                max_rounds=request.max_rounds,
                audit_writer=save_tool_execution,
            )

        # 转换工具执行记录
        executions = [
            ToolExecution(
                tool_name=exec.tool_name,
                arguments=json.loads(exec.arguments),
                result=json.dumps(exec.result) if exec.status == "success" and exec.result else None,
                error=json.dumps(exec.error.model_dump()) if exec.status == "error" and exec.error else None,
                status=exec.status,
                duration_ms=exec.duration_ms,
            )
            for exec in result.executions
        ]

        return ChatResponse(
            run_id=result.run_id,
            status=result.status,
            answer=result.answer,
            rounds=result.rounds,
            executions=executions,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 执行失败: {str(e)}")
