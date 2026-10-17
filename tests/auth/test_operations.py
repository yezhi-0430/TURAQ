from datetime import timedelta

import pytest
from conftest import activate, invite, post
from sqlalchemy import select, update


def test_admin_invite_adjustment_and_revocation(env):
    from app.auth.admin import adjust_invite, disable_user
    from app.auth.models import Invite, User

    client, factory, mail = env
    code = invite(factory)
    with factory() as db:
        row = db.scalar(select(Invite))
        adjust_invite(db, row.id, max_uses=60)
        assert db.get(Invite, row.id).max_uses == 60
        adjust_invite(db, row.id, revoked=True)
    post(client, "/auth/register", dict(email="a@example.com", password="abcdef", invite_code=code))
    assert not mail.messages
    activate(env, "b@example.com")
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "b@example.com"))
        disable_user(db, user.id)
    assert client.get("/api/v1/watchlists").status_code == 401


def test_expired_invite_and_pending_token_rejected_without_consumption(env):
    from app.auth.models import EmailToken, Invite, User
    from app.auth.service import utcnow

    client, factory, mail = env
    code = invite(factory)
    post(client, "/auth/register", dict(email="a@example.com", password="abcdef", invite_code=code))
    token = mail.messages[-1][2]
    with factory() as db:
        db.execute(update(Invite).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
    assert post(client, "/auth/verify-email", {"token": token}).status_code == 400
    with factory() as db:
        assert not db.scalar(select(User)).verified
        assert not db.scalar(select(EmailToken)).consumed
        assert db.scalar(select(Invite)).uses == 0


def test_login_and_mail_shared_throttles(env):
    client, _, _ = env
    for _ in range(5):
        assert (
            post(
                client, "/auth/login", dict(email="missing@example.com", password="abcdef")
            ).status_code
            == 401
        )
    rejected = post(client, "/auth/login", dict(email="missing@example.com", password="abcdef"))
    assert rejected.status_code == 429 and int(rejected.headers["retry-after"]) > 0
    assert (
        post(client, "/auth/forgot-password", dict(email="missing@example.com")).status_code == 202
    )
    assert (
        post(client, "/auth/forgot-password", dict(email="missing@example.com")).status_code == 429
    )


def test_smtp_transport_timeout_tls_and_link(monkeypatch):
    from app.auth.mail import SMTPMailer
    from app.config import Settings

    captures = {}

    class SMTP:
        def __init__(self, *args, **kwargs):
            captures["timeout"] = kwargs["timeout"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            captures["tls"] = True

        def login(self, *args):
            pass

        def send_message(self, message):
            captures["message"] = message

    monkeypatch.setattr("app.auth.mail.smtplib.SMTP", SMTP)
    SMTPMailer(
        Settings(
            smtp_host="smtp.example.com",
            smtp_from="noreply@example.com",
            site_base_url="https://site.example",
        )
    ).send("a@example.com", "verify", "opaque")
    assert captures["tls"] and captures["timeout"] > 0
    assert "https://site.example/#verify=opaque" in captures["message"].get_content()


def test_smtp_failures_never_expose_supplier_secret(env, caplog):
    from app.auth.mail import MailUnavailable

    client, factory, mail = env

    def fail(*args):
        raise MailUnavailable("private supplier credentials")

    mail.send = fail
    response = post(
        client,
        "/auth/register",
        dict(email="a@example.com", password="abcdef", invite_code=invite(factory)),
    )
    assert response.status_code == 202
    assert "private supplier" not in response.text + caplog.text
    assert "a@example.com" not in caplog.text


def test_payload_cannot_assign_owner_or_admin(env):
    client, factory, _ = env
    response = post(
        client,
        "/auth/register",
        dict(email="a@example.com", password="abcdef", invite_code=invite(factory), is_admin=True),
    )
    assert response.status_code == 422
    activate(env)
    assert post(client, "/watchlists", {"name": "A", "owner_id": 999}).status_code == 422


def test_actions_persist_actor_audit(env):
    from app.auth.models import ActionAuditRecord
    from app.database import Stock

    client, factory, _ = env
    activate(env)
    with factory() as db:
        db.add(Stock(symbol="600000.SH", name="trusted"))
        db.commit()
    group = post(client, "/watchlists", {"name": "A"}).json()["id"]
    post(client, f"/watchlists/{group}/stocks", {"symbol": "600000.SH", "name": "untrusted"})
    payload = {
        "kind": "execution_request",
        "operation": "remove_watchlist_stock",
        "watchlist_id": group,
        "stock_code": "600000.SH",
    }
    assert post(client, "/agent/actions/remove-stock", payload).status_code == 200
    assert post(client, "/agent/actions/remove-stock", payload).status_code == 404
    with factory() as db:
        rows = list(db.scalars(select(ActionAuditRecord).order_by(ActionAuditRecord.id)))
        assert [(r.actor_id, r.status) for r in rows] == [(1, "success"), (1, "error")]


def test_unknown_stock_uses_only_trusted_server_quote(env, monkeypatch):
    from app.market_api import service

    client, _, _ = env
    activate(env)
    group = post(client, "/watchlists", {"name": "A"}).json()["id"]
    calls = []

    async def quotes(symbols):
        calls.append(symbols)
        return {
            "quotes": [
                {"symbol": "600000.SH", "name": "trusted source", "kind": "stock", "stale": False}
            ]
        }

    monkeypatch.setattr(service, "quotes", quotes)
    response = post(
        client, f"/watchlists/{group}/stocks", {"symbol": "600000.SH", "name": "attacker"}
    )
    assert response.status_code == 201
    assert response.json()["name"] == "trusted source" and len(calls) == 1


def test_non_ascii_csrf_is_rejected(env):
    client, _, _ = env
    client.get("/api/v1/auth/session")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "abcdef"},
        headers={b"Origin": b"http://testserver", b"X-CSRF-Token": b"\xc3\xa9"},
    )
    assert response.status_code == 403


