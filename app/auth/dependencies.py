from dataclasses import dataclass
from datetime import timedelta
from secrets import compare_digest
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.auth.models import LoginSession, User
from app.auth.service import aware, digest, utcnow
from app.config import Settings
from app.database import SessionLocal, Watchlist


@dataclass(frozen=True)
class Actor:
    id: int
    email: str
    is_admin: bool


def get_session_factory():
    return SessionLocal


def get_settings():
    return Settings()


def load_session(db, raw):
    if not raw:
        return None
    row = db.get(LoginSession, digest(raw))
    now = utcnow()
    if (
        row is None
        or row.revoked
        or aware(row.expires_at) <= now
        or aware(row.last_seen_at) <= now - timedelta(hours=24)
    ):
        return None
    return row


def require_csrf(
    request: Request, settings=Depends(get_settings), factory=Depends(get_session_factory)
):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    expected = urlsplit(settings.site_base_url)
    expected_origin = f"{expected.scheme}://{expected.netloc}"
    # Origin is mandatory even for non-browser clients; same-origin tests send it explicitly.
    if origin != expected_origin or request.headers.get("sec-fetch-site") not in (
        None,
        "same-origin",
    ):
        raise HTTPException(403, "请求来源无效")
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
        raise HTTPException(415, "仅接受 JSON 请求")
    with factory() as db:
        row = load_session(db, request.cookies.get(settings.auth_cookie_name))
        supplied = request.headers.get("x-csrf-token", "")
        if row is None or not supplied.isascii() or not compare_digest(row.csrf_token, supplied):
            raise HTTPException(403, "CSRF 校验失败")


def require_actor(
    request: Request, settings=Depends(get_settings), factory=Depends(get_session_factory)
) -> Actor:
    try:
        with factory() as db:
            row = load_session(db, request.cookies.get(settings.auth_cookie_name))
            user = db.get(User, row.user_id) if row and row.user_id else None
            if user is None or not user.verified or user.disabled:
                raise HTTPException(401, "请先登录")
            if (
                db.scalar(select(Watchlist.id).where(Watchlist.owner_id.is_(None)).limit(1))
                is not None
            ):
                raise HTTPException(503, "私有数据迁移尚未完成")
            require_csrf(request, settings, factory)
            actor = Actor(user.id, user.email, user.is_admin)
            row.last_seen_at = utcnow()
            db.commit()
    except SQLAlchemyError as exc:
        raise HTTPException(503, "身份服务暂不可用") from exc
    request.state.actor = actor
    return actor


def require_admin(actor: Actor = Depends(require_actor)) -> Actor:
    if not actor.is_admin:
        raise HTTPException(403, "需要管理员权限")
    return actor
