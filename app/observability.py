"""Opt-in, bounded metadata export. No business content crosses this boundary."""

import os
from contextvars import ContextVar
from functools import wraps
from queue import Full, Queue
from threading import Thread
from time import monotonic, sleep
from uuid import uuid4

TRACE = ContextVar("turaq_trace", default=None)
KINDS = {"model_attempt", "agent_run", "experiment"}
STATUSES = {"ok", "error", "completed", "max_rounds_exceeded"}
TOKEN_KEYS = {"prompt_tokens", "completion_tokens", "total_tokens"}


def sanitize(kind, values):
    if kind not in KINDS:
        raise ValueError("unsupported trace kind")
    event = dict(kind=kind, event_id=uuid4().hex, trace_id=TRACE.get() or uuid4().hex)
    if values.get("status") in STATUSES:
        event["status"] = values["status"]
    for key in ("attempt", "rounds", "requested", "passed", "scored"):
        if type(values.get(key)) is int and 0 <= values[key] <= 1000000:
            event[key] = values[key]
    for key in ("app_fingerprint", "dataset_fingerprint", "scorer_fingerprint"):
        value = values.get(key)
        if (
            isinstance(value, str)
            and len(value) == 64
            and all(c in "0123456789abcdef" for c in value)
        ):
            event[key] = value
    if type(values.get("integrity_ok")) is bool:
        event["integrity_ok"] = values["integrity_ok"]
    raw = values.get("usage")
    event["usage"] = (
        ({k: v for k, v in raw.items() if k in TOKEN_KEYS and type(v) is int and v >= 0} or None)
        if isinstance(raw, dict)
        else None
    )
    event["cost"] = None
    return event


class Exporter:
    def __init__(self, sink, *, capacity=128):
        self.queue = Queue(maxsize=capacity)
        self.sink = sink
        self.dropped = 0
        self.failed = 0
        Thread(target=self._work, daemon=True, name="turaq-trace").start()

    def emit(self, kind, **values):
        event = sanitize(kind, values)
        try:
            self.queue.put_nowait(event)
        except Full:
            self.dropped += 1

    def _work(self):
        while True:
            event = self.queue.get()
            try:
                self.sink(event)
            except Exception:
                self.failed += 1
            finally:
                self.queue.task_done()

    def drain(self, timeout=2):
        """Explicit CLI/test helper only; never called by business requests."""
        end = monotonic() + timeout
        while self.queue.unfinished_tasks and monotonic() < end:
            sleep(0.005)
        return not self.queue.unfinished_tasks


class LangfuseSink:
    def __init__(self):
        self.client = None

    def __call__(self, event):
        if self.client is None:
            from langfuse import Langfuse

            self.client = Langfuse(timeout=2)
        kwargs = dict(
            name="turaq." + event["kind"],
            metadata=event,
            trace_context={"trace_id": event["trace_id"]},
        )
        if event["kind"] == "model_attempt":
            kwargs.update(as_type="generation")
            usage = event["usage"]
            if usage:
                kwargs["usage_details"] = {
                    {
                        "prompt_tokens": "input",
                        "completion_tokens": "output",
                        "total_tokens": "total",
                    }[k]: v
                    for k, v in usage.items()
                }
        observation = self.client.start_observation(**kwargs)
        if event["kind"] == "experiment":
            for name in ("requested", "passed", "scored"):
                if name in event:
                    observation.score(name=name, value=event[name])
        observation.end()
        if event["kind"] == "experiment":
            self.client.flush()


# Nothing is imported, connected, or queued unless explicitly enabled and configured.
_exporter = (
    Exporter(LangfuseSink())
    if os.getenv("TURAQ_TRACE_ENABLED") == "1"
    and all(
        os.getenv(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
    )
    else None
)


def emit(kind, **values):
    try:
        if _exporter is not None:
            _exporter.emit(kind, **values)
    except Exception:
        pass  # optional telemetry must never change admission, audit, or model behavior


def observed_run(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        token = TRACE.set(uuid4().hex)
        try:
            result = function(*args, **kwargs)
            emit("agent_run", status=result.status, rounds=result.rounds)
            return result
        except Exception:
            emit("agent_run", status="error")
            raise
        finally:
            TRACE.reset(token)

    return wrapped


def finish_cli_export(timeout=2):
    """Wait only at standalone CLI exit, including SDK flush in the worker."""
    if _exporter is None:
        return dict(enabled=False)
    drained = _exporter.drain(timeout)
    return dict(
        enabled=True,
        drained=drained,
        dropped=_exporter.dropped,
        failed=_exporter.failed,
        pending=_exporter.queue.unfinished_tasks,
    )
