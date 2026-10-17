"""Paper trading tables; amounts are yuan Decimals, quantities are shares."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_paper_account_owner_name"),
        CheckConstraint("cash >= 0 AND frozen_cash >= 0 AND frozen_cash <= cash"),
        CheckConstraint("status IN ('active', 'closed')"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    # cash includes frozen_cash; available cash is cash - frozen_cash.
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    frozen_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    min_commission: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (
        UniqueConstraint("account_id", "stock_id", name="uq_paper_position_stock"),
        CheckConstraint("quantity > 0 AND frozen_quantity >= 0 AND today_bought >= 0"),
        CheckConstraint("frozen_quantity + today_bought <= quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    quantity: Mapped[int] = mapped_column()
    # Shares reserved by pending sell orders.
    frozen_quantity: Mapped[int] = mapped_column(default=0)
    # T+1: shares bought on last_buy_date are not sellable until the next trading day.
    today_bought: Mapped[int] = mapped_column(default=0)
    last_buy_date: Mapped[date | None] = mapped_column(Date)
    # Average-cost basis including buy fees.
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    last_price_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (
        CheckConstraint("side IN ('buy', 'sell')"),
        CheckConstraint("order_type IN ('limit', 'market')"),
        CheckConstraint("status IN ('pending', 'filled', 'cancelled', 'expired')"),
        CheckConstraint("quantity > 0"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String(36), unique=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    side: Mapped[str] = mapped_column(String(4))
    order_type: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column()
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    frozen_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(16), index=True)
    # A-share orders are day orders; unfilled ones expire after this Shanghai trade date.
    trade_date: Mapped[date] = mapped_column(Date)
    risk_event_id: Mapped[int | None] = mapped_column(ForeignKey("risk_events.id"))
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("paper_orders.id"), unique=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int] = mapped_column()
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    commission: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stamp_duty: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    transfer_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Sell trades only: net proceeds minus the average cost released.
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    quote_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trade_date: Mapped[date] = mapped_column(Date)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperSnapshot(Base):
    __tablename__ = "paper_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", name="uq_paper_snapshot_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_assets: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    # False when some holding had no same-day real quote and used its last known price.
    complete: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
