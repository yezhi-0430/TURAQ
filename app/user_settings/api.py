"""Versioned settings; all writes use the existing same-origin CSRF guard."""

from dataclasses import asdict
from datetime import timedelta

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.api import limit, no_store
from app.auth.dependencies import (
    Actor,
    get_session_factory,
    get_settings,
    require_actor,
    require_admin,
)
from app.auth.models import EmailToken, LoginSession, User
from app.auth.service import check_password, digest, password_hash, utcnow
from app.user_settings.models import GlobalSettings, PersonalSettings, SettingsAudit
from app.user_settings.runtime import cipher
from app.user_settings.schemas import (
    ADMIN_FIELDS,
    AdminUpdate,
    PasswordUpdate,
    PersonalUpdate,
    Preferences,
    SecretUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["settings"], dependencies=[Depends(no_store)])


def conflict():
    return HTTPException(409, "设置已被其他会话修改，请重新加载后再保存")


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict() from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "设置保存失败，请稍后重试") from None


def personal_json(row, actor):
    defaults = Preferences().model_dump()
    return {
        "preferences": {**defaults, **(row.preferences if row else {})},
        "defaults": defaults,
        "version": row.version if row else 0,
        "account": asdict(actor),
    }


@router.get("/settings")
def personal(actor: Actor = Depends(require_actor), factory=Depends(get_session_factory)):
    with factory() as db:
        return personal_json(db.get(PersonalSettings, actor.id), actor)


@router.put("/settings")
def save_personal(
    payload: PersonalUpdate,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
):
    values = payload.preferences.model_dump()
    with factory() as db:
        if payload.version == 0:
            db.add(PersonalSettings(user_id=actor.id, preferences=values, version=1))
        else:
            result = db.execute(
                update(PersonalSettings)
                .where(
                    PersonalSettings.user_id == actor.id,
                    PersonalSettings.version == payload.version,
                )
                .values(preferences=values, version=payload.version + 1)
            )
            if result.rowcount != 1:
                raise conflict()
        commit(db)
        return personal_json(db.get(PersonalSettings, actor.id), actor)


def active_sessions(actor):
    now = utcnow()
    return (
        LoginSession.user_id == actor.id,
        LoginSession.revoked.is_(False),
        LoginSession.expires_at > now,
        LoginSession.last_seen_at > now - timedelta(hours=24),
    )


@router.get("/settings/sessions")
def sessions(
    request: Request,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
):
    current = digest(request.cookies.get(settings.auth_cookie_name, ""))
    with factory() as db:
        rows = db.scalars(
            select(LoginSession)
            .where(*active_sessions(actor))
            .order_by(LoginSession.last_seen_at.desc())
        ).all()
        # Domain-separated one-way handles cannot authenticate and reveal no stored cookie digest.
        return {
            "sessions": [
                {
                    "id": digest("settings-session:" + row.digest),
                    "current": row.digest == current,
                    "last_seen_at": row.last_seen_at,
                    "expires_at": row.expires_at,
                }
                for row in rows
            ]
        }


@router.post("/settings/sessions/revoke-others")
def revoke_others(
    request: Request,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
):
    current = digest(request.cookies.get(settings.auth_cookie_name, ""))
    with factory() as db:
        result = db.execute(
            update(LoginSession)
            .where(*active_sessions(actor), LoginSession.digest != current)
            .values(revoked=True)
        )
        count = result.rowcount
        commit(db)
        return {"detail": "已退出其他会话", "count": count}


@router.post("/settings/password")
def change_password(
    payload: PasswordUpdate,
    response: Response,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
):
    limit(factory, f"settings-password:{actor.id}", 5, 900)
    with factory() as db:
        user = db.scalar(select(User).where(User.id == actor.id).with_for_update())
        if not check_password(user.password_hash, payload.current_password):
            raise HTTPException(400, "当前密码不正确")
        user.password_hash = password_hash(payload.new_password)
        db.execute(
            update(LoginSession).where(LoginSession.user_id == actor.id).values(revoked=True)
        )
        db.execute(
            update(EmailToken)
            .where(EmailToken.user_id == actor.id, EmailToken.purpose == "reset")
            .values(consumed=True)
        )
        commit(db)
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return {"detail": "密码已修改，所有会话已退出，请重新登录。"}


