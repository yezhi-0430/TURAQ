from sqlalchemy import select

from tests.auth.conftest import activate, post


def write(client, path, payload, method="put"):
    csrf = client.get("/api/v1/auth/session").json()["csrf_token"]
    return getattr(client, method)(
        "/api/v1" + path,
        json=payload,
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
    )


def admin(env):
    from app.auth.dependencies import get_settings
    from app.auth.models import User

    client = activate(env)
    client.app.dependency_overrides[get_settings]().model_provider = "fake"
    with env[1]() as db:
        db.scalar(select(User)).is_admin = True
        db.commit()
    return client


def test_personal_version_validation_and_csrf(env):
    client = activate(env)
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["preferences"]["research_max_rounds"] == 15
    payload = {"preferences": {**data["preferences"], "density": "compact"}, "version": 0}
    assert client.put("/api/v1/settings", json=payload).status_code == 403
    saved = write(client, "/settings", payload)
    assert saved.status_code == 200
    assert saved.json()["version"] == 1
    assert write(client, "/settings", payload).status_code == 409
    payload["version"] = 1
    payload["preferences"]["reduce_motion"] = "false"
    assert write(client, "/settings", payload).status_code == 422


def test_admin_override_audit_and_runtime(env):
    client = admin(env)
    response = client.get("/api/v1/admin/settings")
    assert response.status_code == 200
    data = response.json()
    values = {**data["values"], "paper_max_accounts": 2, "model_enabled": False}
    saved = write(client, "/admin/settings", {"values": values, "version": data["version"]})
    assert saved.status_code == 200
    from app.auth.dependencies import get_settings
    from app.user_settings.runtime import resolve_settings

    base = client.app.dependency_overrides[get_settings]()
    runtime = resolve_settings(base, env[1])
    assert runtime.paper_max_accounts == 2
    assert runtime.model_enabled is False
    assert client.get("/api/v1/auth/session").json()["model_mode"] == "disabled"
    assert client.get("/api/v1/admin/settings/audit").json()["items"][0]["changes"]


