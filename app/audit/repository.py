"""Save audit records without committing a caller's business transaction."""

from collections.abc import Callable
from datetime import datetime

from pydantic import ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, ToolAuditRecord
from app.tools.executor import ToolExecutionRecord


def save_tool_execution(
    run_id: str,
    record: ToolExecutionRecord,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    actor_id: int | None = None,
) -> int:
    """Return the committed row ID; rollback and propagate any storage failure."""
    row = ToolAuditRecord(run_id=run_id, actor_id=actor_id, **record.model_dump(mode="json"))
    with session_factory() as session, session.begin():
        session.add(row)
        session.flush()
        record_id = row.id
    return record_id


class AuditRecord(ToolExecutionRecord):
    """A serializable snapshot that remains usable after its session closes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    created_at: datetime


def list_tool_executions(
    run_id: str,
    *,
    after_id: int = 0,
    limit: int = 20,
    session_factory: Callable[[], Session] = SessionLocal,
    actor_id: int | None = None,
) -> list[AuditRecord]:
    """Read one bounded page for a run, excluding the last seen row ID."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit 必须为 1 到 100 的整数")
    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id 必须为非负整数")
    statement = (
        select(ToolAuditRecord)
        .where(
            ToolAuditRecord.run_id == run_id,
            ToolAuditRecord.id > after_id,
            ToolAuditRecord.actor_id == actor_id,
        )
        .order_by(ToolAuditRecord.id)
        .limit(limit)
    )
    with session_factory() as session:
        return [AuditRecord.model_validate(row) for row in session.scalars(statement)]
