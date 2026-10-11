from datetime import date

import pytest
from sqlalchemy import BigInteger, inspect, select, text

from app import schema_upgrade
from app.database import DailyPrice, SessionLocal, Stock, Watchlist, WatchlistItem, engine


def test_upgrade_preserves_existing_records_and_is_idempotent():
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE daily_prices ALTER COLUMN volume TYPE INTEGER"))
    with SessionLocal() as session:
        stock = Stock(symbol="000001.sz", name="保留名称")
        group = Watchlist(name="保留自选组")
        session.add_all([stock, group])
        session.flush()
        stock_id, group_id = stock.id, group.id
        session.add(WatchlistItem(stock_id=stock_id, watchlist_id=group_id))
        session.add(
            DailyPrice(
                stock_id=stock_id,
                trade_date=date(2026, 9, 25),
                open="10",
                high="11",
                low="9",
                close="10",
                volume=100,
            )
        )
        session.commit()
    schema_upgrade.upgrade_database(engine)
    schema_upgrade.upgrade_database(engine)
    column = next(
        item for item in inspect(engine).get_columns("daily_prices") if item["name"] == "volume"
    )
    assert isinstance(column["type"], BigInteger)
    with SessionLocal() as session:
        stock = session.get(Stock, stock_id)
        assert stock.symbol == "000001.SZ"
        assert stock.name == "保留名称"
        assert session.scalar(select(WatchlistItem)).watchlist_id == group_id
        assert session.scalar(select(DailyPrice)).volume == 100


def test_upgrade_reports_case_collisions_without_merging_records():
    with SessionLocal() as session:
        session.add_all(
            [
                Stock(symbol="000001.sz", name="甲"),
                Stock(symbol="000001.SZ", name="乙"),
            ]
        )
        session.commit()
    with pytest.raises(ValueError, match="股票代码归一化冲突"):
        schema_upgrade.upgrade_database(engine)
    with SessionLocal() as session:
        assert set(session.scalars(select(Stock.symbol))) == {"000001.sz", "000001.SZ"}


def test_upgrade_adds_nullable_source_without_inventing_legacy_provenance():
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tool_audit_records DROP COLUMN IF EXISTS source"))
        connection.execute(
            text("""
            INSERT INTO tool_audit_records
                (run_id, tool_name, arguments, status, result, duration_ms, created_at)
            VALUES ('legacy', 'calculate_change', '{}', 'success',
                    '{"change_percent":"-10.0000"}', 1, now())
        """)
        )
    try:
        schema_upgrade.upgrade_database(engine)
        schema_upgrade.upgrade_database(engine)
        columns = inspect(engine).get_columns("tool_audit_records")
        source = next((column for column in columns if column["name"] == "source"), None)
        assert source is not None, "旧审计表必须升级来源列"
        assert source["nullable"]
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT result, source FROM tool_audit_records WHERE run_id='legacy'")
            ).one()
            assert row.result == {"change_percent": "-10.0000"}
            assert row.source is None
    finally:
        # Keep this isolated test database usable even after an expected RED failure.
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE tool_audit_records ADD COLUMN IF NOT EXISTS source JSON NULL")
            )
