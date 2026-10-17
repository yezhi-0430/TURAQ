import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.database import SessionLocal, Stock
from app.paper_trading import benchmark, performance, rules, service, tasks
from app.paper_trading.models import PaperAccount, PaperOrder, PaperPosition, PaperSnapshot
from app.risk_records import RiskAnalysis, RiskEvent

SH = rules.SHANGHAI
OPEN = datetime(2026, 10, 14, 10, 0, tzinfo=SH)  # Wednesday morning session


class Market:
    """Quotes in MarketService's real wire format, controllable per test."""

    def __init__(self):
        self.now = OPEN
        self.rows = {}

    def set(self, symbol, price, previous="100.00", name=None, at=None):
        self.rows[symbol] = {
            "symbol": symbol, "name": name or {"600519.SH": "贵州茅台"}.get(symbol, "测试股票"),
            "kind": "index" if symbol == "000300.SH" else "stock",
            "price": price, "previous_close": previous,
            "quote_time": (at or self.now).isoformat(), "stale": False,
        }

    async def quotes(self, symbols):
        return {"quotes": [self.rows[s] for s in symbols if s in self.rows], "stale": False}


@pytest.fixture
def market(monkeypatch):
    m = Market()
    monkeypatch.setattr("app.market_api.service.quotes", m.quotes)
    monkeypatch.setattr(service, "clock", lambda: m.now)
    m.set("600519.SH", "100.00")
    return m


@pytest.fixture
def account(client, market):
    response = client.post("/api/v1/paper-trading/accounts",
                           json={"name": "主账户", "initial_capital": 100000})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def order(client, account_id, **body):
    payload = {"symbol": "600519.SH", "side": "buy", "order_type": "market",
               "quantity": 100, **body}
    return client.post(f"/api/v1/paper-trading/accounts/{account_id}/orders", json=payload)


def overview(client, account_id):
    response = client.get(f"/api/v1/paper-trading/accounts/{account_id}")
    assert response.status_code == 200, response.text
    return response.json()


# ---- pure rules ----

def test_boards_and_price_bands():
    today = date(2026, 10, 14)
    assert rules.board_for("600519.SH", "贵州茅台", today).limit == Decimal("0.10")
    assert rules.board_for("300750.SZ", "宁德时代", today).limit == Decimal("0.20")
    star = rules.board_for("688981.SH", "中芯国际", today)
    assert (star.limit, star.min_quantity, star.step) == (Decimal("0.20"), 200, 1)
    assert rules.board_for("830799.BJ", "艾融软件", today).limit == Decimal("0.30")
    assert rules.board_for("600000.SH", "*ST测试", today).limit == Decimal("0.10")
    assert rules.board_for("600000.SH", "*ST测试", date(2026, 7, 3)).limit == Decimal("0.05")
    board = rules.board_for("600519.SH", "贵州茅台", today)
    assert rules.price_band(Decimal("10.05"), board) == (Decimal("9.05"), Decimal("11.06"))


def test_fees_follow_current_rates():
    buy = rules.fees("buy", Decimal("10"), 1000, Decimal("0.00025"), Decimal("5"))
    assert (buy.amount, buy.commission, buy.stamp_duty, buy.transfer_fee) == (
        Decimal("10000.00"), Decimal("5"), Decimal("0.00"), Decimal("0.10"))
    sell = rules.fees("sell", Decimal("100"), 1000, Decimal("0.00025"), Decimal("5"))
    assert (sell.commission, sell.stamp_duty, sell.transfer_fee) == (
        Decimal("25.00"), Decimal("50.00"), Decimal("1.00"))


def test_lot_rules_and_max_buy():
    main = rules.board_for("600519.SH", "贵州茅台", date(2026, 10, 14))
    star = rules.board_for("688981.SH", "中芯国际", date(2026, 10, 14))
    assert rules.check_buy_quantity(150, main)
    assert rules.check_buy_quantity(200, main) is None
    assert rules.check_buy_quantity(199, star)
    assert rules.check_buy_quantity(201, star) is None
    assert rules.check_sell_quantity(50, 50, main) is None  # whole odd-lot remainder
    assert rules.check_sell_quantity(50, 150, main)
    assert rules.check_sell_quantity(300, 200, main)
    quantity = rules.max_buy_quantity(Decimal("10010"), Decimal("100"), main,
                                      Decimal("0.00025"), Decimal("5"))
    assert quantity == 100
    assert rules.max_buy_quantity(Decimal("10000"), Decimal("100"), main,
                                  Decimal("0.00025"), Decimal("5")) == 0


