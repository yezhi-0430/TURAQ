import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import main as main_module
from app.database import SessionLocal, Stock, Watchlist, WatchlistItem


def test_creates_watchlist_from_request_body(client: TestClient) -> None:
    response = client.post(
        "/api/v1/watchlists",
        json={"name": "核心持仓"},
    )

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["name"] == "核心持仓"


@pytest.mark.parametrize(
    "invalid_name",
    [
        "",
        "a" * 41,
    ],
)
def test_rejects_invalid_watchlist_name(
    client: TestClient,
    invalid_name: str,
) -> None:
    response = client.post(
        "/api/v1/watchlists",
        json={"name": invalid_name},
    )

    assert response.status_code == 422


def test_create_watchlist_saves_to_database(client: TestClient) -> None:
    response = client.post(
        "/api/v1/watchlists",
        json={"name": "长期观察"},
    )
    watchlist_id = response.json()["id"]

    try:
        with SessionLocal() as session:
            saved_watchlist = session.get(
                Watchlist,
                watchlist_id,
            )

            assert saved_watchlist is not None
            assert saved_watchlist.name == "长期观察"
    finally:
        with SessionLocal() as session:
            saved_watchlist = session.get(
                Watchlist,
                watchlist_id,
            )
            if saved_watchlist is not None:
                session.delete(saved_watchlist)
                session.commit()


def test_lists_watchlists(client: TestClient) -> None:
    response = client.get("/api/v1/watchlists")
    assert response.status_code == 200
    assert response.json() == []


def test_lists_saved_watchlist(client: TestClient) -> None:
    with SessionLocal() as session:
        watchlist = Watchlist(owner_id=1, name="风险观察")
        session.add(watchlist)
        session.commit()
        session.refresh(watchlist)
        watchlist_id = watchlist.id

    try:
        response = client.get("/api/v1/watchlists")

        assert response.status_code == 200
        assert {
            "id": watchlist_id,
            "name": "风险观察",
        } in response.json()
    finally:
        with SessionLocal() as session:
            saved_watchlist = session.get(Watchlist, watchlist_id)
            if saved_watchlist is not None:
                session.delete(saved_watchlist)
                session.commit()


def test_unexpected_database_error_returns_safe_response(
    monkeypatch: pytest.MonkeyPatch,
    error_client: TestClient,
) -> None:
    def fail_to_create_watchlist(
        session: object,
        name: str,
    ) -> None:
        raise RuntimeError("database connection details")

    monkeypatch.setattr(
        main_module,
        "save_watchlist",
        fail_to_create_watchlist,
    )

    response = error_client.post(
        "/api/v1/watchlists",
        json={"name": "异常测试"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "服务器内部错误"}
    assert "database connection details" not in response.text


def test_adds_stock_to_watchlist(client: TestClient) -> None:
    watchlist_response = client.post(
        "/api/v1/watchlists",
        json={"name": "风险观察"},
    )
    watchlist_id = watchlist_response.json()["id"]

    response = client.post(
        f"/api/v1/watchlists/{watchlist_id}/stocks",
        json={"symbol": "600519.SH", "name": "贵州茅台"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "symbol": "600519.SH",
        "name": "贵州茅台",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"symbol": "", "name": "贵州茅台"},
        {"symbol": "600519.SH", "name": ""},
        {"symbol": "   ", "name": "贵州茅台"},
        {"symbol": "600519.SH", "name": "   "},
        {"symbol": "600519.SH"},
        {"name": "贵州茅台"},
    ],
)
def test_rejects_invalid_stock_fields(
    client: TestClient,
    payload: dict[str, str],
) -> None:
    watchlist = client.post(
        "/api/v1/watchlists",
        json={"name": "输入校验"},
    ).json()

    response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/stocks",
        json=payload,
    )

    assert response.status_code == 422


