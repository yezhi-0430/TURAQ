"""Paper trading endpoints. Fills use live public quotes; nothing reaches a real broker."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import Actor, require_actor
from app.auth.models import User
from app.database import SessionLocal, Stock
from app.json_requests import DecimalJSONRoute
from app.model_limits import market_admission
from app.paper_trading import benchmark, performance, rules, service
from app.paper_trading.models import PaperAccount, PaperOrder, PaperPosition, PaperTrade
from app.paper_trading.quotes import canonical, load_quotes
from app.paper_trading.risk import account_alerts
from app.user_settings.runtime import get_runtime_policy
from app.watchlists.metadata import resolve_stock

router = APIRouter(prefix="/api/v1/paper-trading", tags=["paper-trading"],
                   dependencies=[Depends(market_admission)], route_class=DecimalJSONRoute)
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


def out(value):
    """Money stays exact on the wire: Decimals become strings."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: out(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [out(v) for v in value]
    return value


class AccountRequest(BaseModel):
    name: Name
    initial_capital: Decimal = Field(ge=10000, le=100_000_000, decimal_places=2)
    commission_rate: Decimal = Field(rules.DEFAULT_COMMISSION_RATE, ge=0, le=Decimal("0.003"),
                                     decimal_places=6)
    min_commission: Decimal = Field(rules.DEFAULT_MIN_COMMISSION, ge=0, le=100, decimal_places=2)


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)
    side: Literal["buy", "sell"]
    order_type: Literal["limit", "market"]
    quantity: int = Field(gt=0, le=10_000_000)
    limit_price: Decimal | None = Field(None, gt=0, le=100_000, decimal_places=2)
    acknowledged_risk_event_id: int | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None

    @model_validator(mode="after")
    def price_matches_type(self):
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("限价单需要委托价格")
        if self.order_type == "market" and self.limit_price is not None:
            raise ValueError("市价单不填写委托价格")
        return self


