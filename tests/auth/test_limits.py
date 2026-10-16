"""Shared admission behavior against isolated storage; no real model requests."""

from datetime import timedelta
from importlib.util import find_spec

import httpx
import pytest

from tests.auth.conftest import activate, post


def limits():
    assert find_spec("app.model_limits") is not None, "shared model admission is missing"
    from app import model_limits

    return model_limits


def config(**values):
    from app.config import Settings

    # Local runtime tuning must not change the reservation scenarios under test.
    defaults = dict(model_user_minute_limit=2, model_total_timeout_seconds=60)
    return Settings(**(defaults | values))


def test_document_admission_has_own_http_deadline_and_fenced_lease(env):
    m = limits()
    _, factory, _ = env
    settings = config()
    now = m.utcnow()
    document = m.admit(factory, 1, settings, now=now, purpose="risk_document")
    assert document.remaining() > 170
    assert (document.expires_at - now).total_seconds() > 170
    assert document.before_attempt(now=now) > 110
    with pytest.raises(m.RateLimited):
        m.admit(factory, 1, settings, now=now + timedelta(seconds=100))
    document.release()
    normal = m.admit(factory, 1, settings, now=now + timedelta(seconds=101))
    assert normal.remaining() <= 60
    assert normal.before_attempt(now=now + timedelta(seconds=101)) <= 30
    normal.release()


def test_rolling_quota_owner_separation_and_release(env):
    m = limits()
    _, factory, _ = env
    now = m.utcnow()
    first = m.admit(factory, 1, config(), now=now)
    with pytest.raises(m.RateLimited):
        m.admit(factory, 1, config(), now=now)
    other = m.admit(factory, 2, config(), now=now)
    other.release()
    first.release()
    second = m.admit(factory, 1, config(), now=now + timedelta(seconds=1))
    second.release()
    with pytest.raises(m.RateLimited):
        m.admit(factory, 1, config(), now=now + timedelta(seconds=59))
    third = m.admit(factory, 1, config(), now=now + timedelta(seconds=61))
    third.release()


def test_daily_quota_and_expiry_fences_stale_release(env):
    m = limits()
    _, factory, _ = env
    now = m.utcnow()
    settings = config(model_user_daily_limit=2)
    old = m.admit(factory, 1, settings, now=now)
    fresh = m.admit(factory, 1, settings, now=now + timedelta(seconds=100))
    old.release()
    with pytest.raises(m.RateLimited):
        m.admit(factory, 1, settings, now=now + timedelta(seconds=101))
    with pytest.raises(m.ModelDeadlineExceeded):
        old.before_attempt(now=now + timedelta(seconds=101))
    fresh.release()
    with pytest.raises(m.RateLimited):
        m.admit(factory, 1, settings, now=now + timedelta(minutes=2))
    m.admit(factory, 1, settings, now=now + timedelta(days=1)).release()


def test_global_attempt_budget_counts_connect_retry(env):
    m = limits()
    from app.llm_client import QwenModelClient

    _, factory, _ = env
    admission = m.admit(factory, 1, config(model_site_daily_limit=2))
    calls = []

    def retry(request):
        calls.append(request)
        assert request.read()
        if len(calls) == 1:
            raise httpx.ConnectError("isolated failure")
        assert __import__("json").loads(request.content)["max_tokens"] == 1024
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    with httpx.Client(transport=httpx.MockTransport(retry)) as transport:
        model = QwenModelClient("test-only", transport).with_admission(admission)
        assert model.chat([]) == "ok"
        with pytest.raises(m.RateLimited):
            model.chat([])
    assert len(calls) == 2
    admission.release()
    with pytest.raises(m.RateLimited):
        m.admit(factory, 2, config(model_site_daily_limit=2))


@pytest.mark.parametrize("route,payload", [
    ("/agent/chat", {"messages": [{"role": "user", "content": "研究"}]}),
    ("/risk-summary", {"input_text": "研究"}),
])
def test_rejection_before_model_lookup_and_disabled_mode(env, monkeypatch, route, payload):
    m = limits()
    from app import agent_api, risk_api
    from app.auth.dependencies import get_settings

    client = activate(env)
    factory = env[1]
    settings = config(model_user_daily_limit=1)
    client.app.dependency_overrides[get_settings] = lambda: settings
    # Preserve the same-origin fixture's CSRF settings.
    settings.site_base_url = "http://testserver"
    settings.auth_cookie_secure = False
    m.admit(factory, 1, settings).release()
    calls = []

    def forbidden():
        calls.append(True)
        raise AssertionError("rejection must precede client construction")

    monkeypatch.setattr(agent_api, "get_client", forbidden)
    client.app.dependency_overrides[risk_api.get_model_client] = forbidden
    response = post(client, route, payload)
    assert response.status_code == 429, response.text
    assert int(response.headers["Retry-After"]) > 0
    assert calls == []
    settings.model_enabled = False
    response = post(client, route, payload)
    assert response.status_code == 503
    assert calls == []
    assert client.get("/api/v1/auth/session").json()["model_mode"] == "disabled"


