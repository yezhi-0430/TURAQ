"""Configured SMTP only; injected transports belong to tests."""

import smtplib
import ssl
from email.message import EmailMessage

from fastapi import Depends

from app.auth.dependencies import get_settings
from app.config import Settings


class MailUnavailable(Exception):
    pass


class SMTPMailer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.configured = bool(settings.smtp_host and settings.smtp_from and settings.site_base_url)

    def _connect(self):
        s = self.settings
        client_type = smtplib.SMTP_SSL if s.smtp_tls == "ssl" else smtplib.SMTP
        kwargs = {"timeout": s.smtp_timeout_seconds}
        if s.smtp_tls == "ssl":
            kwargs["context"] = ssl.create_default_context()
        client = client_type(s.smtp_host, s.smtp_port, **kwargs)
        try:
            if s.smtp_tls == "starttls":
                client.starttls(context=ssl.create_default_context())
            if s.smtp_username:
                client.login(
                    s.smtp_username, s.smtp_password.get_secret_value() if s.smtp_password else ""
                )
            return client
        except Exception:
            client.close()
            raise

    def check_available(self) -> None:
        """Same preflight for every address so service outages do not enumerate accounts."""
        if not self.configured:
            raise MailUnavailable()
        try:
            with self._connect() as client:
                code, _ = client.noop()
                if code != 250:
                    raise MailUnavailable()
        except (OSError, smtplib.SMTPException) as exc:
            raise MailUnavailable() from exc

    def send(self, email: str, purpose: str, token: str) -> None:
        if not self.configured:
            raise MailUnavailable()
        message = EmailMessage()
        message["From"] = self.settings.smtp_from
        message["To"] = email

        # 根据 purpose 设置主题和内容
        if purpose == "verify":
            message["Subject"] = "验证邮箱"
        elif purpose == "login":
            message["Subject"] = "登录验证链接"
        else:  # reset
            message["Subject"] = "重置密码"

        url = f"{self.settings.site_base_url.rstrip('/')}/#{purpose}={token}"
        message.set_content(f"{url}\n链接有效期 30 分钟。")

        try:
            with self._connect() as client:
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise MailUnavailable() from exc


def get_mailer(settings: Settings = Depends(get_settings)) -> SMTPMailer:
    return SMTPMailer(settings)
