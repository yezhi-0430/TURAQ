"""Atomic shared throttle API. Keys contain digests, never email addresses or tokens."""

import math
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.auth.models import ThrottleBucket
from app.auth.service import utcnow


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = max(1, retry_after)


def reserve(session_factory, key: str, limit: int, seconds: int) -> None:
    """Reserve before work; conflicting callers serialize in database, not process memory."""
    now = utcnow()
    with session_factory() as db, db.begin():
        try:
            with db.begin_nested():
                db.add(
                    ThrottleBucket(key=key, count=0, expires_at=now + timedelta(seconds=seconds))
                )
                db.flush()
        except IntegrityError:
            pass
        db.execute(
            update(ThrottleBucket)
            .where(ThrottleBucket.key == key, ThrottleBucket.expires_at <= now)
            .values(count=0, expires_at=now + timedelta(seconds=seconds))
        )
        result = db.execute(
            update(ThrottleBucket)
            .where(ThrottleBucket.key == key, ThrottleBucket.count < limit)
            .values(count=ThrottleBucket.count + 1)
        )
        if result.rowcount != 1:
            row = db.get(ThrottleBucket, key)
            expiry = (
                row.expires_at.replace(tzinfo=now.tzinfo)
                if row.expires_at.tzinfo is None
                else row.expires_at
            )
            # Handle negative duration (clock skew) by using minimum 1 second
            seconds_remaining = max(1, math.ceil((expiry - now).total_seconds()))
            raise RateLimited(seconds_remaining)