def symbol_or_422(raw: str) -> str:
    try:
        return canonical(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def account_dict(account: PaperAccount) -> dict:
    return {
        "id": account.id, "name": account.name, "initial_capital": account.initial_capital,
        "commission_rate": account.commission_rate, "min_commission": account.min_commission,
        "status": account.status, "created_at": account.created_at,
    }


def order_dict(order: PaperOrder, stock: Stock) -> dict:
    return {
        "order_id": order.order_id, "symbol": stock.symbol, "name": stock.name,
        "side": order.side, "order_type": order.order_type, "quantity": order.quantity,
        "limit_price": order.limit_price, "frozen_amount": order.frozen_amount,
        "status": order.status, "trade_date": order.trade_date,
        "risk_event_id": order.risk_event_id, "note": order.note,
        "created_at": order.created_at, "updated_at": order.updated_at,
    }


def trade_dict(trade: PaperTrade, stock: Stock) -> dict:
    return {
        "id": trade.id, "symbol": stock.symbol, "name": stock.name, "side": trade.side,
        "quantity": trade.quantity, "price": trade.price, "amount": trade.amount,
        "commission": trade.commission, "stamp_duty": trade.stamp_duty,
        "transfer_fee": trade.transfer_fee, "realized_pnl": trade.realized_pnl,
        "quote_time": trade.quote_time, "trade_date": trade.trade_date,
        "executed_at": trade.executed_at,
    }


def owned(session, actor: Actor, account_id: int) -> PaperAccount:
    account = session.scalar(select(PaperAccount).where(
        PaperAccount.id == account_id, PaperAccount.owner_id == actor.id))
    if account is None:
        raise HTTPException(404, "模拟账户不存在")
    return account


def account_symbols(session, account_id: int) -> list[str]:
    held = session.scalars(
        select(Stock.symbol).join(PaperPosition, PaperPosition.stock_id == Stock.id)
        .where(PaperPosition.account_id == account_id)
    )
    return list(dict.fromkeys([*held, *service.pending_symbols(session, [account_id])]))


@router.get("/accounts")
def list_accounts(actor: Actor = Depends(require_actor)):
    with SessionLocal() as session:
        accounts = session.scalars(
            select(PaperAccount).where(PaperAccount.owner_id == actor.id)
            .order_by(PaperAccount.created_at, PaperAccount.id)
        ).all()
        return {"accounts": out([account_dict(a) for a in accounts])}


@router.post("/accounts", status_code=201)
def create_account(payload: AccountRequest, actor: Actor = Depends(require_actor),
                   settings=Depends(get_runtime_policy)):
    with SessionLocal() as session:
        # Serialize creation per owner so simultaneous requests cannot bypass the configured cap.
        owner = session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
        if owner is None:
            raise HTTPException(401, "请重新登录")
        count = session.scalar(
            select(func.count()).select_from(PaperAccount)
            .where(PaperAccount.owner_id == actor.id)
        )
        if count >= settings.paper_max_accounts:
            raise HTTPException(409, f"每个用户最多 {settings.paper_max_accounts} 个模拟账户")
        try:
            account = service.create_account(
                session, actor.id, payload.name, payload.initial_capital,
                payload.commission_rate, payload.min_commission)
            session.commit()
        except service.TradingError as exc:
            raise HTTPException(409, str(exc)) from exc
        except IntegrityError as exc:
            raise HTTPException(409, "已有同名模拟账户") from exc
        return out(account_dict(account))


@router.get("/accounts/{account_id}")
async def account_overview(account_id: int, actor: Actor = Depends(require_actor)):
    """Matches resting orders against live quotes first, then values the account."""
    with SessionLocal() as session:
        owned(session, actor, account_id)
        symbols = account_symbols(session, account_id)
        symbols += [s for s in performance.recent_trade_symbols(
            session, account_id, rules.trade_date(service.clock())) if s not in symbols]
    quotes = await load_quotes(symbols) if symbols else {}
    now = service.clock()
    with SessionLocal() as session:
        filled = service.match_account(session, account_id, quotes)
        account = owned(session, actor, account_id)
        valuation = performance.value_account(session, account, quotes, now,
                                              persist_prices=True)
        day = performance.day_pnl(session, account, quotes, now)
        for row in valuation["positions"]:
            row.update(day["positions"].get(row["symbol"]) or {"day_pnl": None,
                                                                 "day_pct": None})
        day.pop("positions")
        pending = session.scalar(
            select(func.count()).select_from(PaperOrder)
            .where(PaperOrder.account_id == account_id, PaperOrder.status == "pending")
        )
        session.commit()
        return out({
            **account_dict(account), **valuation, "day": day, "pending_orders": pending,
            "matched_now": filled, "market_open": rules.in_session(now), "checked_at": now,
        })


@router.get("/accounts/{account_id}/preview")
async def preview(
    account_id: int,
    symbol: str = Query(min_length=6, max_length=12),
    side: Literal["buy", "sell"] = "buy",
    quantity: int = Query(0, ge=0, le=10_000_000),
    price: Annotated[Decimal | None, Query(gt=0, le=100_000, decimal_places=2)] = None,
    actor: Actor = Depends(require_actor),
):
    """Everything the order form needs: live quote, band, lots, fees, limits, risk."""
    symbol = symbol_or_422(symbol)
    quote = (await load_quotes([symbol])).get(symbol)
    if quote is None or quote.kind != "stock":
        raise HTTPException(404, "没有该股票的可信实时行情")
    now = service.clock()
    today = rules.trade_date(now)
    board = rules.board_for(symbol, quote.name, today)
    band = rules.price_band(quote.previous_close, board) if quote.previous_close else None
    with SessionLocal() as session:
        account = owned(session, actor, account_id)
        stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
        position = session.scalar(select(PaperPosition).where(
            PaperPosition.account_id == account_id, PaperPosition.stock_id == stock.id
        )) if stock else None
        event = service.latest_risk_event(session, actor.id, stock, now) if stock else None
        available = account.cash - account.frozen_cash
        basis = price or quote.price
        estimate = rules.fees(side, basis, quantity, account.commission_rate,
                              account.min_commission) if basis and quantity else None
        if not quantity:
            check = None
        elif side == "buy":
            check = rules.check_buy_quantity(quantity, board)
        else:
            check = rules.check_sell_quantity(quantity, service.sellable(position, today), board)
        try:
            service.live_market(quote, now)
            market_problem = None
        except service.TradingError as exc:
            market_problem = str(exc)
        return out({
            "symbol": symbol, "name": quote.name, "price": quote.price,
            "previous_close": quote.previous_close, "quote_time": quote.quote_time,
            "stale": quote.stale, "market_problem": market_problem,
            "board": board.name, "limit_pct": board.limit,
            "min_quantity": board.min_quantity, "step": board.step,
            "lower_limit": band[0] if band else None, "upper_limit": band[1] if band else None,
            "available_cash": available,
            "max_buy": rules.max_buy_quantity(available, basis, board, account.commission_rate,
                                              account.min_commission) if basis else 0,
            "holding": position.quantity if position else 0,
            "sellable": service.sellable(position, today),
            "quantity_problem": check,
            "estimate": None if estimate is None else {
                "amount": estimate.amount, "commission": estimate.commission,
                "stamp_duty": estimate.stamp_duty, "transfer_fee": estimate.transfer_fee,
                "fees": estimate.total,
                "net": estimate.amount + estimate.total if side == "buy"
                else estimate.amount - estimate.total,
            },
            "risk_event": None if event is None else {
                "id": event.id, "risk_level": event.risk_level, "risk_type": event.risk_type,
                "summary": event.summary, "analyzed_at": event.analyzed_at,
                "requires_ack": side == "buy" and event.risk_level == "high",
            },
        })


@router.post("/accounts/{account_id}/orders", status_code=201)
async def place_order(account_id: int, payload: OrderRequest,
                      actor: Actor = Depends(require_actor)):
    symbol = symbol_or_422(payload.symbol)
    quotes = await load_quotes([symbol])
    with SessionLocal() as session:
        owned(session, actor, account_id)
        try:
            await resolve_stock(session, symbol)
            session.commit()
        except LookupError as exc:
            raise HTTPException(404, "股票不存在或可信行情暂不可用") from exc
        stock = service.stock_by_symbol(session, symbol)
        try:
            order, trade = service.place_order(
                session, actor.id, account_id, stock, quotes.get(symbol),
                side=payload.side, order_type=payload.order_type, quantity=payload.quantity,
                limit_price=payload.limit_price,
                acknowledged_risk_event_id=payload.acknowledged_risk_event_id,
                note=payload.note,
            )
            session.commit()
        except service.RiskConfirmationRequired as exc:
            session.rollback()
            # Detail stays a string for the shared client; the header names the event to confirm.
            raise HTTPException(409, f"{exc}：{exc.event.summary}",
                                headers={"X-Risk-Event-Id": str(exc.event.id)}) from exc
        except service.TradingError as exc:
            session.rollback()
            raise HTTPException(422, str(exc)) from exc
        except service.NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        return out({"order": order_dict(order, stock),
                    "trade": trade_dict(trade, stock) if trade else None})


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, actor: Actor = Depends(require_actor)):
    with SessionLocal() as session:
        try:
            order = service.cancel_order(session, actor.id, order_id)
            session.commit()
        except service.NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except service.TradingError as exc:
            raise HTTPException(409, str(exc)) from exc
        return out(order_dict(order, session.get(Stock, order.stock_id)))