def test_sessions_and_live_quotes():
    assert rules.in_session(OPEN)
    assert not rules.in_session(OPEN.replace(hour=12))
    assert not rules.in_session(OPEN.replace(hour=15))
    assert not rules.in_session(datetime(2026, 10, 17, 10, tzinfo=SH))
    assert rules.live_quote_problem(OPEN - timedelta(days=1), OPEN)  # holiday: old quote
    assert rules.live_quote_problem(OPEN - timedelta(seconds=30), OPEN) is None


def test_metrics_need_real_observations():
    assert performance.max_drawdown([Decimal(100), Decimal(120), Decimal(90), Decimal(130)]) \
        == Decimal("0.25")
    assert performance.risk_metrics([0.01, -0.01]) == {"volatility": None, "sharpe": None}
    metrics = performance.risk_metrics([0.01, 0.0, 0.02, -0.01, 0.01])
    assert metrics["sharpe"] > 0 and metrics["volatility"] > 0


def test_benchmark_aligns_to_index_dates():
    bars = [{"date": "2026-10-12", "close": "4000"}, {"date": "2026-10-13", "close": "4100"},
            {"date": "2026-10-15", "close": "4200"}]
    points = [(date(2026, 10, 13), Decimal("101000")), (date(2026, 10, 14), Decimal("99000")),
              (date(2026, 10, 15), Decimal("103000"))]
    result = benchmark.align(date(2026, 10, 12), Decimal("100000"), points, bars)
    assert result["base_close"] == Decimal("4000")
    # 10-14 had no index bar yet: compare with the latest earlier close, labelled honestly.
    assert result["series"][1]["benchmark_date"] == "2026-10-13"
    assert result["series"][2]["benchmark_return"] == Decimal("0.05")
    assert result["excess_return"] == Decimal("-0.02")
    assert not benchmark.align(date(2026, 10, 1), Decimal("1"), points, bars)["available"]


# ---- orders through the API ----

def test_market_buy_fills_at_real_quote_with_fees(client, account):
    response = order(client, account)
    assert response.status_code == 201, response.text
    trade = response.json()["trade"]
    assert (trade["price"], trade["amount"], trade["commission"], trade["transfer_fee"]) == (
        "100.00", "10000.00", "5.00", "0.10")
    data = overview(client, account)
    assert data["cash"] == "89994.90"
    position = data["positions"][0]
    assert (position["quantity"], position["sellable"]) == (100, 0)  # T+1
    assert position["cost_amount"] == "10005.10"


def test_t_plus_one_then_sell_records_realized_pnl(client, account, market):
    assert order(client, account).status_code == 201
    rejected = order(client, account, side="sell")
    assert rejected.status_code == 422 and "可卖" in rejected.json()["detail"]
    market.now = OPEN + timedelta(days=1)
    market.set("600519.SH", "110.00", previous="100.00")
    sold = order(client, account, side="sell")
    assert sold.status_code == 201, sold.text
    trade = sold.json()["trade"]
    # 11000 - 5 commission - 5.50 stamp - 0.11 transfer - 10005.10 cost
    assert trade["stamp_duty"] == "5.50"
    assert trade["realized_pnl"] == "984.29"
    data = overview(client, account)
    assert data["positions"] == [] and data["cash"] == "100984.29"
    url = f"/api/v1/paper-trading/accounts/{account}/trades"
    assert [t["side"] for t in client.get(url, params={"symbol": "sh600519"}).json()["trades"]] == [
        "sell", "buy"]
    assert client.get(url, params={"symbol": "000001.SZ"}).json()["trades"] == []
    assert client.get(url, params={"symbol": "abcdef"}).status_code == 422
    stats = client.get(f"/api/v1/paper-trading/accounts/{account}/performance")
    assert stats.status_code == 200
    assert stats.json()["win_rate"] == "1.000000"


