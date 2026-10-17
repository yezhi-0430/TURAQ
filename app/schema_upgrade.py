"""Explicit, transactional upgrade for existing PostgreSQL databases."""

import argparse

from sqlalchemy import BigInteger, Engine, func, inspect, select, text, update

from app.auth.models import User
from app.database import Base, Stock, engine


def upgrade_database(target_engine: Engine, *, owner_id: int | None = None) -> None:
    if target_engine.dialect.name != "postgresql":
        raise ValueError("数据库升级仅支持 PostgreSQL")
    with target_engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.execute(text("LOCK TABLE watchlists IN ACCESS EXCLUSIVE MODE"))
        connection.execute(
            text(
                "ALTER TABLE watchlists ADD COLUMN IF NOT EXISTS "
                "owner_id INTEGER REFERENCES users(id)"
            )
        )
        unowned = connection.scalar(text("SELECT count(*) FROM watchlists WHERE owner_id IS NULL"))
        if unowned:
            owner = connection.execute(
                select(User.id).where(
                    User.id == owner_id,
                    User.verified.is_(True),
                    User.is_admin.is_(True),
                    User.disabled.is_(False),
                )
            ).first()
            if owner is None:
                raise ValueError("旧分组必须显式指定已验证管理员 owner_id 归属")
            connection.execute(
                text("UPDATE watchlists SET owner_id = :owner WHERE owner_id IS NULL"),
                {"owner": owner_id},
            )
        connection.execute(text("ALTER TABLE watchlists ALTER COLUMN owner_id SET NOT NULL"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_watchlists_owner_id ON watchlists(owner_id)")
        )
        connection.execute(
            text(
                "ALTER TABLE tool_audit_records ADD COLUMN IF NOT EXISTS "
                "actor_id INTEGER REFERENCES users(id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_tool_audit_records_actor_id "
                "ON tool_audit_records(actor_id)"
            )
        )
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
    parser = argparse.ArgumentParser(description="显式升级；先备份，旧分组需要已核验管理员")
    parser.add_argument("--owner-id", type=int)
    args = parser.parse_args()
    upgrade_database(engine, owner_id=args.owner_id)
    print("数据库升级完成：股票代码已规范化，成交量列为 BIGINT，审计来源列已就绪。")


if __name__ == "__main__":
    main()
