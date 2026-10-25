from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password: SecretStr
    dashscope_api_key: SecretStr | None = None
    settings_encryption_key: SecretStr | None = None
    openviking_enabled: bool = False
    openviking_url: str = "http://127.0.0.1:1934"
    openviking_root_key: SecretStr | None = None
    paper_max_accounts: int = Field(default=10, ge=1, le=100)
    model_provider: Literal["fake", "qwen"] = "fake"
    model_name: str = Field(default="qwen-plus", min_length=1, max_length=120)
    model_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_enabled: bool = True
    model_user_daily_limit: int = Field(default=20, ge=1, le=10000)
    model_user_minute_limit: int = Field(default=2, ge=1, le=1000)
    model_site_daily_limit: int = Field(default=200, ge=1, le=100000)
    model_max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    agent_max_output_tokens: int = Field(default=4096, ge=1, le=8192)
    risk_max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    risk_document_output_tokens: int = Field(default=4096, ge=1, le=8192)
    risk_document_http_timeout_seconds: float = Field(default=120, gt=0, le=300)
    risk_document_total_timeout_seconds: float = Field(default=180, gt=0, le=600)
    risk_document_chunk_chars: int = Field(default=120000, ge=20000, le=250000)
    model_http_timeout_seconds: float = Field(default=30, gt=0, le=30)
    model_total_timeout_seconds: float = Field(default=60, gt=0, le=120)
    bootstrap_ip_minute_limit: int = Field(default=20, ge=1, le=1000)
    market_user_minute_limit: int = Field(default=120, ge=1, le=10000)
    market_ip_minute_limit: int = Field(default=240, ge=1, le=10000)
    catalog_ip_minute_limit: int = Field(default=120, ge=1, le=10000)

    @property
    def model_mode(self) -> str:
        return self.model_provider if self.model_enabled else "disabled"

    site_base_url: str = "http://localhost:8888"
    auth_cookie_name: str = "session"
    auth_cookie_secure: bool = True
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_tls: Literal["starttls", "ssl"] = "starttls"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_timeout_seconds: float = 10

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )
