"""Save audit records without committing a caller's business transaction."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.database import SessionLocal, ToolAuditRecord
from app.tools.executor import ToolExecutionRecord


def save_tool_execution(
    run_id: str,
    record: ToolExecutionRecord,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
) -> int:
    """Return the committed row ID; rollback and propagate any storage failure."""
    row = ToolAuditRecord(run_id=run_id, **record.model_dump(mode="json"))
    with session_factory() as session, session.begin():
        session.add(row)
        session.flush()
        record_id = row.id
    return record_id
