"""Invitation metadata; plaintext is available only in the creation response."""

from fastapi import HTTPException
from sqlalchemy import func, select

from app.auth.models import Invite
from app.auth.service import aware, create_invite, utcnow


def snapshot(invite, now):
    status = (
        "revoked"
        if invite.revoked
        else "expired"
        if aware(invite.expires_at) <= now
        else "exhausted"
        if invite.uses >= invite.max_uses
        else "active"
    )
    return {
        "id": invite.id,
        "code": None,
        "max_uses": invite.max_uses,
        "used_count": invite.uses,
        "expires_at": aware(invite.expires_at),
        "revoked": invite.revoked,
        "created_at": None,
        "status": status,
    }


def list_invites(db, *, limit, offset):
    now = utcnow()
    total = db.scalar(select(func.count()).select_from(Invite))
    rows = db.scalars(select(Invite).order_by(Invite.id.desc()).offset(offset).limit(limit))
    return {
        "invites": [snapshot(row, now) for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def generate_invite(db, *, max_uses, days):
    invite_id, raw = create_invite(db, max_uses=max_uses, days=days)
    result = snapshot(db.get(Invite, invite_id), utcnow())
    result["code"] = raw
    return result


def revoke_invite(db, invite_id):
    row = db.scalar(select(Invite).where(Invite.id == invite_id).with_for_update())
    if row is None:
        raise HTTPException(404, "邀请码不存在")
    row.revoked = True
    db.commit()
    return snapshot(row, utcnow())
