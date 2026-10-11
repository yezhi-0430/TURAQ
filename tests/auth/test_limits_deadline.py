"""A local slow response verifies cancellation closes work before lease release."""

import asyncio
import time

import httpx
import pytest

from tests.auth.test_limits import limits


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
