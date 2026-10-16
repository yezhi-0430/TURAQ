import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import Actor, get_session_factory, require_actor
from app.auth.models import User
from app.auth.service import utcnow
from app.database import Base, Stock, Watchlist, WatchlistItem
from app.llm_client import FakeModelClient
from app.model_limits import model_admission
from app.risk_api import get_model_client
from tests.unit.admission import offline_admission


@pytest.fixture(autouse=True)
def clean_test_database():
    # This module owns isolated SQLite storage; never touch the shared PostgreSQL fixture.
    yield


@pytest.fixture
def risk_env():
    from app.main import create_app

    application = create_app()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        for i in (1, 2):
            db.add(
                User(
                    id=i,
                    email=f"{i}@example.com",
                    password_hash="unused",
                    verified=True,
                    pending_expires_at=utcnow(),
                )
            )
        db.add_all(
            [
                Stock(id=1, symbol="000001.SZ", name="平安银行"),
                Stock(id=2, symbol="600000.SH", name="浦发银行"),
            ]
        )
        db.flush()
        db.add_all(
            [Watchlist(id=1, name="我的", owner_id=1), Watchlist(id=2, name="他人", owner_id=2)]
        )
        db.flush()
        db.add_all(
            [WatchlistItem(watchlist_id=1, stock_id=1), WatchlistItem(watchlist_id=2, stock_id=2)]
        )
        db.commit()
    actor = [1]
    application.dependency_overrides[require_actor] = lambda: Actor(actor[0], "u@e.com", False)
    application.dependency_overrides[get_session_factory] = lambda: factory
    admission = offline_admission()
    admission.settings.model_provider = "qwen"
    application.dependency_overrides[model_admission] = lambda: admission
    reply = {
        "facts": ["营收下降"],
        "inferences": ["压力上升"],
        "unknowns": ["原因待核实"],
        "risk_level": "high",
        "sources": ["模型声称的来源"],
    }
    application.dependency_overrides[get_model_client] = lambda: FakeModelClient(json.dumps(reply))
    with TestClient(application) as client:
        yield client, actor, application, admission
    engine.dispose()


def submit(client, **extra):
    body = dict(
        input_text="原始公告：营收下降",
        title="季度公告",
        risk_type="announcement",
        symbol="000001.SZ",
        published_date="2026-10-01",
        source_url="https://example.com/report",
        request_id=str(uuid4()),
    )
    body.update(extra)
    return client.post("/api/v1/risk/analyses", json=body)


def test_history_evidence_scope_and_isolation(risk_env):
    c, actor, _, _ = risk_env
    response = submit(c)
    assert response.status_code == 201, response.text
    event = response.json()
    eid = event["id"]
    assert event["result"]["risk_level"] == "high"
    assert event["evidence"][0]["verification"] == "user_provided"
    assert event["evidence"][0]["excerpt"] == "原始公告：营收下降"
    assert event["model_sources"] == ["模型声称的来源"]
    listing = c.get("/api/v1/risk/events?group_id=1").json()
    assert listing["total"] == 1
    assert listing["overview"] == dict(monitored_stocks=1, pending=1, high=1, unknown=0)
    assert listing["scan"]["status"] == "not_connected"
    assert c.get(f"/api/v1/risk/events/{eid}").json()["input_text"] == "原始公告：营收下降"
    assert c.patch(f"/api/v1/risk/events/{eid}", json={"status": "viewed"}).status_code == 200
    assert c.get("/api/v1/risk/events?status=unread").json()["total"] == 0
    assert c.get("/api/v1/risk/events?status=viewed").json()["overview"]["high"] == 1
    actor[0] = 2
    assert c.get("/api/v1/risk/events").json()["total"] == 0
    assert c.get("/api/v1/risk/analyses").json()["items"] == []
    assert c.get(f"/api/v1/risk/events/{eid}").status_code == 404
    assert c.patch(f"/api/v1/risk/events/{eid}", json={"status": "following"}).status_code == 404
    assert c.get("/api/v1/risk/events?group_id=1").status_code == 404
    assert submit(c).status_code == 404


def test_validation_and_idempotency(risk_env):
    c, _, _, _ = risk_env
    key = str(uuid4())
    one = submit(c, request_id=key)
    two = submit(c, request_id=key)
    assert one.status_code == 201
    assert two.json()["id"] == one.json()["id"]
    assert c.get("/api/v1/risk/events").json()["total"] == 1
    assert submit(c, request_id=key, input_text="不同内容").status_code == 409
    for extra in [
        {"input_text": " "},
        {"input_text": "字" * 20001},
        {"source_url": "javascript:alert(1)"},
        {"source_url": "https://u:p@a.com"},
        {"risk_type": "sentiment"},
        {"published_date": "bad"},
    ]:
        assert submit(c, **extra).status_code == 422
    assert c.get("/api/v1/risk/events?date_from=2026-10-10&date_to=2026-10-01").status_code == 422


