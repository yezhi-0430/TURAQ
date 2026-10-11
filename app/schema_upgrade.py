"""Explicit, transactional upgrade for existing PostgreSQL databases."""

from sqlalchemy import BigInteger, Engine, func, inspect, select, text, update

from app.database import Base, Stock, engine


def upgrade_database(target_engine: Engine) -> None:
    if target_engine.dialect.name != "postgresql":
        raise ValueError("数据库升级仅支持 PostgreSQL")
    with target_engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.execute(
            text("ALTER TABLE tool_audit_records ADD COLUMN IF NOT EXISTS source JSON NULL")
        )
        # Keep the collision check and normalization atomic with concurrent writers.
        connection.execute(text("LOCK TABLE stocks IN SHARE ROW EXCLUSIVE MODE"))
        normalized = func.upper(func.trim(Stock.symbol))
        collisions = connection.scalars(
            select(normalized).group_by(normalized).having(func.count() > 1).order_by(normalized)
        ).all()
        if collisions:
            raise ValueError("股票代码归一化冲突：" + ", ".join(collisions))
        connection.execute(
            update(Stock).where(Stock.symbol != normalized).values(symbol=normalized)
        )
        volume_column = next(
            column
            for column in inspect(connection).get_columns("daily_prices")
            if column["name"] == "volume"
        )
        if not isinstance(volume_column["type"], BigInteger):
            connection.execute(text("ALTER TABLE daily_prices ALTER COLUMN volume TYPE BIGINT"))


def main() -> None:
    upgrade_database(engine)
    print("数据库升级完成：股票代码已规范化，成交量列为 BIGINT，审计来源列已就绪。")


if __name__ == "__main__":
    main()
