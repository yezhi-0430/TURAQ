"""Real authenticated/CSRF requests against an isolated database."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from tests.auth.conftest import post


def seed(env):
    from app.auth.models import User
    from app.auth.service import password_hash

    client, factory, _ = env
    with factory.begin() as db:
        db.add_all(
            [
                User(
                    id=1,
                    email="admin@example.com",
                    password_hash=password_hash("abcdef"),
                    verified=True,
                    pending_expires_at=datetime.now(UTC),
                    is_admin=True,
                ),
                User(
                    id=2,
                    email="member@example.com",
                    password_hash=password_hash("abcdef"),
                    verified=True,
                    pending_expires_at=datetime.now(UTC),
                ),
            ]
        )
    assert (
        post(
            client, "/auth/login", {"email": "admin@example.com", "password": "abcdef"}
        ).status_code
        == 200
    )
    return client, factory


def mutate(client, path, body=None, method="PATCH", **headers):
    csrf = client.get("/api/v1/auth/session").json()["csrf_token"]
    return client.request(
        method,
        "/api/v1" + path,
        json=body or {},
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf, **headers},
    )


@pytest.mark.parametrize("path", ["users", "invites", "stats/overview", "stats/llm-usage"])
def test_admin_reads_require_real_admin(env, path):
    client, _ = seed(env)
    assert client.get("/api/v1/admin/" + path).status_code == 200
    assert (
        post(
            client, "/auth/login", {"email": "member@example.com", "password": "abcdef"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/admin/" + path).status_code == 403
    client.cookies.clear()
    assert client.get("/api/v1/admin/" + path).status_code == 401


def test_users_pagination_filters_and_no_credentials(env):
    client, _ = seed(env)
    response = client.get("/api/v1/admin/users?limit=1&offset=0")
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["total"] == 2 and len(data["users"]) == 1
    assert data["users"][0]["id"] == 2
    assert data["users"][0]["created_at"] is None
    assert set(data["users"][0]) == {
        "id",
        "email",
        "verified",
        "disabled",
        "is_admin",
        "created_at",
        "invite_id",
        "last_seen",
    }
    assert client.get("/api/v1/admin/users?limit=1&offset=1").json()["users"][0]["id"] == 1
    seen = client.get("/api/v1/admin/users?limit=1&offset=1").json()["users"][0]["last_seen"]
    assert seen.endswith(("Z", "+00:00"))
    assert client.get("/api/v1/admin/users?q=member").json()["total"] == 1
    assert client.get("/api/v1/admin/users?q=%25").json()["total"] == 0
    for query in ["limit=101", "limit=0", "offset=-1"]:
        assert client.get("/api/v1/admin/users?" + query).status_code == 422


def test_disabling_revokes_sessions_and_enabling_does_not_restore_them(env):
    from app.auth.models import LoginSession, User

    client, factory = seed(env)
    post(client, "/auth/login", {"email": "member@example.com", "password": "abcdef"})
    member_cookies = dict(client.cookies)
    post(client, "/auth/login", {"email": "admin@example.com", "password": "abcdef"})
    admin_cookies = dict(client.cookies)
    assert mutate(client, "/admin/users/2", {"disabled": True}).status_code == 200
    with factory() as db:
        assert db.get(User, 2).disabled
        assert all(
            row.revoked for row in db.scalars(select(LoginSession).where(LoginSession.user_id == 2))
        )
    client.cookies.clear()
    client.cookies.update(member_cookies)
    assert client.get("/api/v1/watchlists").status_code == 401
    client.cookies.clear()
    client.cookies.update(admin_cookies)
    assert mutate(client, "/admin/users/2", {"disabled": False}).status_code == 200
    client.cookies.clear()
    client.cookies.update(member_cookies)
    assert client.get("/api/v1/watchlists").status_code == 401
    assert (
        post(
            client, "/auth/login", {"email": "member@example.com", "password": "abcdef"}
        ).status_code
        == 200
    )


def test_user_writes_protect_admins_validate_payload_and_csrf(env):
    client, _ = seed(env)
    assert mutate(client, "/admin/users/1", {"disabled": True}).status_code == 409
    assert mutate(client, "/admin/users/999", {"disabled": True}).status_code == 404
    for body in [{"disabled": "true"}, {"disabled": 1}, {"disabled": False, "is_admin": True}, {}]:
        assert mutate(client, "/admin/users/2", body).status_code == 422
    assert client.patch("/api/v1/admin/users/2", json={"disabled": True}).status_code == 403
    assert (
        mutate(client, "/admin/users/2", {"disabled": True}, Origin="http://evil.test").status_code
        == 403
    )
    assert (
        post(
            client, "/auth/login", {"email": "member@example.com", "password": "abcdef"}
        ).status_code
        == 200
    )
    assert mutate(client, "/admin/users/1", {"disabled": True}).status_code == 403


def test_invites_only_return_new_plaintext_once_and_revoke_preserves_history(env):
    from app.auth.models import Invite
    from app.auth.service import digest

    client, factory = seed(env)
    response = mutate(client, "/admin/invites", {"max_uses": 3, "days": 2}, method="POST")
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    created = response.json()
    assert created["code"]
    with factory() as db:
        assert db.get(Invite, created["id"]).digest == digest(created["code"])
    listing = client.get("/api/v1/admin/invites").json()
    assert listing["invites"][0]["status"] == "active"
    assert listing["invites"][0]["expires_at"].endswith(("Z", "+00:00"))
    assert created["code"] not in str(listing) and "digest" not in str(listing)
    assert listing["invites"][0]["code"] is None
    assert mutate(client, f"/admin/invites/{created['id']}", method="DELETE").status_code == 200
    assert client.get("/api/v1/admin/invites").json()["invites"][0]["status"] == "revoked"
    with factory() as db:
        assert db.get(Invite, created["id"]) is not None
    assert mutate(client, "/admin/invites/999", method="DELETE").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"max_uses": 0, "days": 1},
        {"max_uses": True, "days": 1},
        {"max_uses": 2, "days": "7"},
        {"max_uses": 2, "days": 0},
        {"max_uses": 2, "days": 1, "is_admin": True},
    ],
)
def test_invalid_invites_are_rejected(env, body):
    client, _ = seed(env)
    assert mutate(client, "/admin/invites", body, method="POST").status_code == 422


def test_invite_statuses_and_available_slots(env):
    from app.auth.models import Invite
    from app.auth.service import utcnow

    client, factory = seed(env)
    now = utcnow()
    with factory.begin() as db:
        for i, uses, expired, revoked in [
            (1, 2, False, False),
            (2, 5, False, False),
            (3, 1, True, False),
            (4, 0, False, True),
        ]:
            db.add(
                Invite(
                    id=i,
                    digest=str(i),
                    max_uses=5,
                    uses=uses,
                    expires_at=now + timedelta(days=-1 if expired else 1),
                    revoked=revoked,
                )
            )
    rows = client.get("/api/v1/admin/invites").json()["invites"]
    assert {r["id"]: r["status"] for r in rows} == {
        1: "active",
        2: "exhausted",
        3: "expired",
        4: "revoked",
    }
    assert client.get("/api/v1/admin/stats/overview").json()["available_slots"] == 3


def test_statistics_distinguish_tools_http_attempts_and_unknown_costs(env, monkeypatch):
    from app.auth.models import ModelBudget
    from app.database import ToolAuditRecord

    client, factory = seed(env)
    now = datetime(2026, 10, 12, 8, tzinfo=UTC)
    # Import only after tests have established the module exists.
    from app.admin import stats_service

    monkeypatch.setattr(stats_service, "utcnow", lambda: now)
    with factory.begin() as db:
        db.add(
            ModelBudget(
                key="site:attempts",
                events=[
                    (now - timedelta(minutes=1)).timestamp(),
                    (now - timedelta(days=2)).timestamp(),
                ],
            )
        )
        db.add(ModelBudget(key="user:2", events=[now.timestamp()]))
        for i, status, stamp in [
            (1, "success", datetime(2026, 10, 11, 16, tzinfo=UTC)),
            (2, "error", datetime(2026, 10, 11, 15, 59, tzinfo=UTC)),
        ]:
            db.add(
                ToolAuditRecord(
                    run_id=f"run-{i}",
                    actor_id=2,
                    tool_name="calculate_change",
                    arguments="{}",
                    status=status,
                    result=None,
                    error=None,
                    duration_ms=1,
                    created_at=stamp,
                )
            )
    overview = client.get("/api/v1/admin/stats/overview").json()
    assert overview["total_users"] == 2
    assert overview["model_http_attempts_24h"] == 1
    assert overview["research_requests_24h"] == 1
    assert overview["tool_attempts_today"] == 1
    assert overview["estimated_cost"] is None and overview["tokens"] is None
    usage = client.get("/api/v1/admin/stats/llm-usage").json()
    assert usage["metric"] == "tool_attempts"
    assert usage["by_user"][0]["calls"] == 2
    assert usage["by_user"][0]["success_rate"] == 0.5
    assert usage["daily_trend"][-1] == {"date": "2026-10-12", "calls": 1}
    assert usage["daily_trend"][-2] == {"date": "2026-10-11", "calls": 1}
