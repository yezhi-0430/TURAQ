"""Database-shared rolling budgets and fenced, bounded model request leases."""

import asyncio
import logging
import math
import time
from collections.abc import Iterator
from datetime import timedelta
from uuid import uuid4

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import event, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import Actor, get_session_factory, require_actor
from app.auth.models import ModelBudget
from app.auth.service import aware, digest, utcnow
from app.auth.throttle import RateLimited, reserve
from app.config import Settings
from app.user_settings.runtime import get_runtime_policy, get_runtime_settings

logger = logging.getLogger(__name__)


class LimitsUnavailable(Exception):
    pass


class ModelDeadlineExceeded(Exception):
    pass


def db_now(db):
    if db.bind.dialect.name == "postgresql":
        # Bound lock waits too; quota-service outages cannot leave requests hanging.
        db.execute(text("SET LOCAL statement_timeout = '3000ms'"))
        db.execute(text("SET LOCAL lock_timeout = '3000ms'"))
        return db.scalar(select(func.clock_timestamp()))
    return utcnow()


def locked_budget(db, key):
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(ModelBudget).values(key=key, events=[]).on_conflict_do_nothing())
    return db.scalar(select(ModelBudget).where(ModelBudget.key == key).with_for_update())


def check_window(events, limit, seconds, stamp):
    active = [event for event in events if event > stamp - seconds]
    if len(active) >= limit:
        raise RateLimited(math.ceil(min(active) + seconds - stamp))
    return active


def bind_database_deadline(db, remaining, *, max_seconds=None):
    """Bound every tool/audit SQL statement, including ORM flushes.

    Hooks belong only to this Session/Connection. Transaction completion removes
    the connection hook and its deadline state before the pool can reuse it.
    """
    state_key = "model_deadline"
    if not db.info.get("model_deadline_hooks"):
        def after_begin(session, transaction, connection):
            state = session.info.get(state_key)
            if state is None or connection in state["connections"]:
                return

            def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                seconds = state["remaining"]()
                if state["max_seconds"] is not None:
                    seconds = min(seconds, state["max_seconds"])
                milliseconds = max(1, math.floor(seconds * 1000))
                # Use this cursor directly: no recursive SQLAlchemy execution event.
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true), "
                    "set_config('lock_timeout', %s, true)",
                    (str(milliseconds), str(min(milliseconds, 3000))),
                )
                state["remaining"]()

            event.listen(connection, "before_cursor_execute", before_cursor_execute)
            state["connections"][connection] = before_cursor_execute

        def after_transaction_end(session, transaction):
            if transaction.parent is None:
                state = session.info.pop(state_key, None)
                if state:
                    for connection, hook in state["connections"].items():
                        event.remove(connection, "before_cursor_execute", hook)

        def before_commit(session):
            state = session.info.get(state_key)
            if state:
                state["remaining"]()

        event.listen(db, "after_begin", after_begin)
        event.listen(db, "after_transaction_end", after_transaction_end)
        event.listen(db, "before_commit", before_commit)
        db.info["model_deadline_hooks"] = after_begin

    state = db.info.setdefault(state_key, {"connections": {}})
    state.update(remaining=remaining, max_seconds=max_seconds)
    connection = db.connection()
    db.info["model_deadline_hooks"](db, db.get_transaction(), connection)
    remaining()  # Pool/connect time is part of the same absolute processing budget.


