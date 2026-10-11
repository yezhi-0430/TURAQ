import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError

from app.agent_api import router as agent_router
from app.auth.api import router as auth_router
from app.auth.dependencies import Actor, require_actor, require_admin
from app.database import DailyPrice, SessionLocal, Stock, Watchlist, WatchlistItem
from app.json_requests import DecimalJSONRoute
from app.market_api import router as market_router
from app.risk_api import router as risk_router
from app.watchlists.metadata import resolve_stock
from app.watchlists.repository import (
    DuplicateStockInWatchlistError,
    StockNotInWatchlistError,
    WatchlistNotFoundError,
    add_stock_to_watchlist,
    get_watchlists,
    remove_stock_from_watchlist,
)
from app.watchlists.repository import create_watchlist as save_watchlist

logger = logging.getLogger(__name__)


class CreateWatchlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class AddStockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


Price = Annotated[Decimal, Field(gt=0, allow_inf_nan=False, max_digits=18, decimal_places=4)]


class DailyPriceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trade_date: date
    open: Price
    high: Price
    low: Price
    close: Price
    volume: int = Field(ge=0, le=9223372036854775807)

    @model_validator(mode="after")
    def validate_price_range(self) -> Self:
        if self.low > self.high:
            raise ValueError("最低价不能高于最高价")
        if not self.low <= self.open <= self.high:
            raise ValueError("开盘价必须在最低价和最高价之间")
        if not self.low <= self.close <= self.high:
            raise ValueError("收盘价必须在最低价和最高价之间")
        return self


