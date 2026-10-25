"""Bounded, content-log-free model gate for the independent OpenViking experiment."""

import json
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from secrets import token_urlsafe
from threading import Lock, Thread
from time import monotonic


class ModelGate:
    def __init__(
        self,
        send,
        *,
        chat_model,
        max_calls=60,
        max_chars=240000,
        seconds=1200,
        embedding_cache=None,
        save_cache=None,
    ):
        self.send = send
        self.chat_model = chat_model
        self.max_calls = max_calls
        self.max_chars = max_chars
        self.deadline = monotonic() + seconds
        self.lock = Lock()
        self.records = []
        self.chars = 0
        self.embedding_lock = Lock()
        self.embedding_cache = embedding_cache if embedding_cache is not None else {}
        self.save_cache = save_cache
        self.cache_hits = 0

    @staticmethod
    def error(status, code):
        return status, {"error": {"message": code, "type": "experiment_gate"}}

    def handle(self, path, raw):
        if path not in {"/v1/embeddings", "/v1/chat/completions"} or len(raw) > 128000:
            return self.error(400, "unsupported_request")
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get("stream"):
                raise ValueError
            if path.endswith("embeddings"):
                if payload.get("model") != "text-embedding-v4":
                    raise ValueError
                inputs = payload.get("input")
                inputs = [inputs] if isinstance(inputs, str) else inputs
                if not isinstance(inputs, list) or not 1 <= len(inputs) <= 10:
                    raise ValueError
                if not all(isinstance(x, str) and 0 < len(x) <= 16000 for x in inputs):
                    raise ValueError
                payload["dimensions"] = 1024
            else:
                if payload.get("model") != self.chat_model:
                    raise ValueError
                if not isinstance(payload.get("messages"), list):
                    raise ValueError
                requested = payload.get("max_tokens", 1024)
                if type(requested) is not int or requested < 1:
                    raise ValueError
                payload.pop("max_completion_tokens", None)
                payload["max_tokens"] = min(requested, 1024)
                payload["n"] = 1
            chars = len(json.dumps(payload, ensure_ascii=False))
        except (TypeError, ValueError, UnicodeError):
            return self.error(400, "invalid_request")
        if path.endswith("embeddings"):
            identity = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            with self.embedding_lock:
                if identity in self.embedding_cache:
                    with self.lock:
                        self.cache_hits += 1
                    result = deepcopy(self.embedding_cache[identity])
                    result["usage"] = dict(prompt_tokens=0, total_tokens=0)
                    return 200, result
                status, result = self._forward(path, payload, chars)
                if status == 200:
                    self.embedding_cache[identity] = deepcopy(result)
                    if self.save_cache:
                        self.save_cache(self.embedding_cache)
                return status, result
        return self._forward(path, payload, chars)

    def _forward(self, path, payload, chars):
        with self.lock:
            remaining = self.deadline - monotonic()
            if (
                remaining <= 0
                or len(self.records) >= self.max_calls
                or self.chars + chars > self.max_chars
            ):
                return self.error(429, "experiment_budget_exhausted")
            row = dict(
                kind="embedding" if path.endswith("embeddings") else "chat",
                status="pending",
                usage=None,
            )
            self.records.append(row)
            self.chars += chars
        start = monotonic()
        try:
            status, result = self.send(path.removeprefix("/v1"), payload, min(30, remaining))
            usage = result.get("usage") if isinstance(result, dict) else None
            if isinstance(usage, dict):
                row["usage"] = {
                    k: v
                    for k, v in usage.items()
                    if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                    and type(v) is int
                    and v >= 0
                }
            row["status"] = status
            if status != 200:
                return self.error(status, "provider_request_failed")
            return status, result
        except Exception:
            row["status"] = "transport_error"
            return self.error(502, "provider_transport_failed")
        finally:
            row["elapsed_seconds"] = round(monotonic() - start, 3)

    def snapshot(self):
        with self.lock:
            records = [dict(r) for r in self.records]
            chars = self.chars
        totals = [(r.get("usage") or {}).get("total_tokens") for r in records]
        return dict(
            attempts=len(records),
            request_chars=chars,
            total_tokens=sum(totals) if totals and all(v is not None for v in totals) else None,
            known_total_tokens=sum(v for v in totals if v is not None),
            unknown_usage_attempts=sum(v is None for v in totals),
            cache_hits=self.cache_hits,
            cost=None,
            records=records,
        )


@contextmanager
def serve_gate(gate):
    token = token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if not compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                status, data = gate.error(401, "unauthorized")
            else:
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 128000:
                        raise ValueError
                    self.connection.settimeout(5)
                    status, data = gate.handle(self.path, self.rfile.read(size))
                except (ValueError, TimeoutError):
                    status, data = gate.error(400, "invalid_body")
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", token
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
