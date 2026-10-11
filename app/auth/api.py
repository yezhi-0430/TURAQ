"""Same-origin JSON account routes. Secrets are never part of responses."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import (
    Actor,
    get_session_factory,
    get_settings,
    load_session,
    require_csrf,
)
from app.auth.mail import MailUnavailable, get_mailer
from app.auth.models import ThrottleBucket, User
from app.auth.schemas import (
    EmailRequest,
    LoginRequest,
    RegisterRequest,
    ResetRequest,
    VerifyRequest,
)
from app.auth.service import (
    aware,
    check_password,
    digest,
    issue_token,
    new_session,
    register,
    reset_password,
    utcnow,
    verify_email,
)
from app.auth.throttle import RateLimited, reserve


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(require_csrf), Depends(no_store)]
)
ACCEPTED = {"detail": "请求已受理；符合条件时将发送邮件。"}


def limit(factory, key, count, seconds):
    try:
        reserve(factory, key, count, seconds)
    except RateLimited as exc:
        raise HTTPException(
            429, "请求过于频繁，请稍后重试", headers={"Retry-After": str(exc.retry_after)}
        ) from exc


def mail_admission(request, payload, factory, mailer):
    if not mailer.configured:
        raise HTTPException(503, "邮件服务暂不可用")
    ip = request.client.host if request.client else "unknown"
    limit(factory, "mail-ip:" + digest(ip), 10, 3600)
    limit(factory, "mail-day:" + digest(payload.email), 5, 86400)
    limit(factory, "mail-gap:" + digest(payload.email), 1, 60)
    try:
        mailer.check_available()
    except MailUnavailable as exc:
        raise HTTPException(503, "邮件服务暂不可用") from exc


def deliver(mailer, email, purpose, token):
    try:
        mailer.send(email, purpose, token)
    except MailUnavailable:
        # Restricted operational signal; never emit address, token or supplier exception.
        logger.warning("Authentication mail transport rejected a delivery")


def session_json(db, row, mailer):
    user = db.get(User, row.user_id) if row.user_id else None
    actor = (
        Actor(user.id, user.email, user.is_admin)
        if user and user.verified and not user.disabled
        else None
    )
    return {
        "user": asdict(actor) if actor else None,
        "csrf_token": row.csrf_token,
        "mail_configured": mailer.configured,
    }


def set_cookie(response, raw, settings):
    response.set_cookie(
        settings.auth_cookie_name,
        raw,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
        max_age=7 * 86400,
    )


@router.get("/session")
def session(
    request: Request,
    response: Response,
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
    mailer=Depends(get_mailer),
):
    with factory() as db:
        row = load_session(db, request.cookies.get(settings.auth_cookie_name))
        user = db.get(User, row.user_id) if row and row.user_id else None
        if row and row.user_id and (not user or not user.verified or user.disabled):
            row.revoked = True
            db.commit()
            row = None
        if row is None:
            raw, row = new_session(db)
            set_cookie(response, raw, settings)
        return session_json(db, row, mailer)


@router.post("/register", status_code=202)
def signup(
    payload: RegisterRequest,
    request: Request,
    factory=Depends(get_session_factory),
    mailer=Depends(get_mailer),
):
    mail_admission(request, payload, factory, mailer)
    with factory() as db:
        try:
            user = register(db, payload.email, payload.password, payload.invite_code)
            if user:
                token = issue_token(db, user.id, "verify")
                deliver(mailer, payload.email, "verify", token)
        except IntegrityError:
            db.rollback()
    return ACCEPTED


@router.post("/resend-verification", status_code=202)
def resend(
    payload: EmailRequest,
    request: Request,
    factory=Depends(get_session_factory),
    mailer=Depends(get_mailer),
):
    mail_admission(request, payload, factory, mailer)
    with factory() as db:
        user = db.scalar(select(User).where(User.email == payload.email).with_for_update())
        if (
            user
            and not user.verified
            and not user.disabled
            and aware(user.pending_expires_at) > utcnow()
        ):
            token = issue_token(db, user.id, "verify")
            deliver(mailer, payload.email, "verify", token)
    return ACCEPTED


@router.post("/forgot-password", status_code=202)
def forgot(
    payload: EmailRequest,
    request: Request,
    factory=Depends(get_session_factory),
    mailer=Depends(get_mailer),
):
    mail_admission(request, payload, factory, mailer)
    with factory() as db:
        user = db.scalar(select(User).where(User.email == payload.email).with_for_update())
        if user and user.verified and not user.disabled:
            token = issue_token(db, user.id, "reset")
            deliver(mailer, payload.email, "reset", token)
    return ACCEPTED


@router.post("/verify-email")
def verify(payload: VerifyRequest, factory=Depends(get_session_factory)):
    with factory() as db:
        try:
            verify_email(db, payload.token, payload.invite_code)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
    return {"detail": "邮箱已验证，请登录。"}


@router.post("/reset-password")
def reset(payload: ResetRequest, factory=Depends(get_session_factory)):
    with factory() as db:
        try:
            reset_password(db, payload.token, payload.password)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
    return {"detail": "密码已重置，请重新登录。"}


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
    mailer=Depends(get_mailer),
):
    ip = request.client.host if request.client else "unknown"
    limit(factory, "login-ip:" + digest(ip), 20, 900)
    limit(factory, "login-email:" + digest(payload.email), 5, 900)
    with factory() as db:
        user = db.scalar(select(User).where(User.email == payload.email).with_for_update())
        valid = check_password(user.password_hash if user else None, payload.password)
        if not valid or not user or not user.verified or user.disabled:
            raise HTTPException(401, "邮箱或密码错误，或账号尚不可用")
        # Successful authentication releases its provisional failure-budget reservations.
        db.execute(
            update(ThrottleBucket)
            .where(
                ThrottleBucket.key.in_(
                    ["login-ip:" + digest(ip), "login-email:" + digest(payload.email)]
                ),
                ThrottleBucket.count > 0,
            )
            .values(count=ThrottleBucket.count - 1)
        )
        previous = load_session(db, request.cookies.get(settings.auth_cookie_name))
        if previous:
            previous.revoked = True
        raw, row = new_session(db, user.id)
        set_cookie(response, raw, settings)
        return session_json(db, row, mailer)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
    mailer=Depends(get_mailer),
):
    with factory() as db:
        previous = load_session(db, request.cookies.get(settings.auth_cookie_name))
        if previous:
            previous.revoked = True
        raw, row = new_session(db)
        set_cookie(response, raw, settings)
        return session_json(db, row, mailer)
