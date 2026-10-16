from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Password = Annotated[str, Field(strict=True, min_length=6, max_length=15)]
Token = Annotated[str, Field(strict=True, min_length=20, max_length=200)]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailRequest(StrictRequest):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class RegisterRequest(EmailRequest):
    password: Password
    invite_code: Token | None = None


class LoginRequest(EmailRequest):
    password: str = Field(strict=True, max_length=1024)


class MagicLinkRequest(EmailRequest):
    """邮箱验证码登录请求"""
    pass


class MagicLinkVerifyRequest(StrictRequest):
    """用验证码登录"""
    token: Token


class VerifyRequest(StrictRequest):
    token: Token
    invite_code: Token | None = None


class ResetRequest(StrictRequest):
    token: Token
    password: Password
