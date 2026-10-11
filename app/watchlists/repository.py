from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Stock, Watchlist, WatchlistItem


class WatchlistNotFoundError(Exception):
    pass


class DuplicateStockInWatchlistError(Exception):
    pass


class StockNotInWatchlistError(Exception):
    pass


def create_watchlist(session: Session, name: str, *, actor_id: int) -> Watchlist:
    watchlist = Watchlist(name=name, owner_id=actor_id)
    session.add(watchlist)
    session.commit()
    session.refresh(watchlist)
    return watchlist


def get_watchlists(session: Session, *, actor_id: int) -> list[Watchlist]:
    statement = select(Watchlist).where(Watchlist.owner_id == actor_id).order_by(Watchlist.id)
    return list(session.scalars(statement).all())


def add_stock_to_watchlist(
    session: Session,
    watchlist_id: int,
    symbol: str,
    name: str,
    *,
    actor_id: int,
) -> Stock:
    symbol = symbol.strip().upper()
    watchlist = session.scalar(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.owner_id == actor_id)
    )
    if watchlist is None:
        raise WatchlistNotFoundError

    stock_statement = select(Stock).where(Stock.symbol == symbol)
    stock = session.scalar(stock_statement)
    if stock is None:
        raise LookupError("股票不存在")

    item_statement = select(WatchlistItem).where(
        WatchlistItem.watchlist_id == watchlist_id,
        WatchlistItem.stock_id == stock.id,
    )
    if stock.id is not None and session.scalar(item_statement) is not None:
        raise DuplicateStockInWatchlistError

    try:
        with session.begin_nested():
            session.add(WatchlistItem(watchlist_id=watchlist_id, stock_id=stock.id))
            session.flush()
    except IntegrityError as exc:
        if session.scalar(item_statement) is not None:
            raise DuplicateStockInWatchlistError from exc
        raise
    session.commit()
    session.refresh(stock)
    return stock


def remove_stock_from_watchlist(
    session: Session,
    watchlist_id: int,
    symbol: str,
    *,
    actor_id: int,
    commit: bool = True,
) -> None:
    symbol = symbol.strip().upper()
    watchlist = session.scalar(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.owner_id == actor_id)
    )
    if watchlist is None:
        raise WatchlistNotFoundError

    statement = (
        select(WatchlistItem)
        .join(Stock, WatchlistItem.stock_id == Stock.id)
        .where(
            WatchlistItem.watchlist_id == watchlist_id,
            Stock.symbol == symbol,
        )
    )
    item = session.scalar(statement)
    if item is None:
        raise StockNotInWatchlistError

    # A concurrent request may remove the row after our read. ORM deletion
    # only warns on zero matches; inspect the atomic DELETE count instead.
    deleted = session.execute(
        delete(WatchlistItem)
        .where(WatchlistItem.id == item.id)
        .execution_options(synchronize_session=False)
    )
    if deleted.rowcount != 1:
        session.rollback()
        raise StockNotInWatchlistError
    if commit:
        session.commit()
