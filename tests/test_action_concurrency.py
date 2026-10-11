"""Reproduce a stale ORM read with a second real, committed transaction."""

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.agent_actions import ExecutionRequest, execute_watchlist_removal
from app.database import SessionLocal, Stock, Watchlist, WatchlistItem, engine


@pytest.mark.parametrize("recreate", [False, True])
def test_interleaved_removal_does_not_claim_a_zero_row_delete_succeeded(recreate):
    with SessionLocal() as session:
        stock = Stock(symbol="000001.SZ", name="保留股票资料")
        group = Watchlist(owner_id=1, name="交错删除测试")
        session.add_all([stock, group])
        session.flush()
        stock_id, group_id = stock.id, group.id
        item = WatchlistItem(stock_id=stock_id, watchlist_id=group_id)
        session.add(item)
        session.commit()
        old_item_id = item.id

    class InterleavedSession(Session):
        pass

    removed = []

    def concurrent_removal(session, instance):
        if not isinstance(instance, WatchlistItem):
            return
        # The outer transaction has fetched this object. Another transaction now
        # removes it before the outer ORM DELETE can run, optionally re-adding it.
        with SessionLocal() as rival:
            rival.execute(delete(WatchlistItem).where(WatchlistItem.id == instance.id))
            if recreate:
                rival.add(WatchlistItem(stock_id=stock_id, watchlist_id=group_id))
            rival.commit()
        removed.append(instance.id)

    event.listen(InterleavedSession, "loaded_as_persistent", concurrent_removal)
    factory = sessionmaker(bind=engine, class_=InterleavedSession)
    result = execute_watchlist_removal(
        ExecutionRequest(
            kind="execution_request",
            operation="remove_watchlist_stock",
            watchlist_id=group_id,
            stock_code="000001.SZ",
        ),
        session_factory=factory,
        actor_id=1,
    )
    assert removed == [old_item_id]
    assert result.status == "error"
    assert result.error.kind == "stock_not_in_watchlist"
    with SessionLocal() as session:
        assert session.get(Stock, stock_id) is not None
        assert session.get(Watchlist, group_id) is not None
        items = session.scalars(select(WatchlistItem)).all()
        assert len(items) == int(recreate)
        if recreate:
            assert items[0].id != old_item_id
            assert (items[0].watchlist_id, items[0].stock_id) == (group_id, stock_id)