class Admission:
    def __init__(self, factory, actor_id, settings, token, expires_at, *, deadline=None,
                 purpose="default"):
        self.factory = factory
        self.actor_id = actor_id
        self.settings = settings
        self.token = token
        self.expires_at = expires_at
        self.http_timeout = (settings.risk_document_http_timeout_seconds
                             if purpose == "risk_document" else settings.model_http_timeout_seconds)
        total_timeout = (settings.risk_document_total_timeout_seconds
                         if purpose == "risk_document" else settings.model_total_timeout_seconds)
        self.deadline = (time.monotonic() + total_timeout
                         if deadline is None else deadline)
        self.attempt_deadline = self.deadline

    def remaining(self):
        seconds = self.deadline - time.monotonic()
        if seconds <= 0:
            raise ModelDeadlineExceeded("研究处理超时")
        return seconds

    def bound_database_work(self, db, *, max_seconds=None):
        self.remaining()
        if db.bind.dialect.name == "postgresql":
            bind_database_deadline(db, self.remaining, max_seconds=max_seconds)

    def before_attempt(self, *, now=None):
        self.remaining()
        if not self.settings.model_enabled:
            raise LimitsUnavailable("研究服务已暂停")
        try:
            with self.factory() as db, db.begin():
                self.bound_database_work(db, max_seconds=3)
                if now is None:
                    db_now(db)
                user = locked_budget(db, f"user:{self.actor_id}")
                site = locked_budget(db, "site:attempts")
                # Sample monotonic time BEFORE asking the DB clock, conservatively
                # mapping the stored expiry after all reservation lock waits.
                sampled_at = time.monotonic()
                clock = now or db_now(db)
                if (
                    user.lease_token != self.token
                    or user.lease_expires_at is None
                    or aware(user.lease_expires_at) <= clock
                ):
                    raise ModelDeadlineExceeded("研究处理超时")
                events = check_window(
                    site.events, self.settings.model_site_daily_limit, 86400, clock.timestamp()
                )
                site.events = events + [clock.timestamp()]
                lease_remaining = (aware(user.lease_expires_at) - clock).total_seconds() - 1
                self.attempt_deadline = min(self.deadline, sampled_at + lease_remaining)
                self.remaining()
            # Recompute after committing the reservation, before starting any network work.
            timeout = min(self.http_timeout, self.remaining(),
                          self.attempt_deadline - time.monotonic())
            if timeout <= 0:
                raise ModelDeadlineExceeded("研究处理超时")
            return timeout
        except SQLAlchemyError as exc:
            raise LimitsUnavailable("研究额度服务暂不可用") from exc

    def release(self):
        try:
            with self.factory() as db, db.begin():
                db_now(db)
                db.execute(update(ModelBudget).where(
                    ModelBudget.key == f"user:{self.actor_id}",
                    ModelBudget.lease_token == self.token,
                ).values(lease_token=None, lease_expires_at=None))
        except SQLAlchemyError:
            # Work has stopped; the bounded lease still expires if storage is unavailable.
            logger.error("模型并发租约释放失败")


def admit(factory, actor_id, settings, *, now=None, charge_request=True, purpose="default"):
    timeout = (settings.risk_document_total_timeout_seconds
               if purpose == "risk_document" else settings.model_total_timeout_seconds)
    deadline = time.monotonic() + timeout
    if not settings.model_enabled:
        raise LimitsUnavailable("研究服务已暂停")
    token = str(uuid4())
    admission = Admission(
        factory, actor_id, settings, token, None, deadline=deadline, purpose=purpose
    )
    try:
        with factory() as db, db.begin():
            admission.bound_database_work(db, max_seconds=3)
            if now is None:
                db_now(db)
            user = locked_budget(db, f"user:{actor_id}")
            # Keep the same lock order in admission and attempt reservations.
            site = locked_budget(db, "site:attempts")
            clock = now or db_now(db)
            remaining = admission.remaining()
            if user.lease_token and aware(user.lease_expires_at) > clock:
                raise RateLimited(math.ceil((aware(user.lease_expires_at) - clock).total_seconds()))
            stamp = clock.timestamp()
            if charge_request:
                events = check_window(user.events, settings.model_user_daily_limit, 86400, stamp)
                check_window(events, settings.model_user_minute_limit, 60, stamp)
                # Reject an already-exhausted site budget before client construction too.
                check_window(site.events, settings.model_site_daily_limit, 86400, stamp)
                user.events = events + [stamp]
            user.lease_token = token
            expiry = clock + timedelta(seconds=remaining + 5)
            user.lease_expires_at = expiry
            admission.expires_at = expiry
        admission.remaining()
        return admission
    except SQLAlchemyError as exc:
        raise LimitsUnavailable("研究额度服务暂不可用") from exc


