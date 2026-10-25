"""Real cookies and CSRF, isolated SQLite and an in-memory native-store stand-in."""

from app.auth.dependencies import get_settings
from app.config import Settings
from tests.auth.conftest import activate, post


def test_context_preferences_are_private_csrf_protected_and_account_scoped(env, monkeypatch):
    client, _, _ = env
    records = {}

    class Store:
        def __init__(self, settings, actor_id):
            self.actor_id = actor_id

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read_preferences(self):
            return records.get(self.actor_id)

        def save_preferences(self, preferences):
            records[self.actor_id] = preferences

        def clear_preferences(self):
            records.pop(self.actor_id, None)

    monkeypatch.setattr("app.context_api.ContextStore", Store)
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        site_base_url="http://testserver", auth_cookie_secure=False, openviking_enabled=True
    )
    path = "/api/v1/context/preferences"
    assert client.get(path).status_code == 401
    activate(env)
    assert client.put(path, json={}).status_code == 403
    assert client.delete(path).status_code == 403
    token = client.get("/api/v1/auth/session").json()["csrf_token"]
    headers = {"Origin": "http://testserver", "X-CSRF-Token": token}
    assert client.put(path, json={"answer_detail": "detailed"}, headers=headers).status_code == 200
    assert client.get(path).json()["preferences"]["answer_detail"] == "detailed"
    assert post(client, "/auth/logout").status_code == 200
    assert client.get(path).status_code == 401
    activate(env, email="context-b@example.com")
    assert client.get(path).json()["preferences"] is None
    token = client.get("/api/v1/auth/session").json()["csrf_token"]
    headers["X-CSRF-Token"] = token
    assert client.request("DELETE", path, json={}, headers=headers).status_code == 200
    assert len(records) == 1
