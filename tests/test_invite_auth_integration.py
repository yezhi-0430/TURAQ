"""Invite registration, email verification and account privacy against the real service API."""

from datetime import timedelta
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.auth.models import EmailToken, Invite, User
from app.auth.service import (
    check_password,
    create_invite,
    digest,
    issue_token,
    password_hash,
    register,
    utcnow,
    verify_email,
)
from app.config import Settings
from app.database import Base
from app.watchlists.repository import (
    WatchlistNotFoundError,
    add_stock_to_watchlist,
    create_watchlist,
    get_watchlists,
)


@pytest.fixture
def db():
    """Own schema in the test DB, so sequences don't collide with the seeded shared user."""
    settings = Settings(database_name="a_share_risk_agent_test")
    admin = create_engine(settings.database_url)
    schema = "invite_test_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    Base.metadata.create_all(engine)
    try:
        with sessionmaker(bind=engine)() as session:
            yield session
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def activate(db, email, code):
    user = register(db, email, "abcdef", code)
    verify_email(db, issue_token(db, user.id, "verify"))
    return user


def test_invite_stores_only_digest(db):
    invite_id, raw = create_invite(db, max_uses=2, days=1)
    row = db.get(Invite, invite_id)
    assert row.digest == digest(raw) and raw not in row.digest
    assert (row.uses, row.max_uses) == (0, 2)


def test_seat_is_claimed_at_verification_not_registration(db):
    invite_id, code = create_invite(db, max_uses=1)
    user = register(db, "a@example.com", "abcdef", code)
    db.commit()
    assert db.get(Invite, invite_id).uses == 0
    verify_email(db, issue_token(db, user.id, "verify"))
    db.refresh(user)
    assert user.verified and db.get(Invite, invite_id).uses == 1


def test_exhausted_invite_fails_at_verification(db):
    _, code = create_invite(db, max_uses=1)
    activate(db, "a@example.com", code)
    second = register(db, "b@example.com", "abcdef", code)
    assert second is None  # invite already full: same silent outcome as any rejection


def test_replacement_invite_at_verification(db):
    _, code = create_invite(db, max_uses=1)
    first = register(db, "a@example.com", "abcdef", code)
    second = register(db, "b@example.com", "abcdef", code)
    activate_token = issue_token(db, first.id, "verify")
    verify_email(db, activate_token)
    token = issue_token(db, second.id, "verify")
    with pytest.raises(ValueError, match="邀请码失效"):
        verify_email(db, token)
    db.rollback()
    replacement_id, replacement = create_invite(db)
    verify_email(db, issue_token(db, second.id, "verify"), replacement)
    db.refresh(second)
    assert second.verified and second.invite_id == replacement_id


def test_rejections_do_not_reveal_registered_emails(db):
    _, code = create_invite(db)
    activate(db, "taken@example.com", code)
    # Taken email and bad invite give the same result as each other, so neither leaks.
    assert register(db, "taken@example.com", "abcdef", code) is None
    assert register(db, "free@example.com", "abcdef", "not-a-real-invite") is None


def test_pending_registration_can_be_retried_after_expiry(db):
    _, code = create_invite(db)
    user = register(db, "a@example.com", "abcdef", code)
    assert register(db, "a@example.com", "abcdef", code) is None
    user.pending_expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    again = register(db, "a@example.com", "ghijkl", code)
    assert again.id == user.id and check_password(again.password_hash, "ghijkl")


def test_registration_password_bounds(db):
    _, code = create_invite(db)
    for bad in ("12345", "a" * 16):
        with pytest.raises(ValueError, match="6–15"):
            register(db, "a@example.com", bad, code)


def test_verification_token_single_use_and_expiry(db):
    _, code = create_invite(db)
    user = register(db, "a@example.com", "abcdef", code)
    token = issue_token(db, user.id, "verify")
    db.get(EmailToken, digest(token)).expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    with pytest.raises(ValueError, match="验证链接无效或已过期"):
        verify_email(db, token)
    fresh = issue_token(db, user.id, "verify")
    verify_email(db, fresh)
    with pytest.raises(ValueError, match="验证链接无效或已过期"):
        verify_email(db, fresh)
    with pytest.raises(ValueError, match="验证链接无效或已过期"):
        verify_email(db, "invalid-token")


def test_password_hashing_and_unknown_account_timing():
    first, second = password_hash("mypassword"), password_hash("mypassword")
    assert first != second
    assert check_password(first, "mypassword") and check_password(second, "mypassword")
    assert not check_password(first, "wrong-password")
    assert not check_password(None, "mypassword")

    def cost(stored):
        started = perf_counter()
        check_password(stored, "mypassword")
        return perf_counter() - started

    # A missing account must still run Argon2; an early return is orders of magnitude faster.
    assert cost(None) > cost(first) / 10


def test_watchlists_are_isolated_per_user(db):
    _, code = create_invite(db)
    a = activate(db, "usera@example.com", code)
    b = activate(db, "userb@example.com", code)
    list_a = create_watchlist(db, "A 组", actor_id=a.id)
    create_watchlist(db, "B 组", actor_id=b.id)
    assert [w.id for w in get_watchlists(db, actor_id=a.id)] == [list_a.id]
    with pytest.raises(WatchlistNotFoundError):
        add_stock_to_watchlist(db, list_a.id, "600000.SH", "浦发银行", actor_id=b.id)
    assert db.scalar(select(User.verified).where(User.id == b.id))
