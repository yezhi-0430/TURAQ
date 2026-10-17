"""Real cookie/CSRF/admission boundary against the auth suite's isolated storage."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.dependencies import get_settings
from app.config import Settings
from tests.auth.conftest import activate, post


def test_private_risk_routes_cookie_csrf_logout_and_owner(env):
    c, _, _ = env
    c.app.dependency_overrides[get_settings] = lambda: Settings(
        site_base_url="http://testserver", auth_cookie_secure=False, model_provider="fake"
    )
    path = "/api/v1/risk/analyses"
    body = {"input_text": "公告原文", "request_id": str(uuid4())}
    assert c.get("/api/v1/risk/events").status_code == 401
    assert c.post(path, json=body).status_code in (401, 403)
    activate(env)
    assert c.post(path, json=body).status_code == 403
    saved = post(c, "/risk/analyses", body)
    assert saved.status_code == 201, saved.text
    eid = saved.json()["id"]
    assert saved.json()["model_mode"] == "fake"
    with TestClient(c.app) as other:
        assert other.get(f"/api/v1/risk/events/{eid}").status_code == 401
    assert post(c, "/auth/logout").status_code == 200
    activate(env, email="b@example.com")
    assert c.get(f"/api/v1/risk/events/{eid}").status_code == 404
    token = c.get("/api/v1/auth/session").json()["csrf_token"]
    assert (
        c.patch(
            f"/api/v1/risk/events/{eid}",
            json={"status": "following"},
            headers={"Origin": "http://testserver", "X-CSRF-Token": token},
        ).status_code
        == 404
    )
    assert c.get("/api/v1/risk/analyses").json()["total"] == 0


def test_collection_has_private_csrf_lease_but_does_not_consume_model_quota(env):
    from sqlalchemy import select

    from app.model_limits import ModelBudget

    c, factory, _ = env
    c.app.dependency_overrides[get_settings] = lambda: Settings(
        site_base_url="http://testserver",
        auth_cookie_secure=False,
        model_provider="fake",
        model_user_daily_limit=1,
        model_user_minute_limit=1,
    )
    activate(env)
    task = post(
        c, "/risk/tasks", dict(request_id=str(uuid4()), scope="stock", symbol="600519.SH", days=90)
    ).json()
    path = f"/risk/tasks/{task['id']}/collect"
    assert c.post("/api/v1" + path, json={}).status_code == 403
    result = post(c, path)
    assert result.status_code == 200
    assert result.json()["items"][0]["progress"]["phase"] == "ready"
    with factory() as db:
        budgets = db.scalars(select(ModelBudget).where(ModelBudget.key.like("user:%"))).all()
        assert budgets and all(b.events == [] and b.lease_token is None for b in budgets)
    assert post(c, f"/risk/tasks/{task['id']}/process").status_code == 200
    post(c, "/auth/logout")
    activate(env, email="other-collector@example.com")
    assert post(c, path).status_code == 404


def test_disabled_and_rate_limited_admission(env):
    c, _, _ = env
    activate(env)
    c.app.dependency_overrides[get_settings] = lambda: Settings(
        site_base_url="http://testserver",
        auth_cookie_secure=False,
        model_provider="fake",
        model_enabled=False,
    )
    assert (
        post(c, "/risk/analyses", {"input_text": "公告", "request_id": str(uuid4())}).status_code
        == 503
    )
    c.app.dependency_overrides[get_settings] = lambda: Settings(
        site_base_url="http://testserver",
        auth_cookie_secure=False,
        model_provider="fake",
        model_user_minute_limit=1,
    )
    assert (
        post(c, "/risk/analyses", {"input_text": "公告", "request_id": str(uuid4())}).status_code
        == 201
    )
    response = post(c, "/risk/analyses", {"input_text": "公告", "request_id": str(uuid4())})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_auto_tasks_use_cookie_csrf_quota_and_owner(env):
    c, _, _ = env
    c.app.dependency_overrides[get_settings] = lambda: Settings(
        site_base_url="http://testserver", auth_cookie_secure=False, model_provider="fake"
    )
    payload = dict(request_id=str(uuid4()), scope="stock", symbol="600519.SH", days=90)
    assert c.post("/api/v1/risk/tasks", json=payload).status_code in (401, 403)
    activate(env)
    assert c.post("/api/v1/risk/tasks", json=payload).status_code == 403
    created = post(c, "/risk/tasks", payload)
    assert created.status_code == 201, created.text
    tid = created.json()["id"]
    processed = post(c, f"/risk/tasks/{tid}/process")
    assert processed.status_code == 200, processed.text
    eid = processed.json()["items"][0]["event_id"]
    assert post(c, f"/risk/tasks/{tid}/process").status_code == 409
    detail = c.get(f"/api/v1/risk/events/{eid}").json()
    assert detail["model_mode"] == "fake" and detail["risk_level"] == "unknown"
    assert detail["result"]["facts"] == [] and detail["evidence"] == []
    assert post(c, "/auth/logout").status_code == 200
    activate(env, email="b@example.com")
    assert c.get(f"/api/v1/risk/tasks/{tid}").status_code == 404
    assert post(c, f"/risk/tasks/{tid}/cancel").status_code == 404
    assert c.get(f"/api/v1/risk/events/{eid}").status_code == 404