@router.get("/accounts/{account_id}/orders")
def list_orders(account_id: int,
                status: Literal["pending", "filled", "cancelled", "expired"] | None = None,
                limit: int = Query(50, ge=1, le=200), actor: Actor = Depends(require_actor)):
    with SessionLocal() as session:
        owned(session, actor, account_id)
        query = (select(PaperOrder, Stock).join(Stock, Stock.id == PaperOrder.stock_id)
                 .where(PaperOrder.account_id == account_id))
        if status:
            query = query.where(PaperOrder.status == status)
        rows = session.execute(
            query.order_by(PaperOrder.created_at.desc(), PaperOrder.id.desc()).limit(limit)
        ).all()
        return {"orders": out([order_dict(o, s) for o, s in rows])}


@router.get("/accounts/{account_id}/trades")
def list_trades(account_id: int, limit: int = Query(50, ge=1, le=200),
                symbol: Annotated[str | None, Query(min_length=6, max_length=12)] = None,
                actor: Actor = Depends(require_actor)):
    with SessionLocal() as session:
        owned(session, actor, account_id)
        query = (select(PaperTrade, Stock).join(Stock, Stock.id == PaperTrade.stock_id)
                 .where(PaperTrade.account_id == account_id))
        if symbol:
            query = query.where(Stock.symbol == symbol_or_422(symbol))
        rows = session.execute(
            query.order_by(PaperTrade.executed_at.desc(), PaperTrade.id.desc()).limit(limit)
        ).all()
        return {"trades": out([trade_dict(t, s) for t, s in rows])}


@router.get("/accounts/{account_id}/performance")
async def account_performance(account_id: int, actor: Actor = Depends(require_actor)):
    with SessionLocal() as session:
        account = owned(session, actor, account_id)
        symbols = account_symbols(session, account_id)
    quotes = await load_quotes(symbols) if symbols else {}
    now = service.clock()
    with SessionLocal() as session:
        account = owned(session, actor, account_id)
        valuation = performance.value_account(session, account, quotes, now)
        metrics = performance.performance(session, account, valuation)
        series = performance.snapshots(session, account_id)
        points = [(s.snapshot_date, s.total_assets) for s in series]
        start = rules.trade_date(account.created_at)
        initial = account.initial_capital
    if not points or points[-1][0] != rules.trade_date(now):
        points.append((rules.trade_date(now), valuation["total_assets"]))
    comparison = await benchmark.compare(start, initial, points)
    return out({**metrics, "valuation_complete": valuation["valuation_complete"],
                "benchmark": comparison,
                "notes": ["日终快照于每个交易日 15:05 记录；当日点为实时估值。",
                          "夏普与波动率至少需要 5 个日收益观测，未满足时不展示。"]})


@router.get("/accounts/{account_id}/risk-alerts")
async def risk_alerts(account_id: int, actor: Actor = Depends(require_actor)):
    with SessionLocal() as session:
        owned(session, actor, account_id)
        symbols = account_symbols(session, account_id)
    quotes = await load_quotes(symbols) if symbols else {}
    with SessionLocal() as session:
        account = owned(session, actor, account_id)
        return out(account_alerts(session, account, quotes, service.clock()))