def test_database_unavailable_fails_closed(env):
    m = limits()
    from sqlalchemy.exc import OperationalError

    def unavailable():
        raise OperationalError("isolated", {}, Exception("secret"))

    with pytest.raises(m.LimitsUnavailable):
        m.admit(unavailable, 1, config())


@pytest.mark.parametrize("route,payload", [
    ("/agent/chat", {"messages": [{"role": "user", "content": "x"}]}),
    ("/risk-summary", {"input_text": "x"}),
])
def test_model_transport_timeout_is_safe_and_releases_lease(env, monkeypatch, route, payload):
    m = limits()
    from app import agent_api, risk_api
    from app.llm_client import ModelTimeoutError

    client = activate(env)

    class TimeoutClient:
        def chat(self, *args):
            raise ModelTimeoutError("credential-bearing provider error")

        chat_with_tools = chat

    monkeypatch.setattr(agent_api, "get_client", TimeoutClient)
    client.app.dependency_overrides[risk_api.get_model_client] = TimeoutClient
    response = post(client, route, payload)
    assert response.status_code == 504
    assert "credential" not in response.text
    m.admit(env[1], 1, config()).release()


def test_exception_releases_and_bootstrap_market_throttle(env, monkeypatch):
    m = limits()
    from app import agent_api
    from app.auth.dependencies import get_settings

    client = activate(env)
    settings = config(site_base_url="http://testserver", auth_cookie_secure=False,
                      market_user_minute_limit=1, bootstrap_ip_minute_limit=2)
    client.app.dependency_overrides[get_settings] = lambda: settings

    def fail():
        raise RuntimeError("secret")

    monkeypatch.setattr(agent_api, "get_client", fail)
    payload = {"messages": [{"role": "user", "content": "x"}]}
    assert post(client, "/agent/chat", payload).status_code == 500
    m.admit(env[1], 1, settings).release()
    assert client.get("/api/v1/market/watchlist").status_code == 200
    response = client.get("/api/v1/market/watchlist")
    assert response.status_code == 429
    # This fixture already made anonymous bootstrap requests while activating the user.
    # Reset only its isolated public bucket before checking the configured boundary.
    from sqlalchemy import delete

    from app.auth.models import ThrottleBucket

    with env[1]() as db:
        db.execute(delete(ThrottleBucket).where(ThrottleBucket.key.like("bootstrap-ip:%")))
        db.commit()
    client.cookies.clear()
    assert client.get("/api/v1/auth/session").status_code == 200
    client.cookies.clear()
    assert client.get("/api/v1/auth/session").status_code == 200
    assert client.get("/api/v1/auth/session").status_code == 429


def test_market_daily_price_reads_and_public_catalog_are_throttled(env):
    limits()
    from app.auth.dependencies import get_settings

    client = activate(env)
    client.app.dependency_overrides[get_settings] = lambda: config(
        site_base_url="http://testserver", auth_cookie_secure=False,
        market_user_minute_limit=1, catalog_ip_minute_limit=1,
    )
    assert client.get("/api/v1/stocks/600519.SH/daily-prices").status_code == 404
    assert client.get("/api/v1/stocks/600519.SH/daily-prices").status_code == 429
    client.cookies.clear()
    assert client.get("/api/v1/stocks/stats").status_code == 200
    assert client.get("/api/v1/stocks/stats").status_code == 429


def test_bootstrap_existing_anonymous_session_is_throttled(env):
    limits()
    from app.auth.dependencies import get_settings

    client = env[0]
    client.app.dependency_overrides[get_settings] = lambda: config(
        site_base_url="http://testserver", auth_cookie_secure=False,
        bootstrap_ip_minute_limit=1,
    )
    assert client.get("/api/v1/auth/session").status_code == 200
    assert client.get("/api/v1/auth/session").status_code == 429


def test_database_pool_wait_is_bounded_without_connecting():
    from app.database import engine

    # 连接池超时不应无限等待；10秒是合理的平衡点（允许锁等待但不无限等）
    assert engine.pool.timeout() <= 10