def defaults(settings):
    return {name: getattr(settings, name) for name in ADMIN_FIELDS}


def admin_json(db, settings):
    row = db.get(GlobalSettings, 1)
    db.execute(text("SELECT 1"))
    values = {**defaults(settings), **(row.values if row else {})}
    configured = bool((row and row.encrypted_api_key) or settings.dashscope_api_key)
    encryption = cipher(settings)
    editable = encryption is not None
    key_error = False
    if row and row.encrypted_api_key:
        if encryption is None:
            key_error = True
        else:
            try:
                encryption.decrypt(row.encrypted_api_key.encode())
            except (InvalidToken, ValueError):
                key_error = True
    return {
        "values": values,
        "defaults": defaults(settings),
        "version": row.version if row else 0,
        "secrets": {"dashscope_api_key": {"configured": configured, "editable": editable}},
        "diagnostics": [
            {"name": "database", "status": "ok", "detail": "数据库 SELECT 1 成功"},
            {
                "name": "model",
                "status": "error" if key_error else "configured" if configured else "unconfigured",
                "detail": "已保存的模型密钥无法解密，请恢复部署加密密钥或重新保存模型密钥"
                if key_error else "密钥配置状态；未发起模型网络请求",
            },
            {
                "name": "encryption",
                "status": "ok" if editable else "unconfigured",
                "detail": "部署加密密钥有效"
                if editable
                else "请部署有效的 SETTINGS_ENCRYPTION_KEY（Fernet），然后重启服务以启用密钥编辑",
            },
            {
                "name": "mail",
                "status": "configured" if settings.smtp_host else "unconfigured",
                "detail": "部署配置状态；未连接邮件服务器",
            },
        ],
    }


@router.get("/admin/settings")
def admin_settings(
    actor: Actor = Depends(require_admin),
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
):
    with factory() as db:
        return admin_json(db, settings)


def save_global(db, version, values):
    if version == 0:
        db.add(GlobalSettings(id=1, version=1, **values))
    else:
        result = db.execute(
            update(GlobalSettings)
            .where(GlobalSettings.id == 1, GlobalSettings.version == version)
            .values(**values, version=version + 1)
        )
        if result.rowcount != 1:
            raise conflict()


def audit(db, actor, changes):
    db.add(
        SettingsAudit(
            actor_id=actor.id, actor_email=actor.email, created_at=utcnow(), changes=changes
        )
    )


@router.put("/admin/settings")
def save_admin(
    payload: AdminUpdate,
    actor: Actor = Depends(require_admin),
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
):
    with factory() as db:
        before = admin_json(db, settings)["values"]
        values = payload.values.model_dump()
        save_global(db, payload.version, {"values": values})
        audit(
            db,
            actor,
            {
                key: {"before": before[key], "after": value}
                for key, value in values.items()
                if before[key] != value
            },
        )
        commit(db)
        return admin_json(db, settings)


@router.post("/admin/settings/secrets")
def save_secret(
    payload: SecretUpdate,
    actor: Actor = Depends(require_admin),
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
):
    encryption = cipher(settings)
    if encryption is None:
        raise HTTPException(503, "请部署有效的 SETTINGS_ENCRYPTION_KEY（Fernet）并重启服务")
    encrypted = (
        encryption.encrypt(payload.dashscope_api_key.encode()).decode()
        if payload.dashscope_api_key
        else None
    )
    with factory() as db:
        save_global(db, payload.version, {"encrypted_api_key": encrypted})
        audit(db, actor, {"dashscope_api_key": {"action": "updated" if encrypted else "cleared"}})
        commit(db)
        return admin_json(db, settings)


@router.get("/admin/settings/audit")
def history(
    actor: Actor = Depends(require_admin),
    factory=Depends(get_session_factory),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    with factory() as db:
        rows = db.scalars(
            select(SettingsAudit).order_by(SettingsAudit.id.desc()).limit(limit).offset(offset)
        ).all()
        return {
            "items": [
                {
                    "actor_email": row.actor_email,
                    "created_at": row.created_at,
                    "changes": row.changes,
                }
                for row in rows
            ]
        }
