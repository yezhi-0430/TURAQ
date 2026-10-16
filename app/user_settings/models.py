from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PersonalSettings(Base):
    __tablename__ = "personal_settings"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    preferences: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)


class GlobalSettings(Base):
    __tablename__ = "global_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)


class SettingsAudit(Base):
    __tablename__ = "settings_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_email: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changes: Mapped[dict] = mapped_column(JSON)
