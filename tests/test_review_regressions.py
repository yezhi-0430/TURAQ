from app.auth.dependencies import Actor, require_actor
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, select
from sqlalchemy.orm import Session, sessionmaker

from app import main
from app.database import DailyPrice, SessionLocal, Stock, Watchlist, WatchlistItem, engine


@pytest.fixture
def imported_stock():
    with SessionLocal() as session:
        session.add(Stock(symbol="000001.SZ", name="测试股票"))
        session.commit()


def price_payload(**overrides):
    values = {
        "trade_date": "2026-09-25",
        "open": "10",
        "high": "11",
        "low": "9",
        "close": "10",
        "volume": 100,
    }
    values.update(overrides)
    return values


def test_numeric_http_prices_keep_all_decimal_digits(client, imported_stock):
    raw = (
        '{"trade_date":"2026-09-25","open":12345678901234.5678,'
        '"high":12345678901234.5678,"low":12345678901234.5678,'
        '"close":12345678901234.5678,"volume":100}'
    )
    response = client.post(
        "/api/v1/stocks/000001.SZ/daily-prices",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 201
    rows = client.get("/api/v1/stocks/000001.SZ/daily-prices").json()
    assert rows[0]["close"] == "12345678901234.5678"


@pytest.mark.parametrize("price", ["0", "-1", "100000000000000", "9.00001", "NaN"])
def test_invalid_prices_are_rejected_before_storage(client, imported_stock, price):
    payload = price_payload(**dict.fromkeys(("open", "high", "low", "close"), price))
    response = client.post("/api/v1/stocks/000001.SZ/daily-prices", json=payload)
    assert response.status_code == 422
    with SessionLocal() as session:
        assert session.scalar(select(DailyPrice)) is None


def test_overprecise_numeric_http_price_is_rejected(client, imported_stock):
    raw = (
        '{"trade_date":"2026-09-25","open":10,"high":11,"low":9,'
        '"close":9.0000000000000001,"volume":100}'
    )
    response = client.post(
        "/api/v1/stocks/000001.SZ/daily-prices",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("value", ["1e9999", "1e-9999"])
def test_extreme_exponents_return_validation_error(error_client, imported_stock, value):
    raw = f'{{"trade_date":"2026-09-25","open":10,"high":11,"low":9,"close":{value},"volume":100}}'
    response = error_client.post(
        "/api/v1/stocks/000001.SZ/daily-prices",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_constants_return_validation_error(error_client, imported_stock, constant):
    raw = (
        f'{{"trade_date":"2026-09-25","open":10,"high":11,"low":9,"close":{constant},"volume":100}}'
    )
    response = error_client.post(
        "/api/v1/stocks/000001.SZ/daily-prices",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides", [{"high": "8"}, {"low": "12"}, {"open": "12"}, {"close": "8"}]
)
def test_inconsistent_ohlc_is_rejected(client, imported_stock, overrides):
    response = client.post("/api/v1/stocks/000001.SZ/daily-prices", json=price_payload(**overrides))
    assert response.status_code == 422


@pytest.mark.parametrize("volume", [2147483648, 9223372036854775807])
def test_bigint_volumes_round_trip(error_client, imported_stock, volume):
    response = error_client.post(
        "/api/v1/stocks/000001.SZ/daily-prices", json=price_payload(volume=volume)
    )
    assert response.status_code == 201
    assert error_client.get("/api/v1/stocks/000001.SZ/daily-prices").json()[0]["volume"] == volume


def test_volume_over_bigint_is_rejected(error_client, imported_stock):
    response = error_client.post(
        "/api/v1/stocks/000001.SZ/daily-prices",
        json=price_payload(volume=9223372036854775808),
    )
    assert response.status_code == 422


def test_volume_column_uses_bigint():
    assert isinstance(DailyPrice.__table__.c.volume.type, BigInteger)


def test_stock_codes_are_normalized_across_add_query_and_remove(client):
    group = client.post("/api/v1/watchlists", json={"name": "大小写测试"}).json()["id"]
    added = client.post(
        f"/api/v1/watchlists/{group}/stocks", json={"symbol": " 000001.sz ", "name": "测试股票"}
    )
    assert added.status_code == 201
    assert added.json()["symbol"] == "000001.SZ"
    assert client.get("/api/v1/stocks/000001.sz/daily-prices").status_code == 200
    duplicate = client.post(
        f"/api/v1/watchlists/{group}/stocks", json={"symbol": "000001.SZ", "name": "测试股票"}
    )
    assert duplicate.status_code == 409
    assert client.delete(f"/api/v1/watchlists/{group}/stocks/000001.sz").status_code == 204


@pytest.mark.parametrize("same_group", [False, True])
def test_concurrent_stock_adds_do_not_return_internal_error(monkeypatch, same_group):
    with SessionLocal() as session:
        session.add_all([Watchlist(owner_id=1, id=1, name="甲"), Watchlist(owner_id=1, id=2, name="乙")])
        if same_group:
            session.add(Stock(symbol="000001.SZ", name="测试股票"))
        session.commit()
    barrier = Barrier(2)
    target = WatchlistItem if same_group else Stock

    class RacingSession(Session):
        def scalar(self, statement, *args, **kwargs):
            result = super().scalar(statement, *args, **kwargs)
            if (
                result is None
                and statement.column_descriptions[0].get("entity") is target
                and not self.info.get("synchronized")
            ):
                self.info["synchronized"] = True
                barrier.wait(timeout=10)
            return result

    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine, class_=RacingSession))
    application = main.create_app()
    application.dependency_overrides[require_actor] = lambda: Actor(1, "test-owner@example.com", True)

    def add(group):
        with TestClient(application, raise_server_exceptions=False) as client:
            return client.post(
                f"/api/v1/watchlists/{group}/stocks",
                json={"symbol": "000001.SZ", "name": "测试股票"},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        statuses = list(workers.map(add, [1, 1 if same_group else 2]))
    assert sorted(statuses) == ([201, 409] if same_group else [201, 201])
    with SessionLocal() as session:
        assert len(session.scalars(select(Stock)).all()) == 1
        assert len(session.scalars(select(WatchlistItem)).all()) == (1 if same_group else 2)
