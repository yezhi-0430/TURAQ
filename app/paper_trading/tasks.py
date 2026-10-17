"""Scheduled matching and end-of-day snapshots for paper accounts."""

import logging
from datetime import timedelta

from sqlalchemy import select

from app.database import SessionLocal, Stock
from app.paper_trading import performance, rules, service
from app.paper_trading.models import PaperAccount, PaperOrder, PaperPosition
from app.paper_trading.quotes import load_quotes

logger = logging.getLogger(__name__)
INDEX = "000300.SH"


async def match_pending_orders() -> int:
    """Resting limit orders fill when a live quote crosses them; each account commits alone."""
    if not rules.in_session(service.clock()):
        return 0
    with SessionLocal() as session:
        accounts = list(session.scalars(
            select(PaperOrder.account_id).where(PaperOrder.status == "pending").distinct()
        ))
        symbols = service.pending_symbols(session)
    if not accounts:
        return 0
    quotes = await load_quotes(symbols)
    filled = 0
    for account_id in accounts:
        try:
            with SessionLocal() as session:
                filled += service.match_account(session, account_id, quotes)
                session.commit()
        except Exception:
            logger.exception("paper_trading_match_failed account_id=%s", account_id)
    if filled:
        logger.info("paper_trading_matched orders=%d", filled)
    return filled


async def record_daily_snapshots() -> int:
    """Expire day orders and store closing valuations; reruns overwrite the same date."""
    now = service.clock()
    today = rules.trade_date(now)
    if now.astimezone(rules.SHANGHAI).weekday() >= 5:
        return 0
    with SessionLocal() as session:
        accounts = list(session.scalars(
            select(PaperAccount.id).where(PaperAccount.status == "active")
        ))
        symbols = list(session.scalars(
            select(Stock.symbol).join(PaperPosition, PaperPosition.stock_id == Stock.id).distinct()
        ))
    quotes = await load_quotes([INDEX, *symbols])
    # No same-day index quote means a holiday; skip instead of recording a flat fake day.
    index = quotes.get(INDEX)
    if index is None or index.quote_time is None or rules.trade_date(index.quote_time) != today:
        logger.info("paper_trading_snapshot_skipped reason=no_trading_day date=%s", today)
        return 0
    saved = 0
    for account_id in accounts:
        try:
            with SessionLocal() as session:
                account = session.scalar(
                    select(PaperAccount).where(PaperAccount.id == account_id).with_for_update()
                )
                service.expire_orders(session, account, today + timedelta(days=1), now)
                valuation = performance.value_account(session, account, quotes, now,
                                                      persist_prices=True)
                performance.save_snapshot(session, account, valuation, today)
                session.commit()
                saved += 1
        except Exception:
            logger.exception("paper_trading_snapshot_failed account_id=%s", account_id)
    logger.info("paper_trading_snapshots saved=%d date=%s", saved, today)
    return saved

