from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from app.config import Settings


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Preferences(StrictModel):
    default_page: Literal["agent", "dashboard", "watchlist", "risk", "trading", "settings"] = (
        "agent"
    )
    density: Literal["comfortable", "compact"] = "comfortable"
    reduce_motion: bool = False
    market_auto_refresh: bool = True
    market_refresh_seconds: Literal[10, 30, 60] = 10
    chart_period: Literal["minute", "day", "week", "month"] = "minute"
    chart_adjustment: Literal["none", "qfq", "hfq"] = "none"
    watchlist_sort: Literal["default", "name", "symbol"] = "default"
    research_send_key: Literal["enter", "ctrl_enter"] = "enter"
    research_max_rounds: int = Field(15, ge=1, le=15)
    risk_level: Literal["all", "high", "medium", "low", "unknown"] = "all"
    risk_status: Literal["all", "unread", "viewed", "following"] = "all"
    risk_lookback_days: Literal[30, 90, 180] = 90
    paper_auto_refresh: bool = True
    paper_refresh_seconds: Literal[15, 30, 60] = 15
    paper_initial_capital: float = Field(1000000, ge=10000, le=100000000)
    paper_commission_rate: float = Field(0.0003, ge=0, le=0.003)
    paper_min_commission: float = Field(5, ge=0, le=100)
    paper_order_type: Literal["limit", "market"] = "limit"


ADMIN_FIELDS = (
    "model_enabled",
    "model_provider",
    "model_name",
    "model_user_daily_limit",
    "model_user_minute_limit",
    "model_site_daily_limit",
    "model_max_output_tokens",
    "agent_max_output_tokens",
    "risk_max_output_tokens",
    "risk_document_output_tokens",
    "model_http_timeout_seconds",
    "model_total_timeout_seconds",
    "risk_document_http_timeout_seconds",
    "risk_document_total_timeout_seconds",
    "risk_document_chunk_chars",
    "market_user_minute_limit",
    "market_ip_minute_limit",
    "catalog_ip_minute_limit",
    "paper_max_accounts",
)
AdminValues = create_model(
    "AdminValues",
    __base__=StrictModel,
    **{
        name: (Settings.model_fields[name].annotation, Settings.model_fields[name])
        for name in ADMIN_FIELDS
    },
)


class PersonalUpdate(StrictModel):
    preferences: Preferences
    version: int = Field(ge=0)

    @model_validator(mode="after")
    def complete(self):
        if self.preferences.model_fields_set != set(Preferences.model_fields):
            raise ValueError("请提交完整个人设置")
        return self


class AdminUpdate(StrictModel):
    values: AdminValues
    version: int = Field(ge=0)

    @model_validator(mode="after")
    def complete(self):
        if self.values.model_fields_set != set(ADMIN_FIELDS):
            raise ValueError("请提交完整管理员设置")
        return self


class SecretUpdate(StrictModel):
    dashscope_api_key: str = Field(max_length=4096, repr=False)
    version: int = Field(ge=0)


class PasswordUpdate(StrictModel):
    current_password: str = Field(max_length=128, repr=False)
    new_password: str = Field(min_length=6, max_length=15, repr=False)
