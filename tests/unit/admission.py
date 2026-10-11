"""Explicit admission fixture for existing offline HTTP-boundary unit tests only."""

from datetime import timedelta

from app.auth.service import utcnow
from app.config import Settings
from app.model_limits import Admission


def offline_admission():
    settings = Settings(
        database_host="127.0.0.1", database_port=5432,
        database_name="unit_test_only", database_user="test", database_password="test",
        model_provider="fake",
    )
    return Admission(None, 1, settings, "unit-only", utcnow() + timedelta(seconds=65))
