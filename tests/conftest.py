import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ["DATABASE_NAME"] = "a_share_risk_agent_test"

from app.auth.dependencies import Actor, require_actor  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.auth.service import utcnow  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_actor] = lambda: Actor(1, "test-owner@example.com", True)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def error_client() -> TestClient:
    app.dependency_overrides[require_actor] = lambda: Actor(1, "test-owner@example.com", True)
    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clean_test_database(upgrade_test_schema, monkeypatch):
    from app.database import Base, SessionLocal, engine

    Base.metadata.create_all(engine)

    def clear_tables() -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE TABLE users, invites, auth_throttle_buckets, tool_audit_records, "
                    "watchlist_items, stocks, watchlists "
                    "RESTART IDENTITY CASCADE"
                )
            )

    clear_tables()
    with SessionLocal() as db:
        db.add(
            User(
                id=1,
                email="test-owner@example.com",
                password_hash="test-only-unused",
                verified=True,
                is_admin=True,
                pending_expires_at=utcnow(),
            )
        )
        db.commit()

    async def trusted_quotes(symbols):
        names = {"600519.SH": "贵州茅台", "000001.SZ": "测试股票", "600000.SH": "浦发银行"}
        return {
            "quotes": [
                {"symbol": symbol, "name": names[symbol], "kind": "stock", "stale": False}
                for symbol in symbols
                if symbol in names
            ]
        }

    monkeypatch.setattr("app.market_api.service.quotes", trusted_quotes)
    yield
    clear_tables()


@pytest.fixture(scope="session")
def upgrade_test_schema():

    from app.database import Base, SessionLocal, engine
    from app.schema_upgrade import upgrade_database

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.get(User, 1):
            db.add(
                User(
                    id=1,
                    email="migration-test-owner@example.com",
                    password_hash="test-only-unused",
                    verified=True,
                    is_admin=True,
                    pending_expires_at=utcnow(),
                )
            )
            db.commit()
    upgrade_database(engine, owner_id=1)
