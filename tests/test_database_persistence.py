import pytest
from sqlalchemy.exc import IntegrityError

from app.database import (
    SessionLocal,
    Stock,
    Watchlist,
    WatchlistItem,
)


def test_watchlist_persists_across_sessions() -> None:
    with SessionLocal() as write_session:
        watchlist = Watchlist(owner_id=1, name="持久化测试")
        write_session.add(watchlist)
        write_session.commit()
        watchlist_id = watchlist.id

    try:
        with SessionLocal() as read_session:
            saved_watchlist = read_session.get(
                Watchlist,
                watchlist_id,
            )

            assert saved_watchlist is not None
            assert saved_watchlist.name == "持久化测试"
    finally:
        with SessionLocal() as cleanup_session:
            saved_watchlist = cleanup_session.get(
                Watchlist,
                watchlist_id,
            )
            if saved_watchlist is not None:
                cleanup_session.delete(saved_watchlist)
                cleanup_session.commit()


def test_rejects_duplicate_stock_in_same_watchlist() -> None:
    with SessionLocal() as session:
        watchlist = Watchlist(owner_id=1, name="重复约束测试")
        stock = Stock(
            symbol="600519.SH",
            name="贵州茅台",
        )
        session.add_all([watchlist, stock])
        session.commit()

        first_item = WatchlistItem(
            watchlist_id=watchlist.id,
            stock_id=stock.id,
        )
        session.add(first_item)
        session.commit()

        duplicate_item = WatchlistItem(
            watchlist_id=watchlist.id,
            stock_id=stock.id,
        )
        session.add(duplicate_item)

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()

        session.delete(first_item)
        session.commit()

        session.delete(stock)
        session.delete(watchlist)
        session.commit()
