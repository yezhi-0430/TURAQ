"""Run with uv run --no-project --with langfuse==5.0.4 python scripts/verify_langfuse_adapter.py.
All HTTP is intercepted; no server, credentials, or private material is used.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import langfuse  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,  # noqa: E402
)

from app.observability import LangfuseSink, sanitize  # noqa: E402

real = langfuse.Langfuse
spans = InMemorySpanExporter()
requests = []


def respond(request):
    requests.append(request)
    return httpx.Response(200, json={"successes": [], "errors": []})


http = httpx.Client(transport=httpx.MockTransport(respond))


def factory(**kwargs):
    return real(
        public_key="pk-lf-offline-test",
        secret_key="sk-lf-offline-test",
        base_url="https://example.invalid",
        httpx_client=http,
        tracer_provider=TracerProvider(),
        span_exporter=spans,
        **kwargs,
    )


langfuse.Langfuse = factory
sink = LangfuseSink()
sink(sanitize("model_attempt", dict(status="ok", usage={"prompt_tokens": 4})))
sink(sanitize("experiment", dict(status="completed", requested=7, passed=7, scored=7)))
sink.client.flush()
assert len(spans.get_finished_spans()) == 2
attrs = str([dict(s.attributes) for s in spans.get_finished_spans()])
assert "usage_details" in attrs and '"input": 4' in attrs
assert "cost_details" not in attrs
assert requests and all(r.url.host == "example.invalid" for r in requests)
assert "requested" in str([r.content for r in requests])
sink.client.shutdown()
http.close()
print("Langfuse 5.0.4 adapter: 2 local spans, usage preserved, scores accepted; HTTP mocked")