def test_role_and_session_security(env):
    client = activate(env)
    assert client.get("/api/v1/admin/settings").status_code == 403
    response = client.get("/api/v1/settings/sessions")
    assert response.status_code == 200
    from app.auth.models import User
    from app.auth.service import digest, new_session

    sessions = response.json()["sessions"]
    assert sessions[0]["current"]
    assert sessions[0]["id"] != digest(client.cookies.get("session"))
    with env[1]() as db:
        new_session(db, db.scalar(select(User.id)))
    assert post(client, "/settings/sessions/revoke-others").json()["count"] == 1
    assert (
        post(
            client, "/settings/password", {"current_password": "wrong", "new_password": "newpass"}
        ).status_code
        == 400
    )
    assert (
        post(
            client,
            "/settings/password",
            {"current_password": " 密码四五六 ", "new_password": "newpass"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/settings").status_code == 401


def test_secrets_encrypt_clear_and_never_disclose(env, monkeypatch):
    client = admin(env)
    from app.auth.dependencies import get_settings

    base = client.app.dependency_overrides[get_settings]()
    base.settings_encryption_key = None
    assert (
        write(
            client,
            "/admin/settings/secrets",
            {"dashscope_api_key": "secret-example", "version": 0},
            "post",
        ).status_code
        == 503
    )
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    base.settings_encryption_key = SecretStr(Fernet.generate_key().decode())
    response = write(
        client,
        "/admin/settings/secrets",
        {"dashscope_api_key": "secret-example", "version": 0},
        "post",
    )
    assert response.status_code == 200
    assert "secret-example" not in response.text
    from app.user_settings.runtime import resolve_settings

    assert resolve_settings(base, env[1]).dashscope_api_key.get_secret_value() == "secret-example"
    assert "secret-example" not in client.get("/api/v1/admin/settings/audit").text
    assert (
        write(
            client, "/admin/settings/secrets", {"dashscope_api_key": "", "version": 1}, "post"
        ).status_code
        == 200
    )


def test_runtime_admission_and_agent_consume_overrides(env):
    client = admin(env)
    data = client.get("/api/v1/admin/settings").json()
    data["values"]["model_enabled"] = False
    assert (
        write(client, "/admin/settings", {"values": data["values"], "version": 0}).status_code
        == 200
    )
    response = post(client, "/agent/chat", {"messages": [{"role": "user", "content": "你好"}]})
    assert response.status_code == 503


def test_secret_only_override_preserves_deployment_values(env):
    client = admin(env)
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    from app.auth.dependencies import get_settings
    from app.user_settings.runtime import resolve_settings

    base = client.app.dependency_overrides[get_settings]()
    base.model_user_daily_limit = 37
    base.settings_encryption_key = SecretStr(Fernet.generate_key().decode())
    assert (
        write(
            client,
            "/admin/settings/secrets",
            {"dashscope_api_key": "example", "version": 0},
            "post",
        ).status_code
        == 200
    )
    assert resolve_settings(base, env[1]).model_user_daily_limit == 37


def test_complete_documents_required_and_sensitive_errors_redacted(env):
    client = admin(env)
    assert write(client, "/settings", {"preferences": {}, "version": 0}).status_code == 422
    assert write(client, "/admin/settings", {"values": {}, "version": 0}).status_code == 422
    response = write(
        client, "/admin/settings/secrets", {"dashscope_api_key": "x" * 4097, "version": 0}, "post"
    )
    assert response.status_code == 422
    assert "x" * 30 not in response.text


def test_paper_account_cap_and_client_configuration(env, monkeypatch):
    client = admin(env)
    data = client.get("/api/v1/admin/settings").json()
    data["values"].update(paper_max_accounts=1, model_name="configured-test-model")
    assert (
        write(client, "/admin/settings", {"values": data["values"], "version": 0}).status_code
        == 200
    )
    monkeypatch.setattr("app.paper_trading.api.SessionLocal", env[1])
    assert (
        post(
            client, "/paper-trading/accounts", {"name": "first", "initial_capital": 10000}
        ).status_code
        == 201
    )
    assert (
        post(
            client, "/paper-trading/accounts", {"name": "second", "initial_capital": 10000}
        ).status_code
        == 409
    )
    captured = []
    from app.llm_client import FakeModelClient

    def create(settings, http_client):
        captured.append(settings.model_name)
        return FakeModelClient(reply="test reply")

    monkeypatch.setattr("app.agent_api.create_model_client", create)
    assert (
        post(
            client, "/agent/chat", {"messages": [{"role": "user", "content": "hello"}]}
        ).status_code
        == 200
    )
    assert captured == ["configured-test-model"]


def test_user_isolation_restore_and_password_throttle(env):
    client = activate(env)
    data = client.get("/api/v1/settings").json()
    saved = write(
        client,
        "/settings",
        {"preferences": {**data["preferences"], "density": "compact"}, "version": 0},
    )
    assert saved.status_code == 200
    restored = write(client, "/settings", {"preferences": data["defaults"], "version": 1})
    assert restored.json()["preferences"] == data["defaults"]
    post(client, "/auth/logout")
    activate(env, email="other@example.com")
    assert client.get("/api/v1/settings").json()["version"] == 0
    for _ in range(5):
        assert (
            post(
                client,
                "/settings/password",
                {"current_password": "wrong", "new_password": "newpass"},
            ).status_code
            == 400
        )
    assert (
        post(
            client, "/settings/password", {"current_password": "wrong", "new_password": "newpass"}
        ).status_code
        == 429
    )


def test_bad_model_encryption_does_not_disable_non_model_services(env, monkeypatch):
    client = admin(env)
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    from app.auth.dependencies import get_settings

    base = client.app.dependency_overrides[get_settings]()
    base.settings_encryption_key = SecretStr(Fernet.generate_key().decode())
    assert write(client, "/admin/settings/secrets", {
        "dashscope_api_key": "synthetic-secret", "version": 0,
    }, "post").status_code == 200
    base.settings_encryption_key = SecretStr(Fernet.generate_key().decode())
    monkeypatch.setattr("app.paper_trading.api.SessionLocal", env[1])
    assert client.get("/api/v1/paper-trading/accounts").status_code == 200
    diagnostics = client.get("/api/v1/admin/settings").json()["diagnostics"]
    assert any(item["status"] == "error" for item in diagnostics)
