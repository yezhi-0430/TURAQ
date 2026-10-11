"""Transactional invitation activation and opaque credential lifecycle."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import delete, select, update

from app.auth.models import EmailToken, Invite, LoginSession, User

hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_dummy_hash = hasher.hash(secrets.token_urlsafe(16))


def utcnow():
    return datetime.now(UTC)


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str) -> str:
    if not 6 <= len(password) <= 15:
        raise ValueError("密码须为 6–15 个字符")
    return hasher.hash(password)


def check_password(stored: str | None, password: str) -> bool:
    try:
        return hasher.verify(stored or _dummy_hash, password) and stored is not None
    except VerificationError:
        return False


def create_invite(db, *, max_uses=50, days=7):
    if max_uses < 1 or days <= 0:
        raise ValueError("名额和有效期必须为正数")
    raw = secrets.token_urlsafe(32)
    row = Invite(digest=digest(raw), max_uses=max_uses, expires_at=utcnow() + timedelta(days=days))
    db.add(row)
    db.commit()
    return row.id, raw


def issue_token(db, user_id: int, purpose: str):
    raw = secrets.token_urlsafe(32)
    db.execute(
        delete(EmailToken).where(EmailToken.user_id == user_id, EmailToken.purpose == purpose)
    )
    db.add(
        EmailToken(
            digest=digest(raw),
            user_id=user_id,
            purpose=purpose,
            expires_at=utcnow() + timedelta(minutes=30),
        )
    )
    db.commit()
    return raw


def register(db, email, password, invite_code):
    now = utcnow()
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if user and (user.verified or aware(user.pending_expires_at) > now):
        return None
    invitation = db.scalar(
        select(Invite).where(
            Invite.digest == digest(invite_code),
            Invite.revoked.is_(False),
            Invite.expires_at > now,
            Invite.uses < Invite.max_uses,
        )
    )
    if invitation is None:
        return None
    if user is None:
        user = User(
            email=email,
            password_hash=password_hash(password),
            pending_expires_at=now + timedelta(hours=24),
            invite_id=invitation.id,
        )
        db.add(user)
    else:
        user.password_hash = password_hash(password)
        user.invite_id = invitation.id
        user.pending_expires_at = now + timedelta(hours=24)
    db.flush()
    return user


def verify_email(db, raw, replacement=None):
    now = utcnow()
    token = db.scalar(
        select(EmailToken).where(
            EmailToken.digest == digest(raw),
            EmailToken.purpose == "verify",
            EmailToken.expires_at > now,
            EmailToken.consumed.is_(False),
        )
    )
    if token is None:
        raise ValueError("验证链接无效或已过期")
    # Serialize by user first, then atomically claim token and invitation in this transaction.
    user = db.scalar(select(User).where(User.id == token.user_id).with_for_update())
    if user.verified or user.disabled or aware(user.pending_expires_at) <= now:
        raise ValueError("验证链接无效或已过期")
    claimed = db.execute(
        update(EmailToken)
        .where(EmailToken.digest == token.digest, EmailToken.consumed.is_(False))
        .values(consumed=True)
    )
    if claimed.rowcount != 1:
        raise ValueError("验证链接无效或已过期")
    invite_id = user.invite_id
    if replacement:
        invite_id = db.scalar(select(Invite.id).where(Invite.digest == digest(replacement)))
    reserved = db.execute(
        update(Invite)
        .where(
            Invite.id == invite_id,
            Invite.revoked.is_(False),
            Invite.expires_at > now,
            Invite.uses < Invite.max_uses,
        )
        .values(uses=Invite.uses + 1)
    )
    if reserved.rowcount != 1:
        raise ValueError("邀请码失效或名额已满，请使用新的邀请码")
    user.verified = True
    user.invite_id = invite_id
    db.commit()


def new_session(db, user_id=None):
    raw = secrets.token_urlsafe(32)
    now = utcnow()
    row = LoginSession(
        digest=digest(raw),
        user_id=user_id,
        csrf_token=secrets.token_urlsafe(32),
        last_seen_at=now,
        expires_at=now + timedelta(days=7) if user_id else now + timedelta(hours=1),
    )
    db.add(row)
    db.commit()
    return raw, row


def reset_password(db, raw, password):
    now = utcnow()
    token = db.scalar(
        select(EmailToken).where(
            EmailToken.digest == digest(raw),
            EmailToken.purpose == "reset",
            EmailToken.expires_at > now,
            EmailToken.consumed.is_(False),
        )
    )
    if token is None:
        raise ValueError("重置链接无效或已过期")
    user = db.scalar(select(User).where(User.id == token.user_id).with_for_update())
    if user is None or not user.verified or user.disabled:
        raise ValueError("重置链接无效或已过期")
    claimed = db.execute(
        update(EmailToken)
        .where(EmailToken.digest == token.digest, EmailToken.consumed.is_(False))
        .values(consumed=True)
    )
    if claimed.rowcount != 1:
        raise ValueError("重置链接无效或已过期")
    user.password_hash = password_hash(password)
    db.execute(update(LoginSession).where(LoginSession.user_id == user.id).values(revoked=True))
    db.commit()
