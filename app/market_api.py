"""Market dashboard endpoints; read-only, independent of the model client."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import Actor, require_actor
from app.database import SessionLocal, Stock, Watchlist, WatchlistItem
from app.market import INDICES, MarketService

router = APIRouter(prefix="/api/v1/market", tags=["market"], dependencies=[Depends(require_actor)])
service = MarketService()


@router.get("/quotes")
async def quotes(symbols: str = Query(",".join(INDICES), max_length=600)):
    try:
        return await service.quotes(symbols.split(","))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/minutes/{symbol}")
async def minutes(symbol: str):
    try:
        return await service.minutes(symbol)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/watchlist")
def watchlist(actor: Actor = Depends(require_actor)):
    try:
        with SessionLocal() as session:
            stocks = session.scalars(
                select(Stock)
                .join(WatchlistItem)
                .join(Watchlist)
                .where(Watchlist.owner_id == actor.id)
                .distinct()
                .order_by(Stock.symbol)
                .limit(31)
            ).all()
            return {
                "stocks": [{"symbol": s.symbol, "name": s.name} for s in stocks[:30]],
                "truncated": len(stocks) > 30,
                "error": None,
            }
    except SQLAlchemyError:
        return {
            "stocks": [],
            "truncated": False,
            "error": "自选股数据库暂不可用，仍可输入代码查询行情",
        }


@router.get("/klines/{symbol}")
async def klines(
    symbol: str,
    period: str = Query("day", pattern="^(day|week|month)$"),
    adjustment: str = Query("none", pattern="^(none|qfq|hfq)$"),
):
    try:
        return await service.klines(symbol, period, adjustment)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