def test_failure_history_and_fake_mode(risk_env):
    c, _, app, admission = risk_env
    app.dependency_overrides[get_model_client] = lambda: FakeModelClient("bad json")
    assert submit(c).status_code == 502
    history = c.get("/api/v1/risk/analyses").json()["items"]
    assert history[0]["generation_status"] == "failed"
    assert c.get("/api/v1/risk/events").json()["total"] == 0
    admission.settings.model_provider = "fake"
    app.dependency_overrides[get_model_client] = lambda: FakeModelClient(
        json.dumps(
            {
                "facts": ["虚假事实"],
                "inferences": [],
                "unknowns": [],
                "sources": [],
                "risk_level": "high",
            }
        )
    )
    event = submit(c).json()
    assert event["model_mode"] == "fake"
    assert event["risk_level"] == "unknown"
    assert c.get("/api/v1/risk/events").json()["overview"]["high"] == 0


def test_sort_pagination_filters(risk_env):
    c, _, _, _ = risk_env
    first = submit(c).json()
    second = submit(c, risk_type="financial", published_date="2026-09-01").json()
    c.patch(f"/api/v1/risk/events/{second['id']}", json={"status": "viewed"})
    data = c.get("/api/v1/risk/events?page_size=1").json()
    assert data["total"] == 2
    assert data["items"][0]["id"] == first["id"]
    data = c.get("/api/v1/risk/events?risk_type=financial&date_to=2026-09-30").json()
    assert data["total"] == 1
    assert data["overview"]["pending"] == 0
    assert c.get("/api/v1/risk/events?symbol=600000.SH").json()["total"] == 0


@pytest.mark.parametrize(
    "error,status", [("timeout", 504), ("connection", 502), ("authentication", 503)]
)
def test_model_errors_are_saved(risk_env, error, status):
    from app.llm_client import ModelAuthenticationError, ModelConnectionError, ModelTimeoutError

    c, _, app, _ = risk_env
    failures = dict(
        timeout=ModelTimeoutError,
        connection=ModelConnectionError,
        authentication=ModelAuthenticationError,
    )

    class FailingModel:
        def chat(self, messages):
            raise failures[error]("private upstream diagnostic")

    app.dependency_overrides[get_model_client] = FailingModel
    response = submit(c)
    assert response.status_code == status
    assert "private upstream" not in response.text
    assert c.get("/api/v1/risk/analyses").json()["items"][0]["generation_status"] == "failed"


def test_additive_risk_schema_preserves_existing_tables():
    from app.risk_schema import upgrade_risk_tables

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[t for name, t in Base.metadata.tables.items() if not name.startswith("risk_")],
    )
    with sessionmaker(bind=engine)() as db:
        db.add(Stock(symbol="TEST", name="existing stock"))
        db.commit()
    upgrade_risk_tables(engine)
    upgrade_risk_tables(engine)
    with sessionmaker(bind=engine)() as db:
        assert db.query(Stock).one().name == "existing stock"
    engine.dispose()


def test_deadline_during_persistence_returns_timeout_and_records_failure(risk_env):
    from app.model_limits import ModelDeadlineExceeded

    c, _, _, admission = risk_env
    count = 0

    def bounded(db):
        nonlocal count
        count += 1
        if count > 1:
            raise ModelDeadlineExceeded("save deadline")

    admission.bound_database_work = bounded
    response = submit(c)
    assert response.status_code == 504
    assert c.get("/api/v1/risk/analyses").json()["items"][0]["generation_status"] == "failed"
    assert c.get("/api/v1/risk/events").json()["total"] == 0


def test_database_timeout_during_save_records_failure(risk_env, monkeypatch):
    from sqlalchemy.exc import OperationalError

    c, _, _, _ = risk_env

    def timeout(*args):
        raise OperationalError("save", {}, Exception("private database diagnostic"))

    monkeypatch.setattr("app.risk_workbench.save_result", timeout)
    response = submit(c)
    assert response.status_code == 503
    assert "private database" not in response.text
    assert c.get("/api/v1/risk/analyses").json()["items"][0]["generation_status"] == "failed"
