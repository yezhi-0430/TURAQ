"""Administrative aggregation uses actual PostgreSQL timezone semantics."""

from datetime import UTC, datetime, timedelta

from tests.auth.test_postgres import pg  # noqa: F401


def test_admin_postgres_stats_use_shanghai_day_and_preserve_unknown_cost(pg, monkeypatch):  # noqa: F811
    from app.admin import stats_service
    from app.auth.models import Invite, User
    from app.database import ToolAuditRecord

    _, factory = pg
    now = datetime(2026, 10, 12, 8, tzinfo=UTC)
    monkeypatch.setattr(stats_service, "utcnow", lambda: now)
    with factory.begin() as db:
        db.add(
            User(
                id=1,
                email="synthetic@example.com",
                password_hash="unused",
                verified=True,
                pending_expires_at=now,
            )
        )
        db.flush()
        db.add(Invite(digest="synthetic", max_uses=3, uses=1, expires_at=now + timedelta(days=1)))
        for i, hour, minute, status in [(1, 16, 0, "success"), (2, 15, 59, "error")]:
            db.add(
                ToolAuditRecord(
                    run_id=str(i),
                    actor_id=1,
                    tool_name="calculate_change",
                    arguments="{}",
                    status=status,
                    duration_ms=1,
                    created_at=datetime(2026, 10, 11, hour, minute, tzinfo=UTC),
                )
            )
    with factory() as db:
        summary = stats_service.overview(db)
        assert summary["tool_attempts_today"] == 1
        assert summary["available_slots"] == 2
        assert summary["estimated_cost"] is None
        usage = stats_service.llm_usage(db)
        assert usage["daily_trend"][-1] == {"date": "2026-10-12", "calls": 1}
        assert usage["daily_trend"][-2] == {"date": "2026-10-11", "calls": 1}
        assert usage["by_user"][0]["success_rate"] == 0.5
