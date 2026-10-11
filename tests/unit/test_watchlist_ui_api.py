import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.dependencies import Actor, require_actor
from app.database import Base, Stock


@pytest.fixture
def watch_client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all(
            [Stock(symbol="600519.SH", name="贵州茅台"), Stock(symbol="000001.SZ", name="平安银行")]
        )
        db.commit()
    application = main.create_app()
    application.dependency_overrides[require_actor] = lambda: Actor(1, "unit@example.com", True)
    with TestClient(application) as client:
        yield client
    engine.dispose()


def test_group_lifecycle_and_stock_isolation(watch_client):
    c = watch_client
    a = c.post("/api/v1/watchlists", json={"name": "  核心  "}).json()
    b = c.post("/api/v1/watchlists", json={"name": "观察"}).json()
    assert a["name"] == "核心"
    for group in (a, b):
        assert (
            c.post(
                f"/api/v1/watchlists/{group['id']}/stocks",
                json={"symbol": "600519.SH", "name": "贵州茅台"},
            ).status_code
            == 201
        )
    items = c.get(f"/api/v1/watchlists/{a['id']}/stocks")
    assert items.status_code == 200 and items.json()[0]["symbol"] == "600519.SH"
    assert c.delete(f"/api/v1/watchlists/{a['id']}/stocks/600519.SH").status_code == 204
    assert c.get(f"/api/v1/watchlists/{a['id']}/stocks").json() == []
    assert len(c.get(f"/api/v1/watchlists/{b['id']}/stocks").json()) == 1
    assert c.get("/api/v1/stocks", params={"query": "茅台"}).json() == [
        {"symbol": "600519.SH", "name": "贵州茅台"}
    ]
    assert c.get("/api/v1/stocks", params={"query": "600519"}).json()[0]["name"] == "贵州茅台"


def test_validation_and_missing_groups(watch_client):
    c = watch_client
    assert c.post("/api/v1/watchlists", json={"name": "   "}).status_code == 422
    assert c.get("/api/v1/stocks", params={"query": "不存在"}).json() == []
    assert c.get("/api/v1/stocks", params={"query": "%"}).json() == []
    assert c.get("/api/v1/watchlists/999/stocks").status_code == 404


def test_rename_and_delete_group_keep_stock_data(watch_client):
    c = watch_client
    group = c.post("/api/v1/watchlists", json={"name": "原名"}).json()
    c.post(
        f"/api/v1/watchlists/{group['id']}/stocks", json={"symbol": "000001.SZ", "name": "平安银行"}
    )
    assert (
        c.patch(f"/api/v1/watchlists/{group['id']}", json={"name": "  新名  "}).json()["name"]
        == "新名"
    )
    assert c.patch(f"/api/v1/watchlists/{group['id']}", json={"name": "  "}).status_code == 422
    assert c.delete(f"/api/v1/watchlists/{group['id']}").status_code == 204
    assert c.get(f"/api/v1/watchlists/{group['id']}/stocks").status_code == 404
    assert c.get("/api/v1/stocks", params={"query": "平安"}).json()[0]["symbol"] == "000001.SZ"
    assert c.patch("/api/v1/watchlists/999", json={"name": "new"}).status_code == 404
    assert c.delete("/api/v1/watchlists/999").status_code == 404
