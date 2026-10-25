import json

import httpx

from app.openviking_gateway import ModelGate


def gate(**kwargs):
    calls = []

    def send(path, payload, timeout):
        calls.append((path, payload, timeout))
        return 200, {"usage": {"prompt_tokens": 7, "total_tokens": 9}}

    return ModelGate(send, chat_model="qwen-plus", **kwargs), calls


def body(**kwargs):
    return json.dumps(dict(model="qwen-plus", messages=[], **kwargs)).encode()


def test_unapproved_models_endpoints_and_stream_never_reach_provider():
    g, calls = gate()
    for path, raw in (
        ("/v1/models", body()),
        ("/v1/chat/completions", b'{"model":"other"}'),
        ("/v1/chat/completions", body(stream=True)),
    ):
        assert g.handle(path, raw)[0] == 400
    assert calls == []


def test_attempts_deadline_output_and_actual_usage_are_bounded():
    g, calls = gate(max_calls=1)
    assert g.handle("/v1/chat/completions", body(max_tokens=9000))[0] == 200
    assert calls[0][1]["max_tokens"] == 1024
    assert 0 < calls[0][2] <= 30
    assert g.handle("/v1/chat/completions", body())[0] == 429
    assert g.snapshot()["total_tokens"] == 9
    assert g.snapshot()["attempts"] == 1


def test_multiple_completions_cannot_multiply_per_request_output_budget():
    g, calls = gate()
    assert g.handle("/v1/chat/completions", body(n=8, max_tokens=1024))[0] == 200
    assert calls[0][1]["n"] == 1


def test_bad_json_character_budget_and_expired_run_fail_closed():
    g, calls = gate(max_chars=5)
    assert g.handle("/v1/chat/completions", b"bad")[0] == 400
    assert g.handle("/v1/chat/completions", body())[0] == 429
    assert not calls
    g, calls = gate(seconds=0)
    assert g.handle("/v1/chat/completions", body())[0] == 429


def test_network_failure_is_counted_without_exposing_exception_text():
    def broken(*args):
        raise RuntimeError("secret-provider-key")

    g = ModelGate(broken, chat_model="qwen-plus")
    status, result = g.handle("/v1/chat/completions", body())
    assert status == 502
    assert "secret-provider-key" not in json.dumps(result)
    assert g.snapshot()["attempts"] == 1
    assert g.snapshot()["total_tokens"] is None


def test_embedding_shape_and_dimension_are_fixed():
    g, calls = gate()
    raw = json.dumps(dict(model="text-embedding-v4", input=["公开财报"], dimensions=5)).encode()
    assert g.handle("/v1/embeddings", raw)[0] == 200
    assert calls[0][1]["dimensions"] == 1024
    assert g.handle("/v1/embeddings", b'{"model":"text-embedding-v4","input":[]}')[0] == 400


def test_local_server_auth_failure_does_not_consume_provider_budget():
    from app.openviking_gateway import serve_gate

    g, calls = gate()
    with serve_gate(g) as (url, key):
        with httpx.Client(trust_env=False) as client:
            assert client.post(url + "/chat/completions", content=body()).status_code == 401
            response = client.post(
                url + "/chat/completions",
                content=body(),
                headers={"Authorization": "Bearer " + key},
            )
            assert response.status_code == 200
    assert len(calls) == 1


def test_identical_embeddings_are_reused_without_counting_provider_usage_twice():
    g, calls = gate(max_calls=1)
    raw = b'{"model":"text-embedding-v4","input":["public page"]}'
    assert g.handle("/v1/embeddings", raw)[0] == 200
    status, cached = g.handle("/v1/embeddings", raw)
    assert status == 200
    assert cached["usage"]["total_tokens"] == 0
    assert len(calls) == 1
    assert g.snapshot()["total_tokens"] == 9
    assert g.snapshot()["cache_hits"] == 1


def test_concurrent_duplicate_embeddings_only_send_one_provider_attempt():
    from concurrent.futures import ThreadPoolExecutor

    g, calls = gate(max_calls=1)
    raw = b'{"model":"text-embedding-v4","input":["concurrent public page"]}'
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _: g.handle("/v1/embeddings", raw)[0], range(4)))
    assert statuses == [200] * 4
    assert len(calls) == 1
    assert g.snapshot()["cache_hits"] == 3