def test_auth_validation_never_echoes_password_or_tokens(env):
    client, _, _ = env
    secret = "TOO-LONG-password-value"
    response = post(client, "/auth/reset-password", {"token": "private", "password": secret})
    assert response.status_code == 422
    assert secret not in response.text and "private" not in response.text


def test_mail_service_wide_outage_is_generic(env):
    from app.auth.mail import MailUnavailable

    client, _, mail = env

    def down():
        raise MailUnavailable("private smtp response")

    mail.check_available = down
    for email in ["a@example.com", "missing@example.com"]:
        response = post(client, "/auth/forgot-password", {"email": email})
        assert response.status_code == 503
        assert "private smtp" not in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/watchlists",
        "/api/v1/market/quotes",
        "/api/v1/market/minutes/600000.SH",
        "/api/v1/market/watchlist",
        "/api/v1/market/klines/600000.SH",
        "/api/v1/stocks",
        "/api/v1/stocks/600000.SH/daily-prices",
    ],
)
def test_all_private_reads_require_identity(env, path):
    client, _, _ = env
    assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/agent/chat", {"messages": [{"role": "user", "content": "research"}]}),
        ("/risk-summary", {"input_text": "research"}),
    ],
)
def test_anonymous_model_requests_do_not_create_clients(env, monkeypatch, path, payload):
    from app import agent_api, risk_api

    client, _, _ = env

    def forbidden(*args, **kwargs):
        pytest.fail("model client must not be created")

    monkeypatch.setattr(agent_api, "get_client", forbidden)
    client.app.dependency_overrides[risk_api.get_model_client] = forbidden
    assert post(client, path, payload).status_code == 401


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_foreign_group_mutations_are_404(env, method):
    client, _, _ = env
    activate(env)
    group = post(client, "/watchlists", {"name": "private"}).json()["id"]
    post(client, "/auth/logout")
    activate(env, "b@example.com")
    csrf = client.get("/api/v1/auth/session").json()["csrf_token"]
    response = client.request(
        method,
        f"/api/v1/watchlists/{group}",
        json={"name": "evil"},
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("length,expected", [(5, 422), (6, 400), (15, 400), (16, 422)])
def test_reset_password_unicode_bounds(env, length, expected):
    client, _, _ = env
    assert (
        post(
            client, "/auth/reset-password", {"token": "z" * 43, "password": "密" * length}
        ).status_code
        == expected
    )


def test_existing_pending_registration_cannot_replace_password(env):
    from sqlalchemy import update

    from app.auth.models import ThrottleBucket
    from app.auth.service import utcnow

    client, factory, mail = env
    code = invite(factory)
    post(
        client,
        "/auth/register",
        {"email": "a@example.com", "password": "original", "invite_code": code},
    )
    original_token = mail.messages[-1][2]
    with factory() as db:
        db.execute(update(ThrottleBucket).values(expires_at=utcnow()))
        db.commit()
    post(
        client,
        "/auth/register",
        {"email": "a@example.com", "password": "attacker", "invite_code": code},
    )
    assert len(mail.messages) == 1
    assert post(client, "/auth/verify-email", {"token": original_token}).status_code == 200
    assert (
        post(client, "/auth/login", {"email": "a@example.com", "password": "original"}).status_code
        == 200
    )
    assert (
        post(client, "/auth/login", {"email": "a@example.com", "password": "attacker"}).status_code
        == 401
    )


def test_logout_rotation_and_expiry(env):
    from app.auth.models import LoginSession
    from app.auth.service import digest, utcnow

    client, factory, _ = env
    activate(env)
    old = client.cookies.get("session")
    assert post(client, "/auth/logout").json()["user"] is None
    client.cookies.clear()
    client.cookies.set("session", old)
    assert client.get("/api/v1/watchlists").status_code == 401
    client.cookies.clear()
    assert (
        post(
            client, "/auth/login", {"email": "a@example.com", "password": " 密码四五六 "}
        ).status_code
        == 200
    )
    with factory() as db:
        row = db.get(LoginSession, digest(client.cookies.get("session")))
        row.last_seen_at = utcnow() - timedelta(hours=25)
        db.commit()
    assert client.get("/api/v1/watchlists").status_code == 401


def test_session_response_is_never_cached(env):
    client, _, _ = env
    response = client.get("/api/v1/auth/session")
    assert response.headers.get("cache-control") == "no-store"


def test_unexpected_background_errors_cannot_change_response_or_log_secrets(env, caplog):
    from fastapi.testclient import TestClient

    client, factory, mail = env

    def broken(*args):
        raise RuntimeError("private-user@example.com private-token")

    mail.send = broken
    with TestClient(client.app, raise_server_exceptions=False) as failure_client:
        response = post(
            failure_client,
            "/auth/register",
            {"email": "a@example.com", "password": "abcdef", "invite_code": invite(factory)},
        )
    assert response.status_code == 202
    assert "private-user@example.com" not in caplog.text
    assert "private-token" not in caplog.text


@pytest.mark.parametrize("target", ["price", "risk"])
def test_non_watchlist_payloads_reject_identity_fields(target):
    from pydantic import ValidationError

    from app.main import DailyPriceRequest
    from app.risk_api import RiskSummaryRequest

    model = DailyPriceRequest if target == "price" else RiskSummaryRequest
    payload = (
        {
            "trade_date": "2026-10-01",
            "open": "10",
            "close": "10",
            "high": "11",
            "low": "9",
            "volume": 1,
        }
        if target == "price"
        else {"input_text": "research"}
    )
    with pytest.raises(ValidationError):
        model(**payload, owner_id=1)


def test_successful_login_does_not_consume_failure_budget(env):
    client, _, _ = env
    activate(env, password="abcdef")
    for _ in range(6):
        assert (
            post(
                client, "/auth/login", {"email": "a@example.com", "password": "abcdef"}
            ).status_code
            == 200
        )
