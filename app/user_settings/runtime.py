"""Merge deployment settings and persisted overrides without depending on authentication."""

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import get_session_factory, get_settings
from app.user_settings.models import GlobalSettings
from app.user_settings.schemas import ADMIN_FIELDS, AdminValues


def cipher(settings):
    key = settings.settings_encryption_key
    if key:
        try:
            return Fernet(key.get_secret_value().encode())
        except (ValueError, TypeError):
            pass
    return None


def resolve_settings(base, factory, *, decrypt_secret=True):
    try:
        with factory() as db:
            row = db.get(GlobalSettings, 1)
            if row is None:
                return base
            values = AdminValues.model_validate(
                {**{name: getattr(base, name) for name in ADMIN_FIELDS}, **row.values}
            ).model_dump()
            if decrypt_secret and row.encrypted_api_key:
                encryption = cipher(base)
                if encryption is None:
                    raise HTTPException(503, "模型密钥无法解密，请检查 SETTINGS_ENCRYPTION_KEY")
                try:
                    values["dashscope_api_key"] = SecretStr(
                        encryption.decrypt(row.encrypted_api_key.encode()).decode()
                    )
                except (InvalidToken, ValueError):
                    raise HTTPException(503, "模型密钥无法解密，请检查部署加密配置") from None
            return base.model_copy(update=values)
    except SQLAlchemyError:
        raise HTTPException(503, "设置服务暂不可用，请稍后重试") from None


def get_runtime_settings(base=Depends(get_settings), factory=Depends(get_session_factory)):
    return resolve_settings(base, factory)


def get_runtime_policy(base=Depends(get_settings), factory=Depends(get_session_factory)):
    """Non-model services need limits, never the model credential or decryption availability."""
    return resolve_settings(base, factory, decrypt_secret=False)
