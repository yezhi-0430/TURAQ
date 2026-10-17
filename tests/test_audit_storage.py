from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.audit.repository import save_tool_execution
from app.database import SessionLocal, Stock, ToolAuditRecord, engine
from app.tools.executor import execute_tool


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("calculate_change", '{"previous_close":"10","current_close":"9"}'),
        ("calculate_change", '{"previous_close":0,"current_close":9}'),
        ("calculate_change", "{broken json"),
        ("unknown", "{}"),
    ],
)
def test_persists_execution_across_sessions(name, arguments):
    record = execute_tool(name, arguments, tool_call_id="call_1")
    run_id = str(uuid4())
    before = datetime.now(UTC)
    record_id = save_tool_execution(run_id, record)
    with SessionLocal() as session:
        saved = session.get(ToolAuditRecord, record_id)
        assert saved.run_id == run_id
        for key, value in record.model_dump(mode="json").items():
            assert getattr(saved, key) == value
        assert before <= saved.created_at <= datetime.now(UTC)
        if record.status == "success":
            assert saved.result == {"change_percent": "-10.0000"}


def test_allows_repeated_call_ids_and_nullable_call_id():
    run_id = str(uuid4())
    for call_id in ["same", "same", None]:
        save_tool_execution(run_id, execute_tool("unknown", "{}", tool_call_id=call_id))
    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ToolAuditRecord)
                .where(ToolAuditRecord.run_id == run_id)
            )
            == 3
        )


@pytest.mark.parametrize("assignment", ["status = 'invalid'", "duration_ms = -1"])
def test_database_rejects_invalid_values(assignment):
    record_id = save_tool_execution(str(uuid4()), execute_tool("unknown", "{}"))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(f"UPDATE tool_audit_records SET {assignment} WHERE id = :id"),
            {"id": record_id},
        )


def test_audit_does_not_commit_business_session():
    with SessionLocal() as business:
        business.add(Stock(symbol="AUDIT.TEST", name="uncommitted"))
        business.flush()
        record_id = save_tool_execution(str(uuid4()), execute_tool("unknown", "{}"))
        business.rollback()
    with SessionLocal() as session:
        assert session.scalar(select(Stock).where(Stock.symbol == "AUDIT.TEST")) is None
        assert session.get(ToolAuditRecord, record_id) is not None


def test_commit_failure_rolls_back_new_record_and_preserves_previous():
    run_id = str(uuid4())
    record = execute_tool("unknown", "{}")
    saved_id = save_tool_execution(run_id, record)

    class FailingSession(Session):
        pass

    def fail_commit(session):
        raise RuntimeError("audit commit failed")

    event.listen(FailingSession, "before_commit", fail_commit)
    factory = sessionmaker(bind=engine, class_=FailingSession)
    with pytest.raises(RuntimeError, match="audit commit failed"):
        save_tool_execution(run_id, record, session_factory=factory)
    with SessionLocal() as session:
        assert session.get(ToolAuditRecord, saved_id) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ToolAuditRecord)
                .where(ToolAuditRecord.run_id == run_id)
            )
            == 1
        )
