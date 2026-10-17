"""Trusted metadata lookup for adding previously unseen shared symbols."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import Stock
from app.market import normalize_symbol
from app.market_api import service


async def resolve_stock(session, symbol: str) -> None:
    code = normalize_symbol(symbol)
    canonical = code[2:] + "." + code[:2].upper()
    if canonical != symbol:
        raise LookupError("股票代码须使用标准格式")
    if session.scalar(select(Stock).where(Stock.symbol == symbol)):
        return
    snapshot = await service.quotes([symbol])
    quote = next(
        (
            q
            for q in snapshot.get("quotes", [])
            if q.get("symbol") == symbol
            and q.get("kind") == "stock"
            and not q.get("stale")
            and q.get("name")
        ),
        None,
    )
    if quote is None:
        raise LookupError("股票不存在或可信行情暂不可用")
    try:
        with session.begin_nested():
            session.add(Stock(symbol=symbol, name=quote["name"]))
            session.flush()
    except IntegrityError:
        if session.scalar(select(Stock).where(Stock.symbol == symbol)) is None:
            raise
