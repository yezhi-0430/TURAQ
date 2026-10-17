import pytest
from conftest import activate, invite, post
from sqlalchemy import select


@pytest.mark.parametrize("length,expected", [(5, 422), (6, 202), (15, 202), (16, 422)])
def test_password_unicode_bounds(env, length, expected):
    client, factory, _ = env
    result = post(
        client,
        "/auth/register",
        dict(email="a@example.com", password="密" * length, invite_code=invite(factory)),
    )
    assert result.status_code == expected


def test_verification_activation_and_single_use(env):
    from app.auth.models import Invite, User

    client, factory, mail = env
    code = invite(factory, max_uses=1)
    assert (
        post(
            client,
            "/auth/register",
            dict(email="A@EXAMPLE.COM", password="abcdef", invite_code=code),
        ).status_code
        == 202
    )
    assert (
        post(client, "/auth/login", dict(email="a@example.com", password="abcdef")).status_code
        == 401
    )
    token = mail.messages[-1][2]
    assert post(client, "/auth/verify-email", {"token": token}).status_code == 200
    assert post(client, "/auth/verify-email", {"token": token}).status_code == 400
    with factory() as db:
        assert db.scalar(select(Invite)).uses == 1
        assert db.scalar(select(User)).email == "a@example.com"


def test_invite_exhaustion_and_replacement(env):
    client, factory, mail = env
    code = invite(factory, max_uses=1)
    for email in ["a@example.com", "b@example.com"]:
        assert (
            post(
                client, "/auth/register", dict(email=email, password="abcdef", invite_code=code)
            ).status_code
            == 202
        )
    token_a, token_b = [msg[2] for msg in mail.messages]
    assert post(client, "/auth/verify-email", {"token": token_a}).status_code == 200
    assert post(client, "/auth/verify-email", {"token": token_b}).status_code == 400
    assert (
        post(
            client, "/auth/verify-email", {"token": token_b, "invite_code": invite(factory)}
        ).status_code
        == 200
    )


def test_private_routes_and_csrf(env):
    client, _, _ = env
    assert client.get("/api/v1/watchlists").status_code == 401
    bootstrap = client.get("/api/v1/auth/session").json()
    assert bootstrap["user"] is None and bootstrap["mail_configured"]
    assert (
        client.post(
            "/api/v1/auth/login", json=dict(email="a@example.com", password="abcdef")
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json=dict(email="a@example.com", password="abcdef"),
            headers={"Origin": "https://evil.example", "X-CSRF-Token": bootstrap["csrf_token"]},
        ).status_code
        == 403
    )


def test_reset_revokes_sessions_and_preserves_whitespace(env):
    client, factory, mail = env
    activate(env, password=" abcde ")
    from sqlalchemy import update

    from app.auth.models import ThrottleBucket
    from app.auth.service import utcnow

    with factory() as db:
        db.execute(update(ThrottleBucket).values(expires_at=utcnow()))
        db.commit()
    old_cookie = client.cookies.get("session")
    assert (
        post(client, "/auth/login", dict(email="a@example.com", password="abcde")).status_code
        == 401
    )
    assert post(client, "/auth/forgot-password", {"email": "a@example.com"}).status_code == 202
    token = mail.messages[-1][2]
    assert (
        post(
            client, "/auth/reset-password", {"token": token, "password": "新密码六个字"}
        ).status_code
        == 200
    )
    client.cookies.set("session", old_cookie)
    assert client.get("/api/v1/watchlists").status_code == 401
    client.cookies.clear()
    assert (
        post(
            client, "/auth/reset-password", {"token": token, "password": "新密码六个字"}
        ).status_code
        == 400
    )


def test_ownership_foreign_group_all_paths_and_market(env):
    client, factory, _ = env
    activate(env)
    group = post(client, "/watchlists", {"name": "A"}).json()["id"]
    assert post(client, "/auth/logout").status_code == 200
    activate(env, "b@example.com")
    assert client.get("/api/v1/watchlists").json() == []
    assert client.get(f"/api/v1/watchlists/{group}/stocks").status_code == 404
    assert (
        post(
            client, f"/watchlists/{group}/stocks", {"symbol": "600000.SH", "name": "evil"}
        ).status_code
        == 404
    )
    result = post(
        client,
        "/agent/actions/remove-stock",
        {
            "kind": "execution_request",
            "operation": "remove_watchlist_stock",
            "watchlist_id": group,
            "stock_code": "600000.SH",
        },
    )
    assert result.status_code == 404
    assert client.get("/api/v1/market/watchlist").json()["stocks"] == []


def test_shared_stock_metadata_and_admin_only_import(env):
    from app.database import Stock

    client, factory, _ = env
    activate(env)
    with factory() as db:
        db.add(Stock(symbol="600000.SH", name="trusted"))
        db.commit()
    group = post(client, "/watchlists", {"name": "A"}).json()["id"]
    response = post(client, f"/watchlists/{group}/stocks", {"symbol": "600000.SH", "name": "evil"})
    assert response.status_code == 201
    assert response.json()["name"] == "trusted"
    assert post(client, "/stocks/600000.SH/daily-prices", {}).status_code == 403


def test_disabled_user_cannot_use_existing_session(env):
    from app.auth.models import User

    client, factory, _ = env
    activate(env)
    with factory() as db:
        db.scalar(select(User)).disabled = True
        db.commit()
    assert client.get("/api/v1/watchlists").status_code == 401


def test_mail_unconfigured_generic_response(env):
    client, factory, mail = env
    mail.configured = False
    for email in ["missing@example.com", "a@example.com"]:
        assert post(client, "/auth/forgot-password", {"email": email}).status_code == 503
    assert (
        post(
            client,
            "/auth/register",
            dict(email="a@example.com", password="abcdef", invite_code=invite(factory)),
        ).status_code
        == 503
    )
