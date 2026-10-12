"""A local slow response verifies cancellation closes work before lease release."""

import asyncio
import gzip
import time
import zlib

import httpx
import pytest

from tests.auth.test_limits import limits


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
@pytest.mark.parametrize("status_code", [200, 429])
def test_compressed_response_is_decoded_once(encoding, compress, status_code):
    m = limits()
    body = b'{"message":"compressed response"}'
    compressed = compress(body)
    closed = []

    class CompressedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for offset in range(0, len(compressed), 7):
                yield compressed[offset:offset + 7]

        async def aclose(self):
            closed.append(True)

    async def respond(request):
        return httpx.Response(status_code, headers={
            "Content-Encoding": encoding,
            "Content-Length": str(len(compressed)),
            "Content-Type": "application/json",
            "Retry-After": "17",
        }, stream=CompressedStream())

    response = m.deadline_post("http://isolated/", {}, {}, 1,
                               transport=httpx.MockTransport(respond))
    assert response.status_code == status_code
    assert response.json() == {"message": "compressed response"}
    assert response.content == body
    assert "content-encoding" not in response.headers
    assert int(response.headers["content-length"]) == len(body)
    assert response.headers["content-type"] == "application/json"
    assert response.headers["retry-after"] == "17"
    assert closed == [True]


def test_compressed_response_limit_uses_decoded_size():
    m = limits()
    compressed = gzip.compress(b"x" * 1048577)
    closed = []

    class LargeStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield compressed

        async def aclose(self):
            closed.append(True)

    async def respond(request):
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=LargeStream())

    with pytest.raises(m.ModelDeadlineExceeded, match="模型响应超出限制"):
        m.deadline_post("http://isolated/", {}, {}, 1,
                        transport=httpx.MockTransport(respond))
    assert closed == [True]


def test_total_http_deadline_cancels_trickle_response():
    m = limits()
    active = []

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            active.append(True)
            try:
                while True:
                    await asyncio.sleep(0.02)
                    yield b" "
            finally:
                active.clear()

    async def respond(request):
        return httpx.Response(200, stream=SlowStream())

    start = time.monotonic()
    with pytest.raises(m.ModelDeadlineExceeded):
        m.deadline_post("http://isolated/", {}, {}, 0.08,
                        transport=httpx.MockTransport(respond))
    assert time.monotonic() - start < 1
    assert active == []


def test_tool_deadline_stops_remaining_calls(env):
    m = limits()
    from app.agent_loop import run_agent_loop
    from app.llm_client import FakeModelClient
    from app.llm_types import ToolReply

    reply = ToolReply.model_validate({"tool_calls": [
        {"id": str(i), "type": "function", "function": {
            "name": "calculate_change", "arguments": '{"previous_close":10,"current_close":9}'
        }} for i in range(2)
    ]})
    checks = []
    executions = []

    def deadline():
        checks.append(True)
        if len(checks) == 3:
            raise m.ModelDeadlineExceeded()

    with pytest.raises(m.ModelDeadlineExceeded):
        run_agent_loop(FakeModelClient("", reply), [],
                       check_deadline=deadline,
                       audit_writer=lambda _, record: executions.append(record))
    assert len(executions) == 1


def test_timeout_never_dispatches_next_http_attempt(env):
    m = limits()
    from app.llm_client import QwenModelClient
    from tests.auth.test_limits import config

    admission = m.admit(env[1], 1, config(model_total_timeout_seconds=0.05,
                                         model_http_timeout_seconds=0.05))
    active = []
    calls = []

    async def respond(request):
        calls.append(True)
        active.append(True)
        try:
            await asyncio.sleep(1)
        finally:
            active.clear()

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model = QwenModelClient("test-only", client).with_admission(admission)
        with pytest.raises(m.ModelDeadlineExceeded):
            model.chat([])
        assert active == []
        with pytest.raises(m.ModelDeadlineExceeded):
            model.chat([])
    assert calls == [True]
    admission.release()
    m.admit(env[1], 1, config()).release()


def test_stale_http_deadline_rejects_before_transport():
    m = limits()
    calls = []

    async def respond(request):
        calls.append(True)
        return httpx.Response(200)

    with pytest.raises(m.ModelDeadlineExceeded):
        m.deadline_post("http://isolated/", {}, {}, 10,
                        deadline=time.monotonic() - 1, transport=httpx.MockTransport(respond))
    assert calls == []


def test_delayed_admission_commit_does_not_restart_deadline(env):
    from sqlalchemy import event

    from tests.auth.test_limits import config

    m = limits()

    def paused_factory():
        db = env[1]()
        event.listen(db, "before_commit", lambda _: time.sleep(0.08))
        return db

    with pytest.raises(m.ModelDeadlineExceeded):
        m.admit(paused_factory, 1, config(model_total_timeout_seconds=0.04))


def test_admission_preserves_deadline_captured_before_factory(env, monkeypatch):
    from tests.auth.test_limits import config

    m = limits()
    clock = [100.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: clock[0])

    def delayed_factory():
        clock[0] += 8
        return env[1]()

    admission = m.admit(delayed_factory, 1, config())
    assert admission.deadline == 160.0
    assert admission.remaining() == 52.0
    admission.factory = env[1]
    admission.release()


def test_transport_startup_delay_cannot_dispatch_after_lease_deadline(env, monkeypatch):
    from datetime import timedelta

    from sqlalchemy import update

    from app.auth.models import ModelBudget
    from app.llm_client import QwenModelClient
    from tests.auth.test_limits import config

    m = limits()
    admission = m.admit(env[1], 1, config())
    with env[1]() as db, db.begin():
        db.execute(update(ModelBudget).where(ModelBudget.key == "user:1").values(
            lease_expires_at=m.utcnow() + timedelta(seconds=1.4)
        ))
    original = m.deadline_post
    calls = []

    def delayed_post(*args, **kwargs):
        time.sleep(1.5)
        return original(*args, **kwargs)

    async def respond(request):
        calls.append(True)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(m, "deadline_post", delayed_post)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(m.ModelDeadlineExceeded):
            QwenModelClient("test-only", client).with_admission(admission).chat([])
    assert calls == []
    admission.release()
