"""Order lifecycle for paper accounts.

Callers fetch real quotes first, then call these functions inside one database
transaction. Every mutation locks the account row before position/order rows, so
concurrent requests and the matching job serialize per account without deadlocks.
Nothing here commits; the caller owns the transaction.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import Stock
from app.paper_trading import rules
from app.paper_trading.models import PaperAccount, PaperOrder, PaperPosition, PaperTrade
from app.paper_trading.quotes import Quote
from app.risk_records import RiskEvent

RISK_LOOKBACK = timedelta(days=30)


def clock() -> datetime:
    return datetime.now(UTC)


class TradingError(Exception):
    """A business rule rejected the request; message is user facing."""


class NotFound(Exception):
    pass


class RiskConfirmationRequired(Exception):
    def __init__(self, event: RiskEvent):
        super().__init__("该股近期存在高风险事件，请确认后再买入")
        self.event = event


def lock_account(session: Session, owner_id: int, account_id: int) -> PaperAccount:
    account = session.scalar(
        select(PaperAccount)
        .where(PaperAccount.id == account_id, PaperAccount.owner_id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if account is None:
        raise NotFound("模拟账户不存在")
    return account


def stock_by_symbol(session: Session, symbol: str) -> Stock:
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None:
        raise NotFound("股票不存在")
    return stock


def refresh_t1(position: PaperPosition, today: date) -> None:
    if position.last_buy_date != today and position.today_bought:
        position.today_bought = 0


def sellable(position: PaperPosition | None, today: date) -> int:
    if position is None:
        return 0
    bought = position.today_bought if position.last_buy_date == today else 0
    return position.quantity - position.frozen_quantity - bought


def event_symbol():
    return RiskEvent.context["subject"]["symbol"].as_string()


def recent_risk_events(session: Session, owner_id: int, stocks: list[Stock], now: datetime):
    """Newest first. Auto analysis of stocks outside the local table stores only the symbol."""
    if not stocks:
        return []
    return list(session.scalars(
        select(RiskEvent)
        .where(
            RiskEvent.owner_id == owner_id,
            or_(RiskEvent.stock_id.in_([s.id for s in stocks]),
                event_symbol().in_([s.symbol for s in stocks])),
            RiskEvent.analyzed_at >= now - RISK_LOOKBACK,
        )
        .order_by(RiskEvent.analyzed_at.desc(), RiskEvent.id.desc())
    ))


def latest_risk_event(session: Session, owner_id: int, stock: Stock, now: datetime):
    events = recent_risk_events(session, owner_id, [stock], now)
    return events[0] if events else None


@dataclass(frozen=True)
class Market:
    """Validated live market facts for one order."""

    board: rules.Board
    price: Decimal
    lower: Decimal
    upper: Decimal
    quote_time: datetime


def live_market(quote: Quote | None, now: datetime) -> Market:
    if quote is None or quote.kind != "stock":
        raise TradingError("没有该股票的可信实时行情")
    if quote.stale or quote.price is None or quote.previous_close is None or not quote.quote_time:
        raise TradingError("实时行情暂不可用或已过期，暂不能成交")
    if problem := rules.live_quote_problem(quote.quote_time, now):
        raise TradingError(problem)
    board = rules.board_for(quote.symbol, quote.name, rules.trade_date(now))
    lower, upper = rules.price_band(quote.previous_close, board)
    return Market(board, quote.price, lower, upper, quote.quote_time)


def create_account(session: Session, owner_id: int, name: str, capital: Decimal,
                   commission_rate: Decimal, min_commission: Decimal) -> PaperAccount:
    if session.scalar(select(PaperAccount.id).where(
            PaperAccount.owner_id == owner_id, PaperAccount.name == name)):
        raise TradingError("已有同名模拟账户")
    account = PaperAccount(
        owner_id=owner_id, name=name, initial_capital=capital, cash=capital,
        frozen_cash=Decimal("0"), commission_rate=commission_rate,
        min_commission=min_commission, status="active", created_at=clock(),
    )
    session.add(account)
    session.flush()
    return account


def _apply_fill(session: Session, account: PaperAccount, order: PaperOrder,
                position: PaperPosition | None, price: Decimal, quote_time: datetime,
                now: datetime, *, reserved: bool) -> PaperTrade:
    today = rules.trade_date(now)
    cost = rules.fees(order.side, price, order.quantity, account.commission_rate,
                      account.min_commission)
    realized = None
    if order.side == "buy":
        # A pending buy reserved cash at its limit; the fill never costs more than that.
        account.frozen_cash -= order.frozen_amount
        spend = cost.amount + cost.total
        if spend > account.cash - account.frozen_cash:
            raise TradingError("可用资金不足")
        account.cash -= spend
        if position is None:
            position = PaperPosition(
                account_id=account.id, stock_id=order.stock_id, quantity=0,
                frozen_quantity=0, today_bought=0, cost_amount=Decimal("0"),
            )
            session.add(position)
        refresh_t1(position, today)
        position.quantity += order.quantity
        position.today_bought += order.quantity
        position.last_buy_date = today
        position.cost_amount += spend
    else:
        if position is None:
            raise TradingError("没有可卖持仓")
        if reserved:
            position.frozen_quantity -= order.quantity
        released = rules.money(position.cost_amount * order.quantity / position.quantity)
        proceeds = cost.amount - cost.total
        realized = proceeds - released
        account.cash += proceeds
        position.quantity -= order.quantity
        position.cost_amount -= released
    position.last_price = price
    position.last_price_at = quote_time
    if position.quantity == 0:
        session.delete(position)
    order.status = "filled"
    order.frozen_amount = Decimal("0")
    order.updated_at = now
    trade = PaperTrade(
        order_id=order.id, account_id=account.id, stock_id=order.stock_id, side=order.side,
        quantity=order.quantity, price=price, amount=cost.amount, commission=cost.commission,
        stamp_duty=cost.stamp_duty, transfer_fee=cost.transfer_fee, realized_pnl=realized,
        quote_time=quote_time, trade_date=today, executed_at=now,
    )
    session.add(trade)
    session.flush()
    return trade


def _fill_price(side: str, order_type: str, limit: Decimal | None, market: Market):
    """Return the fill price or None when the order must wait in the book."""
    # A sealed limit-up (buy) or limit-down (sell) board has no counterparty guarantee.
    if side == "buy" and market.price >= market.upper:
        return None
    if side == "sell" and market.price <= market.lower:
        return None
    if order_type == "market":
        return market.price
    marketable = market.price <= limit if side == "buy" else market.price >= limit
    return market.price if marketable else None


def place_order(session: Session, owner_id: int, account_id: int, stock: Stock,
                quote: Quote | None, *, side: str, order_type: str, quantity: int,
                limit_price: Decimal | None, acknowledged_risk_event_id: int | None = None,
                note: str | None = None) -> tuple[PaperOrder, PaperTrade | None]:
    now = clock()
    today = rules.trade_date(now)
    account = lock_account(session, owner_id, account_id)
    if account.status != "active":
        raise TradingError("模拟账户已停用")
    expire_orders(session, account, today, now)
    market = live_market(quote, now)
    if order_type == "limit":
        if limit_price is None:
            raise TradingError("限价单需要委托价格")
        if not market.lower <= limit_price <= market.upper:
            raise TradingError(f"委托价须在涨跌停范围 {market.lower} - {market.upper} 内")
    position = session.scalar(
        select(PaperPosition)
        .where(PaperPosition.account_id == account.id, PaperPosition.stock_id == stock.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if position is not None:
        refresh_t1(position, today)
    risk_event = None
    if side == "buy":
        if problem := rules.check_buy_quantity(quantity, market.board):
            raise TradingError(problem)
        risk_event = latest_risk_event(session, owner_id, stock, now)
        if risk_event and risk_event.risk_level == "high" and (
                acknowledged_risk_event_id != risk_event.id):
            raise RiskConfirmationRequired(risk_event)
    elif problem := rules.check_sell_quantity(quantity, sellable(position, today), market.board):
        raise TradingError(problem)

    fill = _fill_price(side, order_type, limit_price, market)
    if order_type == "market" and fill is None:
        raise TradingError("股票处于涨跌停封板，市价单无法成交，请改用限价单排队")
    order = PaperOrder(
        order_id=str(uuid4()), account_id=account.id, stock_id=stock.id, side=side,
        order_type=order_type, quantity=quantity, limit_price=limit_price,
        frozen_amount=Decimal("0"), status="pending", trade_date=today,
        risk_event_id=risk_event.id if risk_event else None, note=note,
        created_at=now, updated_at=now,
    )
    if fill is None:
        # Reserve resources so the resting order can always settle when it matches.
        if side == "buy":
            cost = rules.fees("buy", limit_price, quantity, account.commission_rate,
                              account.min_commission)
            reserve = cost.amount + cost.total
            if reserve > account.cash - account.frozen_cash:
                raise TradingError("可用资金不足")
            account.frozen_cash += reserve
            order.frozen_amount = reserve
        else:
            position.frozen_quantity += quantity
        session.add(order)
        session.flush()
        return order, None
    session.add(order)
    session.flush()
    trade = _apply_fill(session, account, order, position, fill, market.quote_time, now,
                        reserved=False)
    return order, trade


def _release(account: PaperAccount, order: PaperOrder, position: PaperPosition | None) -> None:
    if order.side == "buy":
        account.frozen_cash -= order.frozen_amount
        order.frozen_amount = Decimal("0")
    elif position is not None:
        position.frozen_quantity -= order.quantity


def cancel_order(session: Session, owner_id: int, order_uuid: str) -> PaperOrder:
    found = session.execute(
        select(PaperOrder.account_id)
        .join(PaperAccount, PaperOrder.account_id == PaperAccount.id)
        .where(PaperOrder.order_id == order_uuid, PaperAccount.owner_id == owner_id)
    ).first()
    if found is None:
        raise NotFound("委托不存在")
    account = lock_account(session, owner_id, found.account_id)
    order = session.scalar(
        select(PaperOrder).where(PaperOrder.order_id == order_uuid).with_for_update()
        .execution_options(populate_existing=True)
    )
    if order.status != "pending":
        raise TradingError("委托已结束，无法撤单")
    position = _locked_position(session, account.id, order.stock_id)
    _release(account, order, position)
    now = clock()
    order.status = "cancelled"
    order.updated_at = now
    session.flush()
    return order


def _locked_position(session: Session, account_id: int, stock_id: int):
    return session.scalar(
        select(PaperPosition)
        .where(PaperPosition.account_id == account_id, PaperPosition.stock_id == stock_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def expire_orders(session: Session, account: PaperAccount, today: date, now: datetime) -> int:
    """Day orders end with their trade date; caller must hold the account lock."""
    orders = session.scalars(
        select(PaperOrder)
        .where(
            PaperOrder.account_id == account.id,
            PaperOrder.status == "pending",
            PaperOrder.trade_date < today,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    for order in orders:
        _release(account, order, _locked_position(session, account.id, order.stock_id))
        order.status = "expired"
        order.updated_at = now
    session.flush()
    return len(orders)


def pending_symbols(session: Session, account_ids=None) -> list[str]:
    query = (
        select(Stock.symbol)
        .join(PaperOrder, PaperOrder.stock_id == Stock.id)
        .where(PaperOrder.status == "pending")
        .distinct()
    )
    if account_ids is not None:
        query = query.where(PaperOrder.account_id.in_(account_ids))
    return list(session.scalars(query))


def match_account(session: Session, account_id: int, quotes: dict[str, Quote]) -> int:
    """Fill resting orders of one account that are marketable against live quotes."""
    now = clock()
    today = rules.trade_date(now)
    account = session.scalar(
        select(PaperAccount).where(PaperAccount.id == account_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if account is None:
        return 0
    expire_orders(session, account, today, now)
    rows = session.execute(
        select(PaperOrder, Stock.symbol)
        .join(Stock, Stock.id == PaperOrder.stock_id)
        .where(PaperOrder.account_id == account.id, PaperOrder.status == "pending")
        .order_by(PaperOrder.created_at, PaperOrder.id)
        .with_for_update(of=PaperOrder)
        .execution_options(populate_existing=True)
    ).all()
    filled = 0
    for order, symbol in rows:
        try:
            market = live_market(quotes.get(symbol), now)
        except TradingError:
            continue
        price = _fill_price(order.side, order.order_type, order.limit_price, market)
        if price is None:
            continue
        position = _locked_position(session, account.id, order.stock_id)
        if position is not None:
            refresh_t1(position, today)
        try:
            with session.begin_nested():
                _apply_fill(session, account, order, position, price, market.quote_time, now,
                            reserved=True)
        except TradingError:
            continue
        filled += 1
    return filled
