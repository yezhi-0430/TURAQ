import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ["DATABASE_NAME"] = "a_share_risk_agent_test"

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def error_client() -> TestClient:
    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_test_database(upgrade_test_schema):
    from app.database import Base, engine

    Base.metadata.create_all(engine)

    def clear_tables() -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE TABLE tool_audit_records, watchlist_items, stocks, watchlists "
                    "RESTART IDENTITY CASCADE"
                )
            )

    clear_tables()
    yield
    clear_tables()


@pytest.fixture(scope="session")
def upgrade_test_schema():
    from app.database import engine
    from app.schema_upgrade import upgrade_database

    upgrade_database(engine)
