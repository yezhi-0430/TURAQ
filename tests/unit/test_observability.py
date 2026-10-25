import threading
import time

import httpx

from app.llm_client import QwenModelClient


def test_usage_includes_retry_unknown_and_provider_tokens():
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(
            200,
            json={
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                "choices": [{"message": {"content": "ok"}}],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        client = QwenModelClient("dummy", http)
        reply = client.chat_with_tools([], [])
    assert reply.usage == {"prompt_tokens": 12, "completion_tokens": 3}
    assert len(client.attempt_usage) == 2
    assert client.attempt_usage[0]["usage"] is None
    assert client.attempt_usage[1]["usage"] == reply.usage
    assert all(a["cost"] is None for a in client.attempt_usage)


def test_truncated_response_keeps_usage():
    import pytest

    from app.llm_client import ModelOutputTruncatedError

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "usage": {"total_tokens": 7},
                    "choices": [{"finish_reason": "length", "message": {"content": "partial"}}],
                },
            )
        )
    ) as http:
        client = QwenModelClient("dummy", http)
        with pytest.raises(ModelOutputTruncatedError):
            client.chat([])
    assert client.attempt_usage[0]["usage"] == {"total_tokens": 7}


def test_tracing_is_nonblocking_bounded_and_strips_private_values():
    from app.observability import Exporter

    entered = threading.Event()
    release = threading.Event()
    received = []

    def blocked(event):
        received.append(event)
        entered.set()
        release.wait(2)

    exporter = Exporter(blocked, capacity=1)
    start = time.monotonic()
    exporter.emit(
        "model_attempt",
        status="ok",
        usage={"prompt_tokens": 4, "secret": "private"},
        prompt="private",
        user_id="private",
        model="private",
    )
    assert entered.wait(1)
    for _ in range(20):
        exporter.emit("model_attempt", status="ok")
    assert time.monotonic() - start < 1
    assert exporter.dropped > 0
    assert "private" not in str(received)
    release.set()
    assert exporter.drain(2)


def test_export_failure_does_not_escape_or_stop_worker():
    from app.observability import Exporter

    exporter = Exporter(lambda event: 1 / 0)
    exporter.emit("agent_run", status="completed")
    assert exporter.drain(2)
    assert exporter.failed == 1


def test_run_errors_and_trace_failure_keep_local_audit_and_deadline(monkeypatch):
    import pytest

    from app import observability
    from app.agent_loop import run_agent_loop
    from app.llm_types import ToolReply

    events = []

    class Capture:
        def emit(self, kind, **values):
            events.append((kind, values, observability.TRACE.get()))
            raise RuntimeError("export failure")

    monkeypatch.setattr(observability, "_exporter", Capture())

    class Model:
        def chat_with_tools(self, messages, tools):
            return ToolReply.model_validate(
                {
                    "tool_calls": [
                        {
                            "id": "a",
                            "type": "function",
                            "function": {
                                "name": "calculate_change",
                                "arguments": '{"previous_close":"10", "current_close":"9"}',
                            },
                        }
                    ]
                }
            )

    audits = []
    result = run_agent_loop(
        Model(), [], max_rounds=1, audit_writer=lambda run, record: audits.append(record)
    )
    assert result.status == "max_rounds_exceeded" and len(audits) == 1
    assert events[-1][2] is not None
    assert observability.TRACE.get() is None

    def expired():
        raise TimeoutError("deadline")

    with pytest.raises(TimeoutError):
        run_agent_loop(Model(), [], check_deadline=expired)
    assert events[-1][1]["status"] == "error"
    assert observability.TRACE.get() is None


def test_document_chat_usage_survives_temporary_bound_clients():
    from tests.unit.admission import offline_admission

    admitted = offline_admission()
    admitted.before_attempt = lambda: 2.0
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={"usage": {"total_tokens": 7}, "choices": [{"message": {"content": "ok"}}]},
            )
        )
    ) as http:
        client = QwenModelClient("dummy", http)
        for _ in range(2):
            assert client.with_admission(admitted, purpose="risk_document").chat([]) == "ok"
    assert len(admitted.model_attempt_usage) == 2
    other = offline_admission()
    bound = client.with_admission(other, purpose="risk_document")
    assert bound.attempt_usage is not admitted.model_attempt_usage
    assert len(other.model_attempt_usage) == 0
    assert all(r["usage"] == {"total_tokens": 7} for r in admitted.model_attempt_usage)


def test_cli_export_wait_is_bounded_and_reports_pending(monkeypatch):
    from app import observability

    entered = threading.Event()
    release = threading.Event()

    def blocked(event):
        entered.set()
        release.wait(2)

    exporter = observability.Exporter(blocked)
    monkeypatch.setattr(observability, "_exporter", exporter)
    exporter.emit("experiment", status="completed")
    assert entered.wait(1)
    start = time.monotonic()
    result = observability.finish_cli_export(timeout=0.02)
    assert time.monotonic() - start < 0.5
    assert result["drained"] is False and result["pending"] == 1
    release.set()
    assert exporter.drain(2)
