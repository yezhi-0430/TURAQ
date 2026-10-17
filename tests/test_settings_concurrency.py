"""Real PostgreSQL transaction test; parent fixtures use the dedicated test database."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.dependencies import Actor
from app.config import Settings
from app.database import SessionLocal, engine
from app.paper_trading import api
from app.paper_trading.models import PaperAccount


def test_parallel_account_creation_respects_configured_cap(monkeypatch):
    assert engine.url.database == "a_share_risk_agent_test"
    start = Barrier(2)
    counted = Barrier(2)

    class RacingSession(Session):
        def scalar(self, statement, *args, **kwargs):
            result = super().scalar(statement, *args, **kwargs)
            if "count(" in str(statement) and "paper_accounts" in str(statement):
                # Without an owner lock both requests observe 0 before either inserts.
                # With a lock the first proceeds after this bounded wait, then the second sees 1.
                try:
                    counted.wait(timeout=1)
                except BrokenBarrierError:
                    pass
            return result

    monkeypatch.setattr(api, "SessionLocal", sessionmaker(bind=engine, class_=RacingSession))
    settings = Settings(paper_max_accounts=1)

    def create(name):
        start.wait(timeout=5)
        try:
            api.create_account(
                api.AccountRequest(name=name, initial_capital=10000),
                Actor(1, "test-owner@example.com", True),
                settings,
            )
            return 201
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ["parallel-a", "parallel-b"]))
    assert sorted(results) == [201, 409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PaperAccount)) == 1
