"""Valuation, daily snapshots and performance metrics from recorded real data."""

import math
import statistics
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import Stock
from app.paper_trading import rules
from app.paper_trading.models import PaperAccount, PaperPosition, PaperSnapshot, PaperTrade
from app.paper_trading.quotes import Quote

TRADING_DAYS = 250
MIN_RETURNS_FOR_RISK = 5
DAY_PNL_LOOKBACK_DAYS = 15  # covers the Spring Festival / National Day closures


def holdings(session: Session, account_id: int):
    return session.execute(
        select(PaperPosition, Stock)
        .join(Stock, Stock.id == PaperPosition.stock_id)
        .where(PaperPosition.account_id == account_id)
        .order_by(Stock.symbol)
    ).all()


def value_account(session: Session, account: PaperAccount, quotes: dict[str, Quote],
                  now: datetime, *, persist_prices: bool = False) -> dict:
    """Mark holdings to real quotes; without one, fall back to the last real fill/mark price."""
    today = rules.trade_date(now)
    rows, market_value, complete = [], Decimal("0"), True
    for position, stock in holdings(session, account.id):
        quote = quotes.get(stock.symbol)
        price, quote_time, live = position.last_price, position.last_price_at, False
        if quote and quote.price is not None and not quote.stale and quote.quote_time:
            price, quote_time, live = quote.price, quote.quote_time, True
            if persist_prices:
                position.last_price, position.last_price_at = price, quote_time
        if not live or rules.trade_date(quote_time) != today:
            complete = False
        value = rules.money(price * position.quantity) if price is not None else Decimal("0")
        market_value += value
        bought = position.today_bought if position.last_buy_date == today else 0
        rows.append({
            "symbol": stock.symbol,
            "name": quote.name if quote else stock.name,
            "quantity": position.quantity,
            "sellable": position.quantity - position.frozen_quantity - bought,
            "frozen": position.frozen_quantity,
            "cost_amount": position.cost_amount,
            "average_cost": rules.money(position.cost_amount / position.quantity),
            "price": price,
            "previous_close": quote.previous_close if quote else None,
            "price_time": quote_time,
            "price_live": live,
            "market_value": value,
            "unrealized_pnl": value - position.cost_amount,
            "unrealized_pct": ratio(value - position.cost_amount, position.cost_amount),
        })
    total = account.cash + market_value
    for row in rows:
        row["weight"] = ratio(row["market_value"], total)
    return {
        "cash": account.cash,
        "frozen_cash": account.frozen_cash,
        "available_cash": account.cash - account.frozen_cash,
        "market_value": market_value,
        "total_assets": total,
        "total_return": ratio(total - account.initial_capital, account.initial_capital),
        "valuation_complete": complete,
        "positions": rows,
    }


def recent_trade_symbols(session: Session, account_id: int, today: date) -> list[str]:
    """Symbols traded recently: a stock sold out today still has a day P&L."""
    return list(session.scalars(
        select(Stock.symbol).join(PaperTrade, PaperTrade.stock_id == Stock.id)
        .where(PaperTrade.account_id == account_id,
               PaperTrade.trade_date >= today - timedelta(days=DAY_PNL_LOOKBACK_DAYS))
        .distinct()
    ))


def day_pnl(session: Session, account: PaperAccount, quotes: dict[str, Quote],
            now: datetime) -> dict:
    """P&L of the latest trading day against the exchange's previous close.

    Per stock: held*price - overnight*previous_close + sells - buys - fees, where
    overnight = held - bought + sold. Cash only moves through fills, so the sum is the
    account's change since the previous close, exact on day one and without a snapshot.
    """
    held = {stock.symbol: position.quantity for position, stock in holdings(session, account.id)}
    traded = recent_trade_symbols(session, account.id, rules.trade_date(now))
    live = {s: q for s, q in quotes.items()
            if q.price is not None and not q.stale and q.quote_time is not None}
    days = [rules.trade_date(live[s].quote_time) for s in {*held, *traded} if s in live]
    # Before the open and on weekends this is the last session, labelled by its date.
    day = max(days) if days else rules.trade_date(now)
    flows: dict[str, dict] = {}
    for trade, symbol in session.execute(
        select(PaperTrade, Stock.symbol).join(Stock, Stock.id == PaperTrade.stock_id)
        .where(PaperTrade.account_id == account.id, PaperTrade.trade_date == day)
    ):
        flow = flows.setdefault(symbol, {"bought": 0, "sold": 0, "buys": Decimal("0"),
                                         "sells": Decimal("0"), "fees": Decimal("0")})
        if trade.side == "buy":
            flow["bought"] += trade.quantity
            flow["buys"] += trade.amount
        else:
            flow["sold"] += trade.quantity
            flow["sells"] += trade.amount
        flow["fees"] += trade.commission + trade.stamp_duty + trade.transfer_fee
    per_symbol, complete = {}, True
    total, base_total, closed = Decimal("0"), account.cash, Decimal("0")
    for symbol in sorted({*held, *flows}):
        flow = flows.get(symbol, {"bought": 0, "sold": 0, "buys": Decimal("0"),
                                  "sells": Decimal("0"), "fees": Decimal("0")})
        quantity = held.get(symbol, 0)
        overnight = quantity - flow["bought"] + flow["sold"]
        quote = live.get(symbol)
        on_day = quote is not None and rules.trade_date(quote.quote_time) == day
        suspended = quote is not None and not on_day and symbol not in flows
        needs_quote = quantity or overnight
        if overnight < 0 or (needs_quote and not suspended and not on_day) or (
                on_day and overnight and quote.previous_close is None):
            per_symbol[symbol] = None
            complete = False
            continue
        if suspended:
            # No print on this day (suspension): the holding did not move.
            per_symbol[symbol] = {"day_pnl": Decimal("0.00"), "day_pct": Decimal("0"),
                                  "day_suspended": True}
            base_total += rules.money(quote.price * quantity)
            continue
        value = rules.money(quote.price * quantity) if quantity else Decimal("0")
        previous = rules.money(quote.previous_close * overnight) if overnight else Decimal("0")
        pnl = value - previous + flow["sells"] - flow["buys"] - flow["fees"]
        per_symbol[symbol] = {"day_pnl": pnl, "day_pct": ratio(pnl, previous + flow["buys"])}
        total += pnl
        # Yesterday's total: today's cash before these fills plus overnight shares at close.
        base_total += previous - flow["sells"] + flow["buys"] + flow["fees"]
        if not quantity:
            closed += pnl
    return {
        "date": day,
        "is_today": day == rules.trade_date(now),
        "complete": complete,
        "pnl": total if complete else None,
        "return": ratio(total, base_total) if complete else None,
        "closed_pnl": closed if complete else None,
        "positions": per_symbol,
    }


def ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if not denominator:
        return None
    return (numerator / denominator).quantize(Decimal("0.000001"))


def save_snapshot(session: Session, account: PaperAccount, valuation: dict, day: date) -> None:
    """Idempotent per account/day: re-running after close overwrites with the latest marks."""
    values = dict(
        account_id=account.id, snapshot_date=day, cash=valuation["cash"],
        market_value=valuation["market_value"], total_assets=valuation["total_assets"],
        complete=valuation["valuation_complete"],
    )
    session.execute(
        insert(PaperSnapshot).values(**values).on_conflict_do_update(
            constraint="uq_paper_snapshot_date",
            set_={k: values[k] for k in ("cash", "market_value", "total_assets", "complete")},
        )
    )


def snapshots(session: Session, account_id: int) -> list[PaperSnapshot]:
    return list(session.scalars(
        select(PaperSnapshot)
        .where(PaperSnapshot.account_id == account_id)
        .order_by(PaperSnapshot.snapshot_date)
    ))


def daily_returns(values: list[Decimal]) -> list[float]:
    return [float(b / a - 1) for a, b in zip(values, values[1:], strict=False) if a > 0]


def max_drawdown(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    peak, worst = values[0], Decimal("0")
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst.quantize(Decimal("0.000001"))


def risk_metrics(returns: list[float], risk_free: float = 0.0) -> dict:
    """Annualized only with enough observations; otherwise report None, never a fake 0."""
    if len(returns) < MIN_RETURNS_FOR_RISK:
        return {"volatility": None, "sharpe": None}
    std = statistics.stdev(returns)
    volatility = std * math.sqrt(TRADING_DAYS)
    if std == 0:
        return {"volatility": round(volatility, 6), "sharpe": None}
    excess = statistics.mean(returns) - risk_free / TRADING_DAYS
    return {"volatility": round(volatility, 6),
            "sharpe": round(excess / std * math.sqrt(TRADING_DAYS), 4)}


def trade_stats(session: Session, account_id: int) -> dict:
    trades = list(session.scalars(
        select(PaperTrade).where(PaperTrade.account_id == account_id)
    ))
    closed = [t.realized_pnl for t in trades if t.side == "sell" and t.realized_pnl is not None]
    wins = [p for p in closed if p > 0]
    losses = [p for p in closed if p < 0]
    fees = sum((t.commission + t.stamp_duty + t.transfer_fee for t in trades), Decimal("0"))
    return {
        "trade_count": len(trades),
        "buy_count": sum(t.side == "buy" for t in trades),
        "sell_count": len(closed),
        "win_rate": ratio(Decimal(len(wins)), Decimal(len(closed))),
        "realized_pnl": sum(closed, Decimal("0")),
        "average_win": rules.money(sum(wins, Decimal("0")) / len(wins)) if wins else None,
        "average_loss": rules.money(sum(losses, Decimal("0")) / len(losses)) if losses else None,
        "profit_factor": ratio(sum(wins, Decimal("0")), -sum(losses, Decimal("0")))
        if losses else None,
        "total_fees": fees,
    }


def performance(session: Session, account: PaperAccount, valuation: dict) -> dict:
    series = snapshots(session, account.id)
    values = [account.initial_capital] + [s.total_assets for s in series]
    returns = daily_returns([s.total_assets for s in series])
    return {
        "initial_capital": account.initial_capital,
        "total_assets": valuation["total_assets"],
        "total_return": valuation["total_return"],
        "max_drawdown": max_drawdown(values + [valuation["total_assets"]]),
        "snapshot_days": len(series),
        "incomplete_snapshot_days": sum(not s.complete for s in series),
        **risk_metrics(returns),
        **trade_stats(session, account.id),
    }
