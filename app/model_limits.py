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
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import Actor, get_session_factory, get_settings, require_actor
from app.auth.models import ModelBudget
from app.auth.service import aware, digest, utcnow
from app.auth.throttle import RateLimited, reserve
from app.config import Settings

logger = logging.getLogger(__name__)


class LimitsUnavailable(Exception):
    pass


class ModelDeadlineExceeded(Exception):
    pass


def db_now(db):
    if db.bind.dialect.name == "postgresql":
        # Bound lock waits too; quota-service outages cannot leave requests hanging.
        db.execute(text("SET LOCAL statement_timeout = '3000ms'"))
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


class Admission:
    def __init__(self, factory, actor_id, settings, token, expires_at):
        self.factory = factory
        self.actor_id = actor_id
        self.settings = settings
        self.token = token
        self.expires_at = expires_at
        self.deadline = time.monotonic() + settings.model_total_timeout_seconds

    def remaining(self):
        seconds = self.deadline - time.monotonic()
        if seconds <= 0:
            raise ModelDeadlineExceeded("研究处理超时")
        return seconds

    def bound_database_work(self, db):
        remaining = self.remaining()
        if db.bind.dialect.name == "postgresql":
            milliseconds = max(1, math.floor(remaining * 1000))
            db.execute(select(func.set_config("statement_timeout", str(milliseconds), True)))

    def before_attempt(self, *, now=None):
        self.remaining()
        if not self.settings.model_enabled:
            raise LimitsUnavailable("研究服务已暂停")
        try:
            with self.factory() as db, db.begin():
                clock = now or db_now(db)
                user = locked_budget(db, f"user:{self.actor_id}")
                clock = now or db_now(db)
                if (
                    user.lease_token != self.token
                    or user.lease_expires_at is None
                    or aware(user.lease_expires_at) <= clock
                ):
                    raise ModelDeadlineExceeded("研究处理超时")
                site = locked_budget(db, "site:attempts")
                events = check_window(
                    site.events, self.settings.model_site_daily_limit, 86400, clock.timestamp()
                )
                site.events = events + [clock.timestamp()]
                lease_remaining = (aware(user.lease_expires_at) - clock).total_seconds() - 1
                timeout = min(self.remaining(), self.settings.model_http_timeout_seconds,
                              lease_remaining)
                if timeout <= 0:
                    raise ModelDeadlineExceeded("研究处理超时")
            # Recompute after committing the reservation, before starting any network work.
            return min(timeout, self.remaining())
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


def admit(factory, actor_id, settings, *, now=None):
    if not settings.model_enabled:
        raise LimitsUnavailable("研究服务已暂停")
    token = str(uuid4())
    try:
        with factory() as db, db.begin():
            clock = now or db_now(db)
            user = locked_budget(db, f"user:{actor_id}")
            clock = now or db_now(db)
            if user.lease_token and aware(user.lease_expires_at) > clock:
                raise RateLimited(math.ceil((aware(user.lease_expires_at) - clock).total_seconds()))
            stamp = clock.timestamp()
            events = check_window(user.events, settings.model_user_daily_limit, 86400, stamp)
            check_window(events, settings.model_user_minute_limit, 60, stamp)
            # Reject an already-exhausted site budget before client construction too.
            site = locked_budget(db, "site:attempts")
            check_window(site.events, settings.model_site_daily_limit, 86400, stamp)
            user.events = events + [stamp]
            user.lease_token = token
            expiry = clock + timedelta(seconds=settings.model_total_timeout_seconds + 5)
            user.lease_expires_at = expiry
        return Admission(factory, actor_id, settings, token, expiry)
    except SQLAlchemyError as exc:
        raise LimitsUnavailable("研究额度服务暂不可用") from exc


def public_error(exc):
    if isinstance(exc, RateLimited):
        return HTTPException(429, "请求额度已用尽，请稍后重试",
                             headers={"Retry-After": str(exc.retry_after)})
    if isinstance(exc, ModelDeadlineExceeded):
        return HTTPException(504, "研究处理超时，请稍后重试")
    return HTTPException(503, "研究服务暂不可用")


def model_admission(
    actor: Actor = Depends(require_actor), factory=Depends(get_session_factory),
    settings: Settings = Depends(get_settings),
) -> Iterator[Admission]:
    try:
        admission = admit(factory, actor.id, settings)
    except (RateLimited, LimitsUnavailable) as exc:
        raise public_error(exc) from exc
    try:
        yield admission
    finally:
        admission.release()


def bind_model(client, admission):
    # Custom/fake clients are also deadline-checked, but never billed as HTTP attempts.
    if hasattr(client, "with_admission"):
        return client.with_admission(admission)

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
                return httpx.Response(response.status_code, headers=response.headers,
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
                     factory=Depends(get_session_factory), settings=Depends(get_settings)):
    read_limit(factory, f"market-user:{actor.id}", settings.market_user_minute_limit)
    read_limit(factory, "market-ip:" + client_ip(request), settings.market_ip_minute_limit)


def catalog_admission(request: Request, factory=Depends(get_session_factory),
                      settings=Depends(get_settings)):
    read_limit(factory, "catalog-ip:" + client_ip(request), settings.catalog_ip_minute_limit)
