import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def env(monkeypatch):
    from app.auth.dependencies import get_session_factory, get_settings
    from app.auth.mail import get_mailer
    from app.config import Settings
    from app.database import Base
    from app.main import create_app

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    for module in ["app.main", "app.agent_api", "app.market_api"]:
        monkeypatch.setattr(module + ".SessionLocal", factory)
    # Auth tests must never start the unrelated live market scheduler.
    monkeypatch.setattr("app.main.start_scheduler", lambda: None)
    monkeypatch.setattr("app.main.shutdown_scheduler", lambda: None)
    app = create_app()
    settings = Settings(site_base_url="http://testserver", auth_cookie_secure=False)

    class Mailbox:
        configured = True

        def __init__(self):
            self.messages = []

        def check_available(self):
            pass

        def send(self, email, purpose, token):
            self.messages.append((email, purpose, token))

    mail = Mailbox()
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_mailer] = lambda: mail
    with TestClient(app) as client:
        yield client, factory, mail
    engine.dispose()


def post(client, path, payload=None):
    bootstrap = client.get("/api/v1/auth/session").json()
    return client.post(
        "/api/v1" + path,
        json=payload or {},
        headers={"Origin": "http://testserver", "X-CSRF-Token": bootstrap["csrf_token"]},
    )


def invite(factory, **kwargs):
    from app.auth.service import create_invite

    with factory() as session:
        return create_invite(session, **kwargs)[1]


def activate(env, email="a@example.com", password=" 密码四五六 "):
    client, factory, mail = env
    code = invite(factory)
    response = post(
        client, "/auth/register", dict(email=email, password=password, invite_code=code)
    )
    assert response.status_code == 202, response.text
    assert post(client, "/auth/verify-email", {"token": mail.messages[-1][2]}).status_code == 200
    assert post(client, "/auth/login", dict(email=email, password=password)).status_code == 200
    return client


@pytest.fixture(autouse=True)
def clean_test_database():
    """Override the parent integration suite cleanup; these tests own isolated engines."""
    yield
