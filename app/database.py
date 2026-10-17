from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)

from app.config import Settings

settings = Settings()
engine = create_engine(
    settings.database_url,
    pool_timeout=10,  # 增至10秒，允许合理的锁等待和网络抖动恢复
    connect_args={"connect_timeout": 5},  # TCP连接给5秒
    pool_size=10,  # 显式设置连接池大小
    max_overflow=5,  # 允许临时超额连接
    echo=False,  # 生产环境禁用SQL日志
)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column()


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "trade_date",
            name="uq_daily_prices_stock_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    trade_date: Mapped[date] = mapped_column(Date)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    volume: Mapped[int] = mapped_column(BigInteger)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint(
            "watchlist_id",
            "stock_id",
            name="uq_watchlist_items_watchlist_stock",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))


class ToolAuditRecord(Base):
    __tablename__ = "tool_audit_records"
    __table_args__ = (
        CheckConstraint("status IN ('success', 'error')", name="ck_tool_audit_status"),
        CheckConstraint("duration_ms >= 0", name="ck_tool_audit_duration"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    tool_call_id: Mapped[str | None] = mapped_column(Text)
    tool_name: Mapped[str] = mapped_column(Text)
    arguments: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(7))
    result: Mapped[dict | list | None] = mapped_column(JSON(none_as_null=True))
    error: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    source: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    duration_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


def create_tables() -> None:
    Base.metadata.create_all(engine)


# Register identity tables for explicit create/upgrade commands.
from app import risk_records  # noqa: E402, F401
from app.auth import models as auth_models  # noqa: E402, F401
from app.paper_trading import models as paper_trading_models  # noqa: E402, F401
from app.user_settings import models as user_settings_models  # noqa: E402, F401
