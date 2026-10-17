"""Real session/CSRF administration QA on loopback and memory SQLite only.

Run python -m tests.manual.admin_browser_fixture; open http://127.0.0.1:8893.
Synthetic accounts admin@example.com / member@example.com, password admin-test.
Never use real credentials in this fixture. Stop process to discard all data.
"""

import os
from datetime import timedelta
from pathlib import Path


def build_fixture():
    os.environ.update(
        DATABASE_HOST="127.0.0.1",
        DATABASE_PORT="1",
        DATABASE_NAME="admin_qa_unused",
        DATABASE_USER="test",
        DATABASE_PASSWORD="test",
        MODEL_PROVIDER="fake",
        MODEL_ENABLED="false",
        DASHSCOPE_API_KEY="",
    )
    import httpx
    from fastapi.staticfiles import StaticFiles
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import agent_api, database, main, market_api
    from app.auth.dependencies import get_session_factory, get_settings
    from app.auth.mail import get_mailer
    from app.auth.models import Invite, User
    from app.auth.service import password_hash, utcnow
    from app.config import Settings

    def no_network(*args, **kwargs):
        raise AssertionError("Outbound HTTP is disabled in this isolated fixture")

    httpx.Client.send = no_network
    httpx.AsyncClient.send = no_network
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    factory = sessionmaker(bind=engine)
    database.Base.metadata.create_all(engine)
    database.SessionLocal = main.SessionLocal = agent_api.SessionLocal = market_api.SessionLocal = (
        factory
    )
    main.start_scheduler = main.shutdown_scheduler = lambda: None
    now = utcnow()
    with factory.begin() as db:
        for i, email, admin in [
            (1, "admin@example.com", True),
            (2, "member@example.com", False),
            (3, "pending@example.com", False),
        ]:
            db.add(
                User(
                    id=i,
                    email=email,
                    password_hash=password_hash("admin-test"),
                    verified=i != 3,
                    is_admin=admin,
                    pending_expires_at=now + timedelta(days=1),
                )
            )
        db.add_all(
            [
                Invite(
                    digest="synthetic-active",
                    max_uses=50,
                    uses=2,
                    expires_at=now + timedelta(days=7),
                ),
                Invite(
                    digest="synthetic-expired",
                    max_uses=10,
                    uses=1,
                    expires_at=now - timedelta(days=1),
                ),
            ]
        )
        for i, status in [(1, "success"), (2, "error")]:
            db.add(
                database.ToolAuditRecord(
                    run_id="qa-only-" + str(i),
                    actor_id=2,
                    tool_name="calculate_change",
                    arguments="{}",
                    status=status,
                    result=None,
                    error=None,
                    duration_ms=1,
                    created_at=now,
                )
            )
    settings = Settings(
        _env_file=None,
        model_provider="fake",
        model_enabled=False,
        site_base_url="http://127.0.0.1:8893",
        auth_cookie_secure=False,
    )

    class NoMail:
        configured = False

    app = main.create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_mailer] = NoMail
    app.mount(
        "/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "frontend", html=True)
    )
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_fixture(), host="127.0.0.1", port=8893)
