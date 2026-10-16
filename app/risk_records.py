"""Private risk records. Analysis versions are immutable; review status is independent."""

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RiskAnalysis(Base):
    __tablename__ = "risk_analyses"
    __table_args__ = (
        UniqueConstraint("owner_id", "request_id", name="uq_risk_analysis_request"),
        CheckConstraint("generation_status IN ('pending', 'completed', 'failed')"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), index=True)
    risk_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    published_date: Mapped[date | None] = mapped_column(Date)
    input_text: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    model_mode: Mapped[str] = mapped_column(String(20))
    generation_status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(String(200))
    error_status: Mapped[int | None] = mapped_column()
    version: Mapped[int] = mapped_column(default=1)
    previous_version_id: Mapped[int | None] = mapped_column(ForeignKey("risk_analyses.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskEvent(Base):
    __tablename__ = "risk_events"
    __table_args__ = (
        CheckConstraint("status IN ('unread', 'viewed', 'following')"),
        CheckConstraint("risk_level IN ('high', 'medium', 'low', 'unknown')"),
        # Future scanners must derive a stable source/rule key, not a model prose hash.
        UniqueConstraint("owner_id", "dedup_key", name="uq_risk_event_dedup"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("risk_analyses.id"), unique=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), index=True)
    risk_type: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="unread")
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    published_date: Mapped[date | None] = mapped_column(Date)
    trade_date: Mapped[date | None] = mapped_column(Date)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedup_key: Mapped[str | None] = mapped_column(String(200))
    # Only structure is reserved: no RAG or sentiment computation in this release.
    context: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {"observations": [], "knowledge_references": [], "historical_cases": []},
    )