def test_limit_order_rests_freezes_cash_and_matches_later(client, account, market):
    resting = order(client, account, order_type="limit", limit_price=95, quantity=200)
    assert resting.status_code == 201
    assert resting.json()["trade"] is None
    data = overview(client, account)
    assert data["frozen_cash"] == "19005.19" and data["pending_orders"] == 1
    market.set("600519.SH", "94.50")
    data = overview(client, account)
    assert data["matched_now"] == 1 and data["frozen_cash"] == "0.00"
    # Filled at the real crossing price, not the more expensive limit.
    trades = client.get(f"/api/v1/paper-trading/accounts/{account}/trades").json()["trades"]
    assert trades[0]["price"] == "94.50"


def test_cancel_releases_frozen_cash_and_shares(client, account, market):
    resting = order(client, account, order_type="limit", limit_price=95).json()["order"]
    cancelled = client.post(f"/api/v1/paper-trading/orders/{resting['order_id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert overview(client, account)["frozen_cash"] == "0.00"
    again = client.post(f"/api/v1/paper-trading/orders/{resting['order_id']}/cancel")
    assert again.status_code == 409

    assert order(client, account).status_code == 201
    market.now = OPEN + timedelta(days=1)
    market.set("600519.SH", "100.00")
    sell = order(client, account, side="sell", order_type="limit", limit_price=105).json()
    assert overview(client, account)["positions"][0]["frozen"] == 100
    client.post(f"/api/v1/paper-trading/orders/{sell['order']['order_id']}/cancel")
    assert overview(client, account)["positions"][0]["sellable"] == 100


def test_price_band_session_and_stale_quote_rejections(client, account, market):
    out_of_band = order(client, account, order_type="limit", limit_price="111.00")
    assert out_of_band.status_code == 422 and "涨跌停" in out_of_band.json()["detail"]
    market.set("600519.SH", "110.00")  # sealed at limit-up
    assert "封板" in order(client, account).json()["detail"]
    market.now = OPEN.replace(hour=12)
    market.set("600519.SH", "100.00")
    assert "交易时段" in order(client, account).json()["detail"]
    market.now = OPEN
    market.set("600519.SH", "100.00", at=OPEN - timedelta(days=1))
    assert "当日实时成交" in order(client, account).json()["detail"]


def test_insufficient_cash_and_lot_size(client, account):
    assert "100 股整数倍" in order(client, account, quantity=150).json()["detail"]
    assert order(client, account, quantity=1000).json()["detail"] == "可用资金不足"
    with SessionLocal() as session:
        assert session.scalar(select(PaperOrder.id)) is None  # rejected orders leave no rows


def test_day_orders_expire_and_release_cash(client, account, market):
    order(client, account, order_type="limit", limit_price=95)
    market.now = OPEN + timedelta(days=1)
    data = overview(client, account)
    assert data["frozen_cash"] == "0.00" and data["pending_orders"] == 0
    orders = client.get(f"/api/v1/paper-trading/accounts/{account}/orders").json()["orders"]
    assert orders[0]["status"] == "expired"


def test_high_risk_event_requires_acknowledgement(client, account, market):
    with SessionLocal() as session:
        stock = Stock(symbol="600519.SH", name="贵州茅台")
        session.add(stock)
        session.flush()
        analysis = RiskAnalysis(
            owner_id=1, request_id="r1", fingerprint="f", stock_id=stock.id,
            risk_type="financial", title="t", input_text="x", evidence=[], model_mode="fake",
            generation_status="completed")
        session.add(analysis)
        session.flush()
        event = RiskEvent(owner_id=1, analysis_id=analysis.id, stock_id=stock.id,
                          risk_type="financial", summary="经营现金流连续为负",
                          risk_level="high", analyzed_at=OPEN - timedelta(days=2))
        session.add(event)
        session.commit()
        event_id = event.id
    preview = client.get(f"/api/v1/paper-trading/accounts/{account}/preview",
                         params={"symbol": "600519", "quantity": 100}).json()
    assert preview["risk_event"]["requires_ack"] is True
    assert preview["upper_limit"] == "110.00" and preview["estimate"]["fees"] == "5.10"
    blocked = order(client, account)
    assert blocked.status_code == 409 and "经营现金流连续为负" in blocked.json()["detail"]
    assert blocked.headers["X-Risk-Event-Id"] == str(event_id)
    assert order(client, account, acknowledged_risk_event_id=event_id + 1).status_code == 409
    filled = order(client, account, acknowledged_risk_event_id=event_id)
    assert filled.status_code == 201
    assert filled.json()["order"]["risk_event_id"] == event_id
    alerts = client.get(f"/api/v1/paper-trading/accounts/{account}/risk-alerts").json()
    assert alerts["alerts"][0]["kind"] == "risk_event"
    assert alerts["unanalyzed"] == []


def test_accounts_are_private(client, account):
    with SessionLocal() as session:
        from app.auth.models import User
        from app.auth.service import utcnow

        session.add(User(id=2, email="other@example.com", password_hash="x", verified=True,
                         is_admin=False, pending_expires_at=utcnow()))
        session.flush()
        other = service.create_account(session, 2, "他人", Decimal("50000"),
                                       Decimal("0.00025"), Decimal("5"))
        session.commit()
        other_id = other.id
    assert client.get(f"/api/v1/paper-trading/accounts/{other_id}").status_code == 404
    assert order(client, other_id).status_code == 404
    names = [a["name"] for a in client.get("/api/v1/paper-trading/accounts").json()["accounts"]]
    assert names == ["主账户"]


def test_duplicate_account_name(client, account):
    again = client.post("/api/v1/paper-trading/accounts",
                        json={"name": "主账户", "initial_capital": 100000})
    assert again.status_code == 409


# ---- scheduled jobs ----

def test_match_job_and_daily_snapshot(client, account, market, monkeypatch):
    order(client, account, order_type="limit", limit_price=95)
    market.set("600519.SH", "94.00")
    assert asyncio.run(tasks.match_pending_orders()) == 1

    market.now = OPEN.replace(hour=15, minute=5)
    market.set("600519.SH", "96.00", at=OPEN.replace(hour=15))
    market.set("000300.SH", "4000.00", at=OPEN.replace(hour=15))
    assert asyncio.run(tasks.record_daily_snapshots()) == 1
    assert asyncio.run(tasks.record_daily_snapshots()) == 1  # idempotent rerun
    with SessionLocal() as session:
        snaps = session.scalars(select(PaperSnapshot)).all()
        assert len(snaps) == 1 and snaps[0].market_value == Decimal("9600.00")
        position = session.scalar(select(PaperPosition))
        assert position.last_price == Decimal("96.00")


def test_snapshot_skips_holiday(client, account, market):
    market.now = OPEN.replace(hour=15, minute=5)
    market.set("000300.SH", "4000.00", at=OPEN - timedelta(days=1))
    assert asyncio.run(tasks.record_daily_snapshots()) == 0


def test_concurrent_orders_cannot_overspend(account, market):
    """Two sessions race for the same cash; the account row lock serializes them."""
    import threading

    with SessionLocal() as session:
        session.add(Stock(symbol="600519.SH", name="贵州茅台"))
        session.commit()
    quote = asyncio.run(_quote())
    results, barrier = [], threading.Barrier(2)

    def buy():
        with SessionLocal() as session:
            stock = service.stock_by_symbol(session, "600519.SH")
            barrier.wait()
            try:
                service.place_order(session, 1, account, stock, quote, side="buy",
                                    order_type="market", quantity=600, limit_price=None)
                session.commit()
                results.append("ok")
            except service.TradingError:
                session.rollback()
                results.append("rejected")

    threads = [threading.Thread(target=buy) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["ok", "rejected"]
    with SessionLocal() as session:
        cash = session.scalar(select(PaperAccount.cash))
        assert cash == Decimal("39984.40")


async def _quote():
    from app.paper_trading.quotes import load_quotes

    return (await load_quotes(["600519.SH"]))["600519.SH"]


def test_auto_analysis_event_without_stock_id_still_gates_buy(client, account):
    """Automatic analysis of a stock not yet in `stocks` stores only context.subject.symbol."""
    with SessionLocal() as session:
        analysis = RiskAnalysis(
            owner_id=1, request_id="r2", fingerprint="f", stock_id=None,
            risk_type="comprehensive", title="t", input_text="x", evidence=[],
            model_mode="qwen", generation_status="completed")
        session.add(analysis)
        session.flush()
        event = RiskEvent(owner_id=1, analysis_id=analysis.id, stock_id=None,
                          risk_type="comprehensive", summary="跌破关键均线且放量",
                          risk_level="high", analyzed_at=OPEN - timedelta(days=1),
                          context={"subject": {"symbol": "600519.SH", "name": "贵州茅台"}})
        session.add(event)
        session.commit()
        event_id = event.id
    assert order(client, account).status_code == 409
    assert order(client, account, acknowledged_risk_event_id=event_id).status_code == 201
    alerts = client.get(f"/api/v1/paper-trading/accounts/{account}/risk-alerts").json()
    assert alerts["alerts"][0]["risk_event_id"] == event_id and alerts["unanalyzed"] == []


# ---- day P&L ----

def test_day_pnl_on_first_day_uses_fill_price_and_fees(client, account, market):
    assert order(client, account).status_code == 201  # 100 @ 100.00, fees 5.10
    market.set("600519.SH", "102.00", previous="100.00")
    data = overview(client, account)
    # Bought today: compare with the fill, not yesterday's close.
    assert data["day"]["pnl"] == "194.90" and data["day"]["complete"] is True
    assert Decimal(data["total_assets"]) - Decimal("100000") == Decimal("194.90")
    assert data["positions"][0]["day_pnl"] == "194.90"


def test_day_pnl_mixes_overnight_buys_and_full_exit(client, account, market):
    market.set("000001.SZ", "10.00", previous="10.00", name="平安银行")
    assert order(client, account).status_code == 201
    assert order(client, account, symbol="000001.SZ", quantity=1000).status_code == 201
    market.now = OPEN.replace(hour=15, minute=5)
    market.set("600519.SH", "105.00", previous="100.00")
    market.set("000001.SZ", "11.00", previous="10.00", name="平安银行")
    yesterday = Decimal(overview(client, account)["total_assets"])

    market.now = OPEN + timedelta(days=1)
    market.set("600519.SH", "106.00", previous="105.00")
    market.set("000001.SZ", "11.50", previous="11.00", name="平安银行")
    assert order(client, account, quantity=100).status_code == 201  # add 100 @ 106
    assert order(client, account, symbol="000001.SZ", side="sell",
                 quantity=1000).status_code == 201  # exit all @ 11.50
    market.set("600519.SH", "107.00", previous="105.00")
    data = overview(client, account)
    day = data["day"]
    assert day["complete"] is True and day["is_today"] is True
    # The invariant that makes the number trustworthy: no deposits, so P&L is the asset change.
    assert Decimal(day["pnl"]) == Decimal(data["total_assets"]) - yesterday
    assert Decimal(day["return"]) == (Decimal(day["pnl"]) / yesterday).quantize(
        Decimal("0.000001"))
    # 100 overnight +2.00 and 100 new +1.00 less 5.11 fees; the exit stays visible.
    assert data["positions"][0]["day_pnl"] == "294.89"
    assert Decimal(day["closed_pnl"]) == Decimal(day["pnl"]) - Decimal("294.89")
    assert Decimal(day["closed_pnl"]) < Decimal("500")  # +500 move minus sell fees


def test_day_pnl_refuses_to_guess_without_a_same_day_quote(client, account, market):
    assert order(client, account).status_code == 201
    market.now = OPEN + timedelta(days=1)
    market.set("600519.SH", "101.00", at=OPEN)  # the feed is still on yesterday
    market.set("000001.SZ", "10.00", name="平安银行")
    assert order(client, account, symbol="000001.SZ", quantity=100).status_code == 201
    day = overview(client, account)["day"]
    # 600519 printed yesterday but 000001 traded today: a halt is assumed, priced flat.
    assert day["complete"] is True
    held = {p["symbol"]: p for p in overview(client, account)["positions"]}
    assert held["600519.SH"]["day_pnl"] == "0.00"
    market.rows.pop("600519.SH")
    day = overview(client, account)["day"]
    assert day["complete"] is False and day["pnl"] is None


def test_day_pnl_after_close_reports_last_session(client, account, market):
    assert order(client, account).status_code == 201
    market.now = datetime(2026, 10, 17, 10, tzinfo=SH)  # Saturday
    market.set("600519.SH", "103.00", at=OPEN.replace(hour=15))
    day = overview(client, account)["day"]
    assert day["date"] == "2026-10-14" and day["is_today"] is False
    assert day["pnl"] == "294.90"