def test_rejects_adding_same_stock_twice_to_watchlist(
    client: TestClient,
) -> None:
    watchlist_response = client.post(
        "/api/v1/watchlists",
        json={"name": "风险观察"},
    )
    watchlist_id = watchlist_response.json()["id"]
    payload = {"symbol": "600519.SH", "name": "贵州茅台"}

    first_response = client.post(
        f"/api/v1/watchlists/{watchlist_id}/stocks",
        json=payload,
    )
    second_response = client.post(
        f"/api/v1/watchlists/{watchlist_id}/stocks",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_rejects_adding_stock_to_missing_watchlist(client: TestClient) -> None:
    response = client.post(
        "/api/v1/watchlists/999999/stocks",
        json={"symbol": "600519.SH", "name": "贵州茅台"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "自选组不存在"}


def test_reuses_stock_record_across_watchlists(client: TestClient) -> None:
    first_watchlist = client.post(
        "/api/v1/watchlists",
        json={"name": "核心持仓"},
    ).json()
    second_watchlist = client.post(
        "/api/v1/watchlists",
        json={"name": "长期观察"},
    ).json()
    payload = {"symbol": "600519.SH", "name": "贵州茅台"}

    first_response = client.post(
        f"/api/v1/watchlists/{first_watchlist['id']}/stocks",
        json=payload,
    )
    second_response = client.post(
        f"/api/v1/watchlists/{second_watchlist['id']}/stocks",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    with SessionLocal() as session:
        stocks = session.scalars(select(Stock).where(Stock.symbol == "600519.SH")).all()
        associations = session.scalars(
            select(WatchlistItem).where(
                WatchlistItem.stock_id == stocks[0].id,
            )
        ).all()

    assert len(stocks) == 1
    assert len(associations) == 2
    assert second_response.json()["name"] == "贵州茅台"


def test_reuses_existing_stock_name(client: TestClient) -> None:
    first_watchlist = client.post(
        "/api/v1/watchlists",
        json={"name": "核心持仓"},
    ).json()
    second_watchlist = client.post(
        "/api/v1/watchlists",
        json={"name": "长期观察"},
    ).json()

    client.post(
        f"/api/v1/watchlists/{first_watchlist['id']}/stocks",
        json={"symbol": "600519.SH", "name": "贵州茅台"},
    )
    response = client.post(
        f"/api/v1/watchlists/{second_watchlist['id']}/stocks",
        json={"symbol": "600519.SH", "name": "错误名称"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "贵州茅台"


def test_removes_stock_from_only_the_selected_watchlist(client: TestClient) -> None:
    first_watchlist = client.post(
        "/api/v1/watchlists",
        json={"name": "核心持仓"},
    ).json()
    second_watchlist = client.post(
        "/api/v1/watchlists",
        json={"name": "长期观察"},
    ).json()
    stock_payload = {"symbol": "600519.SH", "name": "贵州茅台"}
    client.post(
        f"/api/v1/watchlists/{first_watchlist['id']}/stocks",
        json=stock_payload,
    )
    client.post(
        f"/api/v1/watchlists/{second_watchlist['id']}/stocks",
        json=stock_payload,
    )

    response = client.delete(f"/api/v1/watchlists/{first_watchlist['id']}/stocks/600519.SH")

    assert response.status_code == 204
    with SessionLocal() as session:
        stock = session.scalar(select(Stock).where(Stock.symbol == "600519.SH"))
        associations = session.scalars(
            select(WatchlistItem).where(WatchlistItem.stock_id == stock.id)
        ).all()

    assert stock is not None
    assert len(associations) == 1
    assert associations[0].watchlist_id == second_watchlist["id"]


def test_returns_404_when_removing_missing_stock_association(
    client: TestClient,
) -> None:
    watchlist = client.post(
        "/api/v1/watchlists",
        json={"name": "风险观察"},
    ).json()

    response = client.delete(f"/api/v1/watchlists/{watchlist['id']}/stocks/600519.SH")

    assert response.status_code == 404
    assert response.json() == {"detail": "自选组中不存在该股票"}


def test_returns_404_when_removing_stock_from_missing_watchlist(
    client: TestClient,
) -> None:
    response = client.delete("/api/v1/watchlists/999999/stocks/600519.SH")

    assert response.status_code == 404
    assert response.json() == {"detail": "自选组不存在"}
