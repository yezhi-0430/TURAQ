"""Public auth responses must finish before account-dependent SMTP work."""

import asyncio
import json
from datetime import timedelta
from threading import Event

import pytest
from conftest import invite


@pytest.mark.parametrize(
    "endpoint,state,should_deliver",
    [
        ("register", "missing", True),
        ("register", "verified", False),
        ("resend-verification", "pending", True),
        ("resend-verification", "verified", False),
        ("resend-verification", "missing", False),
        ("forgot-password", "verified", True),
        ("forgot-password", "pending", False),
        ("forgot-password", "missing", False),
    ],
)
def test_response_finishes_before_account_dependent_delivery(env, endpoint, state, should_deliver):
    from sqlalchemy import event

    from app.auth.models import User
    from app.auth.service import password_hash, utcnow

    client, factory, mail = env
    if state != "missing":
        with factory() as db:
            db.add(
                User(
                    email="account@example.com",
                    password_hash=password_hash("abcdef"),
                    verified=state == "verified",
                    pending_expires_at=utcnow() + timedelta(hours=24),
                )
            )
            db.commit()
    payload = {"email": "account@example.com"}
    if endpoint == "register":
        payload.update(password="abcdef", invite_code=invite(factory))
    bootstrap = client.get("/api/v1/auth/session").json()
    response_finished = Event()
    deliveries_after_response = []
    preflights_before_response = []
    lookups_after_response = []

    def inspect_account_lookup(connection, cursor, statement, parameters, context, many):
        if "FROM users" in statement:
            lookups_after_response.append(response_finished.is_set())

    event.listen(factory.kw["bind"], "before_cursor_execute", inspect_account_lookup)

    def available():
        preflights_before_response.append(not response_finished.is_set())

    def gated_delivery(*args):
        # A causality assertion: transport cannot complete until the response reached the client.
        # Timeout bounds a broken implementation; this is not a timing threshold or fake delay.
        deliveries_after_response.append(response_finished.wait(timeout=2))

    mail.check_available = available
    mail.send = gated_delivery
    body = json.dumps(payload).encode()
    messages = []

    async def request():
        received = False
        total_body = 0
        expected_length = None

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Future()

        async def send(message):
            nonlocal total_body, expected_length
            messages.append(message)
            if message["type"] == "http.response.start":
                headers = dict(message["headers"])
                expected_length = int(headers[b"content-length"])
            if message["type"] == "http.response.body":
                total_body += len(message.get("body", b""))
                if total_body == expected_length:
                    response_finished.set()

        await client.app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/auth/" + endpoint,
                "raw_path": ("/api/v1/auth/" + endpoint).encode(),
                "query_string": b"",
                "root_path": "",
                "server": ("testserver", 80),
                "client": ("testclient", 50000),
                "headers": [
                    (b"host", b"testserver"),
                    (b"origin", b"http://testserver"),
                    (b"content-type", b"application/json"),
                    (b"x-csrf-token", bootstrap["csrf_token"].encode()),
                    (b"cookie", ("session=" + client.cookies.get("session")).encode()),
                ],
            },
            receive,
            send,
        )

    asyncio.run(request())
    assert messages[0]["status"] == 202
    assert preflights_before_response == [True]
    assert lookups_after_response and all(lookups_after_response)
    assert deliveries_after_response == ([True] if should_deliver else [])
    public_body = b"".join(m.get("body", b"") for m in messages)
    assert json.loads(public_body) == {"detail": "请求已受理；符合条件时将发送邮件。"}
