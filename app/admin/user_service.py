"""User listing and status changes; credentials and roles are never writable here."""

from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.auth.models import LoginSession, User
from app.auth.service import aware


def snapshot(user, last_seen=None):
    return {
        "id": user.id,
        "email": user.email,
        "verified": user.verified,
        "disabled": user.disabled,
        "is_admin": user.is_admin,
        "created_at": None,
        "invite_id": user.invite_id,
        "last_seen": aware(last_seen) if last_seen is not None else None,
    }


def list_users(db, *, limit, offset, q="", disabled=None):
    conditions = []
    if q:
        conditions.append(User.email.contains(q, autoescape=True))
    if disabled is not None:
        conditions.append(User.disabled == disabled)
    total = db.scalar(select(func.count()).select_from(User).where(*conditions))
    last_seen = (
        select(LoginSession.user_id, func.max(LoginSession.last_seen_at).label("seen"))
        .group_by(LoginSession.user_id)
        .subquery()
    )
    rows = db.execute(
        select(User, last_seen.c.seen)
        .outerjoin(last_seen, User.id == last_seen.c.user_id)
        .where(*conditions)
        .order_by(User.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "users": [snapshot(user, seen) for user, seen in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def set_disabled(db, user_id, disabled):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(404, "账号不存在")
    if disabled and user.is_admin:
        raise HTTPException(409, "管理员账号不能在此禁用")
    user.disabled = disabled
    if disabled:
        db.execute(update(LoginSession).where(LoginSession.user_id == user_id).values(revoked=True))
    db.commit()
    return snapshot(user)
