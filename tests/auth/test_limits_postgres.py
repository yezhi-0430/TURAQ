"""Races use separate connections inside a unique dedicated-test-database schema."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from tests.auth.test_limits import config, limits
from tests.auth.test_postgres import pg  # noqa: F401


def race(call, count=8):
    barrier = Barrier(count)

    def run(index):
        barrier.wait(timeout=10)
        try:
            call(index)
            return True
        except limits().RateLimited:
            return False

    with ThreadPoolExecutor(count) as pool:
        return list(pool.map(run, range(count)))


def test_postgres_one_concurrent_request_across_connections(pg):  # noqa: F811
    m = limits()
    _, factory = pg
    assert sum(race(lambda _: m.admit(factory, 1, config()))) == 1


def test_postgres_daily_requests_and_site_attempts_are_atomic(pg):  # noqa: F811
    m = limits()
    _, factory = pg
    settings = config(model_user_daily_limit=3, model_user_minute_limit=100)

    def research(_):
        admission = m.admit(factory, 1, settings)
        admission.release()

    # Concurrency rejections are legitimate; retry sequentially to consume remaining seats.
    admitted = sum(race(research))
    while True:
        try:
            research(0)
            admitted += 1
        except m.RateLimited:
            break
    with pytest.raises(m.RateLimited):
        research(0)
    from sqlalchemy import select

    from app.auth.models import ModelBudget

    assert admitted == 3
    with factory() as db:
        assert len(db.scalar(select(ModelBudget).where(ModelBudget.key == "user:1")).events) == 3
    admissions = [m.admit(factory, i + 2, config(model_site_daily_limit=3)) for i in range(8)]
    assert sum(race(lambda i: admissions[i].before_attempt())) == 3
    for admission in admissions:
        admission.release()


def test_postgres_rolling_minute_limit_after_release(pg):  # noqa: F811
    m = limits()
    _, factory = pg
    for _ in range(2):
        m.admit(factory, 1, config()).release()
    assert sum(race(lambda _: m.admit(factory, 1, config()))) == 0


def test_postgres_tool_statement_respects_processing_deadline(pg):  # noqa: F811
    import time

    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    m = limits()
    _, factory = pg
    admission = m.admit(factory, 1, config(model_total_timeout_seconds=0.1))
    started = time.monotonic()
    with factory() as db:
        admission.bound_database_work(db)
        with pytest.raises(OperationalError):
            db.execute(text("SELECT pg_sleep(1)"))
    assert time.monotonic() - started < 1
    admission.release()


def test_postgres_sequential_statements_share_absolute_deadline(pg):  # noqa: F811
    import time

    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    m = limits()
    engine, factory = pg
    admission = m.admit(factory, 1, config(model_total_timeout_seconds=0.4))
    started = time.monotonic()
    with factory() as db:
        admission.bound_database_work(db)
        connection = db.connection()
        db.execute(text("SELECT pg_sleep(0.25)"))
        with pytest.raises((OperationalError, m.ModelDeadlineExceeded)):
            db.execute(text("SELECT pg_sleep(0.25)"))
        db.rollback()
        # A returned pooled connection must not retain the old request's hook/timeout.
        assert not list(connection.dispatch.before_cursor_execute)
        assert db.scalar(text("SHOW statement_timeout")) == "0"
        db.execute(text("SELECT pg_sleep(0.03)"))
    assert time.monotonic() - started < 0.65
    with engine.connect() as connection:
        assert not list(connection.dispatch.before_cursor_execute)
        assert connection.scalar(text("SHOW statement_timeout")) == "0"
    admission.release()


@pytest.mark.parametrize("finish", ["commit", "close"])
def test_postgres_deadline_hooks_do_not_survive_transaction_or_session(pg, finish):  # noqa: F811
    import time

    from sqlalchemy import text

    m = limits()
    _, factory = pg
    admission = m.admit(factory, 1, config())
    with factory() as db:
        admission.bound_database_work(db)
        # Repeated tool checks keep exactly one connection hook.
        admission.bound_database_work(db)
        connection = db.connection()
        assert len(list(connection.dispatch.before_cursor_execute)) == 1
        db.execute(text("SELECT 1"))
        getattr(db, finish)()
        assert not list(connection.dispatch.before_cursor_execute)
        assert "model_deadline" not in db.info
        admission.deadline = time.monotonic() - 1
        # The same Session may start fresh work without inheriting the expired guard.
        assert db.scalar(text("SHOW statement_timeout")) == "0"
        assert db.scalar(text("SELECT 1")) == 1
    admission.release()


def test_postgres_admission_lock_wait_does_not_restart_processing_clock(pg):  # noqa: F811
    import time

    from sqlalchemy import select

    from app.auth.models import ModelBudget

    m = limits()
    _, factory = pg
    m.admit(factory, 2, config()).release()  # Establish the shared site row.
    with factory() as blocker, blocker.begin():
        blocker.scalar(select(ModelBudget).where(
            ModelBudget.key == "site:attempts"
        ).with_for_update())
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(m.admit, factory, 1, config(model_total_timeout_seconds=0.1))
            time.sleep(0.2)
            blocker.commit()
            # PostgreSQL can cancel a fraction of a millisecond before the absolute
            # deadline; either generic fail-closed response is safe for that boundary.
            with pytest.raises((m.ModelDeadlineExceeded, m.LimitsUnavailable)):
                future.result(timeout=5)


def test_postgres_audit_flush_uses_updated_deadline(pg):  # noqa: F811
    from sqlalchemy import func, select, text
    from sqlalchemy.exc import OperationalError

    from app.audit.repository import save_tool_execution
    from app.database import ToolAuditRecord
    from app.tools.executor import ToolExecutionRecord

    m = limits()
    _, factory = pg
    with factory() as db, db.begin():
        db.execute(text("""
            CREATE FUNCTION slow_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN PERFORM pg_sleep(0.25); RETURN NEW; END $$
        """))
        db.execute(text("""
            CREATE TRIGGER slow_audit BEFORE INSERT ON tool_audit_records
            FOR EACH ROW EXECUTE FUNCTION slow_audit()
        """))
    admission = m.admit(factory, 1, config(model_total_timeout_seconds=0.4))

    def before_work(db):
        admission.bound_database_work(db)
        db.execute(text("SELECT pg_sleep(0.25)"))

    record = ToolExecutionRecord(tool_name="calculate_change", arguments="{}", status="success",
                                 result={}, error=None, duration_ms=0)
    with pytest.raises((OperationalError, m.ModelDeadlineExceeded)):
        save_tool_execution("test-only", record, session_factory=factory, before_work=before_work)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ToolAuditRecord)) == 0
    admission.release()


def test_postgres_delayed_reservation_closes_stream_before_new_lease_dispatch(pg):  # noqa: F811
    import asyncio
    import time
    from datetime import timedelta
    from threading import Event

    import httpx
    from sqlalchemy import event, func, select, update

    from app.auth.models import ModelBudget
    from app.llm_client import QwenModelClient

    m = limits()
    _, factory = pg
    settings = config(model_total_timeout_seconds=10, model_user_minute_limit=100)
    old = m.admit(factory, 1, settings)
    with factory() as db, db.begin():
        expiry = db.scalar(select(func.clock_timestamp())) + timedelta(seconds=4)
        db.execute(update(ModelBudget).where(ModelBudget.key == "user:1").values(
            lease_expires_at=expiry
        ))
    started = time.monotonic()
    active = Event()
    closed = Event()
    calls = []

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            active.set()
            try:
                while True:
                    await asyncio.sleep(0.02)
                    yield b" "
            finally:
                active.clear()
                closed.set()

    async def respond(request):
        calls.append(True)
        if len(calls) == 1:
            return httpx.Response(200, stream=SlowStream())
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    def paused_factory():
        db = factory()
        event.listen(db, "before_commit", lambda _: time.sleep(0.8))
        return db

    old.factory = paused_factory

    def fresh_request(client):
        time.sleep(max(0, started + 4.1 - time.monotonic()))
        fresh = m.admit(factory, 1, settings)
        try:
            assert closed.is_set() and not active.is_set(), "old HTTP outlived its lease"
            assert QwenModelClient("test-only", client).with_admission(fresh).chat([]) == "ok"
        finally:
            fresh.release()

    try:
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with factory() as blocker, blocker.begin():
                blocker.scalar(select(ModelBudget).where(
                    ModelBudget.key == "site:attempts"
                ).with_for_update())
                with ThreadPoolExecutor(2) as pool:
                    fresh = pool.submit(fresh_request, client)
                    old_call = pool.submit(QwenModelClient("test-only", client)
                                           .with_admission(old).chat, [])
                    time.sleep(1.3)
                    blocker.commit()
                    with pytest.raises(m.ModelDeadlineExceeded):
                        old_call.result(timeout=8)
                    fresh.result(timeout=8)
        assert calls == [True, True]
        assert closed.is_set() and not active.is_set()
    finally:
        old.factory = factory
        old.release()