def public_error(exc):
    if isinstance(exc, RateLimited):
        return HTTPException(429, "请求额度已用尽，请稍后重试",
                             headers={"Retry-After": str(exc.retry_after)})
    if isinstance(exc, ModelDeadlineExceeded):
        if str(exc) == "模型请求超时":
            return HTTPException(504, "模型生成超时，请稍后重试")
        return HTTPException(504, "研究处理超时，请稍后重试")
    return HTTPException(503, "研究服务暂不可用")


def model_admission(
    request: Request,
    actor: Actor = Depends(require_actor), factory=Depends(get_session_factory),
    settings: Settings = Depends(get_runtime_settings),
) -> Iterator[Admission]:
    try:
        admission = admit(factory, actor.id, settings,
                          purpose=getattr(request.state, "model_purpose", "default"))
    except (RateLimited, LimitsUnavailable, ModelDeadlineExceeded) as exc:
        raise public_error(exc) from exc
    try:
        yield admission
    finally:
        admission.release()


def bind_model(client, admission, *, purpose="default"):
    # Custom/fake clients are also deadline-checked, but never billed as HTTP attempts.
    if hasattr(client, "with_admission"):
        return client.with_admission(admission, purpose=purpose)

    class BoundedClient:
        def chat(self, messages):
            admission.remaining()
            reply = client.chat(messages)
            admission.remaining()
            return reply

        def chat_with_tools(self, messages, tools):
            admission.remaining()
            reply = client.chat_with_tools(messages, tools)
            admission.remaining()
            return reply

    return BoundedClient()


def deadline_post(url, headers, payload, timeout, *, transport=None, deadline=None):
    """Cancel the actual async HTTP stream, close it, then return to the sync loop.

    No abandoned worker or background HTTP request survives a timeout. The lease is
    released only after asyncio.run has completed cancellation and transport cleanup.
    """
    async def send():
        remaining = min(timeout, deadline - time.monotonic()) if deadline else timeout
        if remaining <= 0:
            raise ModelDeadlineExceeded("模型请求超时")
        async with asyncio.timeout(remaining), httpx.AsyncClient(
            timeout=remaining, transport=transport, trust_env=False, follow_redirects=False
        ) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 1048576:
                        raise ModelDeadlineExceeded("模型响应超出限制")
                    chunks.append(chunk)
                # aiter_bytes already decoded the body; discard wire encoding/framing.
                decoded_headers = response.headers.copy()
                for name in ("content-encoding", "content-length", "transfer-encoding"):
                    decoded_headers.pop(name, None)
                return httpx.Response(response.status_code, headers=decoded_headers,
                                      content=b"".join(chunks))

    try:
        return asyncio.run(send())
    except TimeoutError as exc:
        raise ModelDeadlineExceeded("模型请求超时") from exc


def read_limit(factory, key, count):
    try:
        reserve(factory, key, count, 60)
    except RateLimited as exc:
        raise public_error(exc) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "请求额度服务暂不可用") from exc


def client_ip(request):
    # Ignore untrusted forwarded headers. A trusted proxy must be configured in Uvicorn.
    return digest(request.client.host if request.client else "unknown")


def market_admission(request: Request, actor: Actor = Depends(require_actor),
                     factory=Depends(get_session_factory), settings=Depends(get_runtime_policy)):
    read_limit(factory, f"market-user:{actor.id}", settings.market_user_minute_limit)
    read_limit(factory, "market-ip:" + client_ip(request), settings.market_ip_minute_limit)


def catalog_admission(request: Request, factory=Depends(get_session_factory),
                      settings=Depends(get_runtime_policy)):
    read_limit(factory, "catalog-ip:" + client_ip(request), settings.catalog_ip_minute_limit)