def create_app() -> FastAPI:
    application = FastAPI(
        title="A 股自选股风险监控 Agent",
        version="0.1.0",
    )

    application.include_router(auth_router)
    application.include_router(risk_router)
    application.include_router(agent_router)
    application.include_router(market_router)
    price_router = APIRouter(route_class=DecimalJSONRoute)

    @application.exception_handler(RequestValidationError)
    async def handle_invalid_request(request: Request, exc: RequestValidationError):
        # Validation errors must not echo credentials, tokens or entire request bodies.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": error["loc"], "type": error["type"], "msg": error["msg"]}
                    for error in exc.errors()
                ]
            },
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error("未处理的应用异常: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误"},
        )

    @application.middleware("http")
    async def protect_exception_details(request: Request, call_next):
        # Consume unexpected errors before the server can log credential-bearing tracebacks.
        try:
            return await call_next(request)
        except Exception as exc:
            return await handle_unexpected_error(request, exc)

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/v1/stocks/{symbol}", tags=["stocks"])
    async def get_stock(symbol: str, actor: Actor = Depends(require_actor)) -> dict[str, str]:
        return {"symbol": symbol.upper()}

    @price_router.post("/api/v1/stocks/{symbol}/daily-prices", status_code=201)
    def import_daily_price(
        symbol: str,
        payload: DailyPriceRequest,
        actor: Actor = Depends(require_admin),
    ):
        with SessionLocal() as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == symbol.strip().upper()))

            if stock is None:
                raise HTTPException(status_code=404, detail="股票不存在")

            daily_price = DailyPrice(
                stock_id=stock.id,
                trade_date=payload.trade_date,
                open=payload.open,
                high=payload.high,
                low=payload.low,
                close=payload.close,
                volume=payload.volume,
            )

            session.add(daily_price)

            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="该股票当天的日线数据已存在",
                ) from exc

        return {"symbol": symbol.strip().upper()}

    application.include_router(price_router)

    @application.get("/api/v1/stocks/{symbol}/daily-prices")
    def get_daily_prices(
        symbol: str, actor: Actor = Depends(require_actor)
    ) -> list[dict[str, object]]:
        with SessionLocal() as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == symbol.strip().upper()))

            if stock is None:
                raise HTTPException(status_code=404, detail="股票不存在")

            daily_prices = session.scalars(
                select(DailyPrice)
                .where(DailyPrice.stock_id == stock.id)
                .order_by(DailyPrice.trade_date.desc())
            ).all()

            return [
                {
                    "trade_date": item.trade_date.isoformat(),
                    "open": str(item.open),
                    "high": str(item.high),
                    "low": str(item.low),
                    "close": str(item.close),
                    "volume": item.volume,
                }
                for item in daily_prices
            ]

    @application.get("/api/v1/stocks", tags=["stocks"])
    def search_stocks(query: str, actor: Actor = Depends(require_actor)) -> list[dict[str, str]]:
        query = query.strip()
        if not query:
            return []
        with SessionLocal() as session:
            stocks = session.scalars(
                select(Stock)
                .where(
                    or_(
                        Stock.name.contains(query, autoescape=True),
                        Stock.symbol.contains(query.upper(), autoescape=True),
                    )
                )
                .order_by(Stock.symbol)
                .limit(30)
            ).all()
            return [{"symbol": stock.symbol, "name": stock.name} for stock in stocks]

    @application.patch("/api/v1/watchlists/{watchlist_id}", tags=["watchlists"])
    def rename_watchlist(
        watchlist_id: int, payload: CreateWatchlistRequest, actor: Actor = Depends(require_actor)
    ):
        with SessionLocal() as session:
            group = session.scalar(
                select(Watchlist)
                .where(Watchlist.id == watchlist_id, Watchlist.owner_id == actor.id)
                .with_for_update()
            )
            if group is None:
                raise HTTPException(404, "自选组不存在")
            group.name = payload.name
            session.commit()
            return {"id": group.id, "name": group.name}

    @application.delete("/api/v1/watchlists/{watchlist_id}", status_code=204, tags=["watchlists"])
    def delete_watchlist(watchlist_id: int, actor: Actor = Depends(require_actor)):
        with SessionLocal() as session:
            group = session.scalar(
                select(Watchlist)
                .where(Watchlist.id == watchlist_id, Watchlist.owner_id == actor.id)
                .with_for_update()
            )
            if group is None:
                raise HTTPException(404, "自选组不存在")
            session.execute(delete(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id))
            session.delete(group)
            session.commit()

    @application.get("/api/v1/watchlists/{watchlist_id}/stocks", tags=["watchlists"])
    def list_watchlist_stocks(
        watchlist_id: int, actor: Actor = Depends(require_actor)
    ) -> list[dict[str, str]]:
        with SessionLocal() as session:
            if (
                session.scalar(
                    select(Watchlist)
                    .where(Watchlist.id == watchlist_id, Watchlist.owner_id == actor.id)
                    .with_for_update()
                )
                is None
            ):
                raise HTTPException(404, "自选组不存在")
            stocks = session.scalars(
                select(Stock)
                .join(WatchlistItem)
                .where(WatchlistItem.watchlist_id == watchlist_id)
                .order_by(Stock.symbol)
            ).all()
            return [{"symbol": stock.symbol, "name": stock.name} for stock in stocks]

    @application.post(
        "/api/v1/watchlists",
        tags=["watchlists"],
        status_code=status.HTTP_201_CREATED,
    )
    def create_watchlist(
        payload: CreateWatchlistRequest,
        actor: Actor = Depends(require_actor),
    ) -> dict[str, int | str]:
        with SessionLocal() as session:
            watchlist = save_watchlist(session, payload.name, actor_id=actor.id)
            return {
                "id": watchlist.id,
                "name": watchlist.name,
            }

    @application.get("/api/v1/watchlists", tags=["watchlists"])
    def list_watchlists(actor: Actor = Depends(require_actor)) -> list[dict[str, int | str]]:
        with SessionLocal() as session:
            watchlists = get_watchlists(session, actor_id=actor.id)

            return [
                {
                    "id": watchlist.id,
                    "name": watchlist.name,
                }
                for watchlist in watchlists
            ]

    @application.post(
        "/api/v1/watchlists/{watchlist_id}/stocks",
        tags=["watchlists"],
        status_code=status.HTTP_201_CREATED,
    )
    async def add_stock(
        watchlist_id: int,
        payload: AddStockRequest,
        actor: Actor = Depends(require_actor),
    ) -> dict[str, str]:
        with SessionLocal() as session:
            try:
                owned = session.scalar(
                    select(Watchlist).where(
                        Watchlist.id == watchlist_id, Watchlist.owner_id == actor.id
                    )
                )
                if owned is None:
                    raise WatchlistNotFoundError
                await resolve_stock(session, payload.symbol)
                stock = add_stock_to_watchlist(
                    session,
                    watchlist_id,
                    payload.symbol,
                    payload.name,
                    actor_id=actor.id,
                )
            except WatchlistNotFoundError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="自选组不存在",
                ) from exc
            except (LookupError, ValueError) as exc:
                raise HTTPException(404, "股票不存在") from exc
            except DuplicateStockInWatchlistError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="该股票已在自选组中",
                ) from exc

            return {
                "symbol": stock.symbol,
                "name": stock.name,
            }

    @application.delete(
        "/api/v1/watchlists/{watchlist_id}/stocks/{symbol}",
        tags=["watchlists"],
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def remove_stock(watchlist_id: int, symbol: str, actor: Actor = Depends(require_actor)) -> None:
        with SessionLocal() as session:
            try:
                remove_stock_from_watchlist(session, watchlist_id, symbol, actor_id=actor.id)
            except WatchlistNotFoundError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="自选组不存在",
                ) from exc
            except StockNotInWatchlistError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="自选组中不存在该股票",
                ) from exc

    return application


app = create_app()
