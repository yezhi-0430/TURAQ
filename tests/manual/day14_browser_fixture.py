"""Loopback-only manual QA: real chat/loop/executor/audit with synthetic identity/model.

Run: python -m tests.manual.day14_browser_fixture [--check]
Open http://127.0.0.1:8892; login qa-day14@example.test / day14-test.
Prompts containing 错误 reject zero; 轮数 exhausts five rounds; others recover.
This fixture is not an authentication test or a deployable application.
"""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def build_fixture():
    os.environ.update(
        DATABASE_HOST="127.0.0.1", DATABASE_PORT="1", DATABASE_NAME="day14_unused",
        DATABASE_USER="test", DATABASE_PASSWORD="test", MODEL_PROVIDER="fake",
        DASHSCOPE_API_KEY="",
    )
    import httpx
    from fastapi import FastAPI, HTTPException
    from fastapi.staticfiles import StaticFiles
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import agent_api, database
    from app.agent_policy import ChatRequest
    from app.auth.dependencies import Actor
    from app.auth.models import User
    from app.config import Settings
    from app.llm_types import ToolReply
    from app.model_limits import Admission

    def block_network(*args, **kwargs):
        raise AssertionError("This fixture must never make outbound HTTP requests")

    httpx.Client.send = block_network
    httpx.AsyncClient.send = block_network
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    database.SessionLocal = agent_api.SessionLocal = factory
    with factory.begin() as db:
        db.add(User(id=1, email="qa-day14@example.test", password_hash="unused", verified=True))
    settings = Settings(_env_file=None, model_provider="fake")

    class ScriptedModel:
        def __init__(self):
            self.calls = 0

        def chat_with_tools(self, messages, tools):
            self.calls += 1
            prompt = next(m["content"] for m in reversed(messages) if m["role"] == "user")
            invalid = "错误" in prompt
            if "轮数" not in prompt and self.calls > 1:
                return ToolReply(content="隔离验收：前期价格必须大于 0，无法计算涨跌幅。"
                                 if invalid else "隔离验收：Python 计算结果为下跌 10%。")
            return ToolReply.model_validate({"tool_calls": [{
                "id": f"fixture-{self.calls}", "type": "function", "function": {
                    "name": "calculate_change", "arguments": json.dumps({
                        "previous_close": 0 if invalid else 10, "current_close": 9,
                    }),
                },
            }]})

    agent_api.get_client = ScriptedModel
    app = FastAPI()
    results = []
    identity = {"id": 1, "email": "qa-day14@example.test", "is_admin": False}
    state = {"user": None, "csrf_token": "fixture-only", "mail_configured": False,
             "model_mode": "fake"}

    @app.get("/api/v1/auth/session")
    def session():
        return state

    @app.post("/api/v1/auth/login")
    def login(body: dict):
        if body != {"email": identity["email"], "password": "day14-test"}:
            raise HTTPException(401, "Only synthetic fixture credentials are accepted")
        state["user"] = identity
        return state

    @app.post("/api/v1/agent/chat")
    def chat(body: ChatRequest):
        admission = Admission(factory, 1, settings, "fixture", datetime.now(UTC)
                              + timedelta(seconds=65))
        response = agent_api.chat(body, Actor(1, identity["email"], False), admission)
        with factory() as db:
            rows = db.scalars(select(database.ToolAuditRecord).where(
                database.ToolAuditRecord.run_id == response.run_id)).all()
            assert len(rows) == len(response.executions)
            assert [row.status for row in rows] == [item.status for item in response.executions]
        results.append(response.model_dump(mode="json"))
        return response

    @app.get("/fixture/results")
    def report():
        return results

    @app.get("/api/v1/watchlists")
    def watchlists():
        return []

    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "frontend",
                              html=True))
    return app, chat, ChatRequest


if __name__ == "__main__":
    app, chat, request_type = build_fixture()
    if "--check" in sys.argv:
        for prompt, expected, count in [("错误", "completed", 1),
                                        ("轮数", "max_rounds_exceeded", 5),
                                        ("恢复", "completed", 1)]:
            result = chat(request_type(messages=[{"role": "user", "content": prompt}]))
            assert result.status == expected
            assert len(result.executions) == count
            if prompt == "错误":
                assert result.executions[0].status == "error"
                assert result.executions[0].result is None
                assert "invalid_arguments" in result.executions[0].error
            elif prompt == "轮数":
                assert result.rounds == 5 and result.answer is None
            else:
                assert json.loads(result.executions[0].result)["change_percent"] == "-10.0000"
            print(prompt, result.status, "audit records:", count)
    else:
        import uvicorn

        uvicorn.run(app, host="127.0.0.1", port=8892)
