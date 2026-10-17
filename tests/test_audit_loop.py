import json
from uuid import UUID

import pytest
from sqlalchemy import select

from app.agent_loop import run_agent_loop
from app.audit.repository import save_tool_execution
from app.database import SessionLocal, ToolAuditRecord, engine
from app.llm_client import ModelTimeoutError
from app.llm_types import ToolReply


def call(call_id, previous=10):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "calculate_change",
            "arguments": json.dumps({"previous_close": previous, "current_close": 9}),
        },
    }


class ScriptedClient:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.requests = 0

    def chat_with_tools(self, messages, tools):
        self.requests += 1
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return ToolReply.model_validate(reply)


def rows():
    with SessionLocal() as session:
        return list(session.scalars(select(ToolAuditRecord).order_by(ToolAuditRecord.id)))


def test_multiple_rounds_and_calls_share_run_id_and_persist_before_next_request():
    def save(run_id, record):
        save_tool_execution(run_id, record)
        assert len(rows()) == len(saved) + 1
        saved.append(record)

    saved = []
    client = ScriptedClient(
        {"tool_calls": [call("a"), call("b", 0)]},
        {"tool_calls": [call("c")]},
        {"content": "done"},
    )
    result = run_agent_loop(client, [], audit_writer=save)
    assert str(UUID(result.run_id)) == result.run_id
    assert result.rounds == 3
    assert [row.run_id for row in rows()] == [result.run_id] * 3
    assert [row.tool_call_id for row in rows()] == ["a", "b", "c"]
    assert [row.status for row in rows()] == ["success", "error", "success"]
    assert rows()[1].error["kind"] == "invalid_arguments"


def test_separate_runs_have_different_ids_and_direct_answer_saves_nothing():
    first = run_agent_loop(ScriptedClient({"content": "one"}), [], audit_writer=save_tool_execution)
    second = run_agent_loop(
        ScriptedClient({"content": "two"}), [], audit_writer=save_tool_execution
    )
    assert first.run_id != second.run_id
    assert rows() == []


def test_model_failure_keeps_committed_record():
    client = ScriptedClient({"tool_calls": [call("a")]}, ModelTimeoutError("timeout"))
    with pytest.raises(ModelTimeoutError):
        run_agent_loop(client, [], audit_writer=save_tool_execution)
    assert len(rows()) == 1
    assert rows()[0].tool_call_id == "a"


def test_round_limit_keeps_last_round_record():
    result = run_agent_loop(
        ScriptedClient({"tool_calls": [call("a")]}),
        [],
        max_rounds=1,
        audit_writer=save_tool_execution,
    )
    assert result.status == "max_rounds_exceeded"
    assert rows()[0].run_id == result.run_id


@pytest.mark.parametrize("fail_at", [1, 2])
def test_save_failure_stops_remaining_tools_and_model_requests(monkeypatch, fail_at):
    from app import tool_calling

    real_execute = tool_calling.execute_tool
    executed = []

    def execute(*args, **kwargs):
        executed.append(kwargs["tool_call_id"])
        return real_execute(*args, **kwargs)

    def save(run_id, record):
        if len(executed) == fail_at:
            raise RuntimeError("storage unavailable")
        return save_tool_execution(run_id, record)

    monkeypatch.setattr(tool_calling, "execute_tool", execute)
    client = ScriptedClient({"tool_calls": [call("a"), call("b"), call("c")]})
    with pytest.raises(RuntimeError, match="storage unavailable"):
        run_agent_loop(client, [], audit_writer=save)
    assert executed == ["a", "b"][:fail_at]
    assert client.requests == 1
    assert len(rows()) == fail_at - 1


def test_default_loop_does_not_open_database(monkeypatch):
    def fail_connect(*args, **kwargs):
        raise AssertionError("offline loop opened database")

    with monkeypatch.context() as patch:
        patch.setattr(engine, "connect", fail_connect)
        result = run_agent_loop(
            ScriptedClient({"tool_calls": [call("a")]}, {"content": "done"}),
            [],
        )
    assert result.status == "completed"
    assert str(UUID(result.run_id)) == result.run_id
    assert rows() == []
