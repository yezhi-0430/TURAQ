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
    race(research)
    while True:
        try:
            research(0)
        except m.RateLimited:
            break
    with pytest.raises(m.RateLimited):
        research(0)
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
