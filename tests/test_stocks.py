import asyncio
from datetime import date

import httpx
import pytest

from app.database import DailyPrice, SessionLocal, Stock
from app.main import app


@pytest.mark.parametrize("symbol,status", [
    ("600519.sh", 200), ("600519.SH", 200), ("999999.SH", 404),
])
def test_get_stock_returns_normalized_catalog_record(client, monkeypatch, symbol, status) -> None:
    from app.stock_list import stock_list_service

    record = {"symbol": "600519.SH", "code": "sh600519", "name": "贵州茅台", "market": "sh"}
    monkeypatch.setattr(stock_list_service, "symbol_map", {"600519.SH": record})

    async def request_stock() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get(f"/api/v1/stocks/{symbol}")

    response = asyncio.run(request_stock())

    assert response.status_code == status
    assert response.json() == (record if status == 200 else {"detail": "股票不存在"})

def test_searches_stocks_by_name(client) -> None:
    with SessionLocal() as session:
        session.add(Stock(symbol="000001.SZ", name="平安银行"))
        session.commit()

    async def request_stocks() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get(
                "/api/v1/stocks",
                params={"query": "平安"},
            )

    response = asyncio.run(request_stocks())

    assert response.status_code == 200
    assert response.json() == [
        {
            "symbol": "000001.SZ",
            "name": "平安银行",
        }
    ]

def test_import_daily_price(client) -> None:
        with SessionLocal() as session:
            session.add(
                Stock(
                    symbol="600519.SH",
                    name="贵州茅台",
                )
            )
            session.commit()
        response = client.post(
        "/api/v1/stocks/600519.SH/daily-prices",
        json={
            "trade_date": "2026-09-25",
            "open": "1450.00",
            "high": "1465.50",
            "low": "1442.00",
            "close": "1460.25",
            "volume": 328900,
        },
    )

        assert response.status_code == 201
        with SessionLocal() as session:
            daily_price = session.query(DailyPrice).one()

        assert daily_price.trade_date.isoformat() == "2026-09-25"
        assert str(daily_price.open) == "1450.0000"
        assert str(daily_price.close) == "1460.2500"
        assert daily_price.volume == 328900

def test_import_daily_price_returns_404_for_unknown_stock(client) -> None:
    response = client.post(
        "/api/v1/stocks/999999.SH/daily-prices",
        json={
            "trade_date": "2026-09-25",
            "open": "10.00",
            "high": "10.50",
            "low": "9.80",
            "close": "10.20",
            "volume": 100000,
        },
    )

    assert response.status_code == 404

def test_import_daily_price_returns_409_when_duplicate(client) -> None:
    with SessionLocal() as session:
        session.add(
            Stock(
                symbol="600519.SH",
                name="贵州茅台",
            )
        )
        session.commit()

    payload = {
        "trade_date": "2026-09-25",
        "open": "1450.00",
        "high": "1465.50",
        "low": "1442.00",
        "close": "1460.25",
        "volume": 328900,
    }

    first_response = client.post(
        "/api/v1/stocks/600519.SH/daily-prices",
        json=payload,
    )
    second_response = client.post(
        "/api/v1/stocks/600519.SH/daily-prices",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409

def test_import_daily_price_rejects_negative_volume(client) -> None:
    with SessionLocal() as session:
        session.add(
            Stock(
                symbol="000001.SZ",
                name="平安银行",
            )
        )
        session.commit()

    response = client.post(
        "/api/v1/stocks/000001.SZ/daily-prices",
        json={
            "trade_date": "2026-09-25",
            "open": "10.00",
            "high": "10.50",
            "low": "9.80",
            "close": "10.20",
            "volume": -1,
        },
    )

    assert response.status_code == 422


def test_get_daily_prices_returns_sorted_data(client) -> None:
    with SessionLocal() as session:
        stock = Stock(
            symbol="600519.SH",
            name="贵州茅台",
        )
        session.add(stock)
        session.flush()

        session.add_all(
            [
                DailyPrice(
                    stock_id=stock.id,
                    trade_date=date(2026, 9, 25),
                    open="1450.00",
                    high="1465.50",
                    low="1442.00",
                    close="1460.25",
                    volume=328900,
                ),
                DailyPrice(
                    stock_id=stock.id,
                    trade_date=date(2026, 9, 24),
                    open="1440.00",
                    high="1455.00",
                    low="1435.00",
                    close="1450.00",
                    volume=298000,
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/stocks/600519.SH/daily-prices")

    assert response.status_code == 200
    assert response.json()[0]["trade_date"] == "2026-09-25"
    assert response.json()[1]["trade_date"] == "2026-09-24"

def test_get_daily_prices_returns_404_for_unknown_stock(client) -> None:
    response = client.get(
        "/api/v1/stocks/999999.SH/daily-prices"
    )

    assert response.status_code == 404

def test_get_daily_prices_returns_empty_list_when_no_data(client) -> None:
    with SessionLocal() as session:
        session.add(
            Stock(
                symbol="000001.SZ",
                name="平安银行",
            )
        )
        session.commit()

    response = client.get(
        "/api/v1/stocks/000001.SZ/daily-prices"
    )

    assert response.status_code == 200
    assert response.json() == []
