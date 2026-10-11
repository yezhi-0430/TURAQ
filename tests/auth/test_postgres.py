"""Real PostgreSQL transactions, confined to a unique schema in the dedicated test DB."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def pg():
    from app.config import Settings
    from app.database import Base

    settings = Settings(database_name="a_share_risk_agent_test")
    assert settings.database_url.database == "a_share_risk_agent_test"
    admin = create_engine(settings.database_url)
    schema = "auth_test_" + uuid4().hex
    with admin.begin() as db:
        db.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    Base.metadata.create_all(engine)
    try:
        yield engine, sessionmaker(bind=engine)
    finally:
        engine.dispose()
        with admin.begin() as db:
            db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_postgres_invite_last_seat_race(pg):
    from app.auth.models import Invite, User
    from app.auth.service import create_invite, issue_token, register, verify_email

    _, factory = pg
    with factory() as db:
        _, code = create_invite(db, max_uses=1)
        first = register(db, "a@example.com", "abcdef", code)
        token_a = issue_token(db, first.id, "verify")
        second = register(db, "b@example.com", "abcdef", code)
        token_b = issue_token(db, second.id, "verify")
    barrier = Barrier(2)

    def run(token):
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                verify_email(db, token)
                return True
            except ValueError:
                db.rollback()
                return False

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, [token_a, token_b]))
    assert sorted(results) == [False, True]
    with factory() as db:
        assert db.scalar(select(Invite)).uses == 1
        assert len(list(db.scalars(select(User).where(User.verified.is_(True))))) == 1


def test_postgres_token_double_activation_and_throttle_race(pg):
    from app.auth.models import Invite
    from app.auth.service import create_invite, issue_token, register, verify_email
    from app.auth.throttle import RateLimited, reserve

    _, factory = pg
    with factory() as db:
        _, code = create_invite(db)
        user = register(db, "a@example.com", "abcdef", code)
        token = issue_token(db, user.id, "verify")
    barrier = Barrier(2)

    def run(_):
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                verify_email(db, token)
                return True
            except ValueError:
                return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, range(2))) == [False, True]
    with factory() as db:
        assert db.scalar(select(Invite)).uses == 1
    barrier = Barrier(2)

    def admit(_):
        barrier.wait(timeout=10)
        try:
            reserve(factory, "race", 1, 60)
            return True
        except RateLimited:
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(admit, range(2))) == [False, True]


def test_explicit_legacy_migration_requires_verified_owner_and_is_repeatable(pg):
    from app.auth.admin import bootstrap_admin
    from app.database import Stock, Watchlist
    from app.schema_upgrade import upgrade_database

    engine, factory = pg
    with factory() as db:
        owner = bootstrap_admin(db, "admin@example.com", "abcdef", verified_email=True)
        db.add(Stock(symbol="600000.SH", name="preserved"))
        db.commit()
    with engine.begin() as db:
        db.execute(text("ALTER TABLE watchlists DROP COLUMN owner_id CASCADE"))
        db.execute(text("INSERT INTO watchlists(name) VALUES ('legacy')"))
        db.execute(text("ALTER TABLE tool_audit_records DROP COLUMN actor_id CASCADE"))
    with pytest.raises(ValueError, match="owner|所有者|归属"):
        upgrade_database(engine)
    upgrade_database(engine, owner_id=owner)
    upgrade_database(engine, owner_id=owner)
    with factory() as db:
        assert db.scalar(select(Watchlist)).owner_id == owner
        assert db.scalar(select(Stock)).name == "preserved"
