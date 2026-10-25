from copy import deepcopy

import httpx
import pytest

from app.openviking_pilot import allowed_resources, lexical_find, prepare_resources, resolve_hits
from app.report_evidence_eval import load_corpus


def test_public_page_resources_keep_exact_text_identity_without_gold():
    corpus = load_corpus()
    resources = prepare_resources(corpus, owner="pilot-a")
    assert len(resources) == 7
    for item in resources:
        doc = corpus["documents"][item["document_id"]]
        assert item["text"] == doc["text_pages"][item["page"] - 1]["text"]
        assert item["pdf_sha256"] == doc["pdf_sha256"]
        assert not {"gold", "answer", "expected", "citations"} & item.keys()


def test_owner_security_time_and_deleted_revision_are_fail_closed():
    resources = prepare_resources(load_corpus(), owner="pilot-a")
    assert not allowed_resources(resources, owner="pilot-b", symbol="600519.SH", as_of="2025-04-10")
    assert not allowed_resources(resources, owner="pilot-a", symbol="600519.SH", as_of="2024-01-01")
    copies = deepcopy(resources)
    for item in copies:
        item["active"] = False
    assert not allowed_resources(copies, owner="pilot-a", symbol="600519.SH", as_of="2025-04-10")
    found = allowed_resources(resources, owner="pilot-a", symbol="600519.SH", as_of="2025-04-10")
    assert len(found) == 3
    assert all(x["symbol"] == "600519.SH" for x in found)


def test_unbound_lookalike_and_inactive_uris_cannot_become_evidence():
    resources = prepare_resources(load_corpus(), owner="pilot-a")
    first = resources[0]
    uri = "viking://user/pilot-a/resources/pilot/page-a"
    bindings = {uri: first["id"]}
    hits = [
        {"uri": uri + "/content.md"},
        {"uri": uri + "-evil/content.md"},
        {"uri": "viking://user/pilot-b/resources/private"},
    ]
    assert resolve_hits(hits, bindings, [first]) == [first]
    assert resolve_hits(hits, bindings, []) == []
    assert resolve_hits(hits, bindings, [dict(first, active=False)]) == []


def test_lexical_baseline_uses_only_allowed_pages_and_fixed_top_k():
    resources = prepare_resources(load_corpus(), owner="pilot-a")
    allowed = allowed_resources(resources, owner="pilot-a", symbol="600519.SH", as_of="2025-04-10")
    found = lexical_find("营业收入 2024", allowed, limit=2)
    assert 0 < len(found) <= 2
    assert all(x["symbol"] == "600519.SH" for x in found)
    assert lexical_find("营业收入", [], limit=3) == []


def test_http_client_is_loopback_only_and_fails_closed_on_error_or_invalid_envelope():
    from app.openviking_pilot import PilotClient

    with pytest.raises(ValueError):
        PilotClient("https://example.com", "local-key")
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"status": "ok", "result": {"total": 0}})

    with PilotClient(
        "http://127.0.0.1:1933", "local-key", transport=httpx.MockTransport(respond)
    ) as client:
        assert client.call("POST", "/api/v1/search/find", json={"query": "收入"}) == {"total": 0}
    assert seen[0].headers["X-API-Key"] == "local-key"
    for response in (
        httpx.Response(503, text="private-debug-content"),
        httpx.Response(200, json={"status": "error"}),
    ):
        with PilotClient(
            "http://127.0.0.1:1933",
            "local-key",
            transport=httpx.MockTransport(lambda request, response=response: response),
        ) as client:
            with pytest.raises(RuntimeError) as exc:
                client.call("GET", "/api/v1/fs/ls")
            assert "private-debug-content" not in str(exc.value)


def test_retrieval_coverage_is_not_fact_accuracy_or_abstention_score():
    from app.openviking_pilot import retrieval_coverage

    resources = prepare_resources(load_corpus(), owner="pilot-a")
    corpus = load_corpus()
    gold = corpus["gold"]["moutai-revenue-2024"]
    assert retrieval_coverage(gold, resources) is True
    assert retrieval_coverage(gold, [r for r in resources if r["page"] == 1]) is False
    assert retrieval_coverage({"status": "insufficient"}, resources) is None
    assert retrieval_coverage(gold, [dict(r, text="伪造的页正文") for r in resources]) is False


def test_updated_backend_body_cannot_inherit_old_frozen_source_identity():
    from app.openviking_pilot import verify_content

    item = prepare_resources(load_corpus(), owner="pilot-a")[0]
    assert verify_content(item, "# 来源信息\n\n" + item["text"])
    assert not verify_content(item, "更正版本：原页面已撤回")
    assert not verify_content(dict(item, text="被改写的资料"), "被改写的资料")


def test_append_only_correction_is_detected_after_backend_digest_is_bound():
    from app.openviking_pilot import bind_content, verify_content

    item = prepare_resources(load_corpus(), owner="pilot-a")[0]
    imported = "# 来源信息\n\n" + item["text"]
    bound = bind_content(item, imported)
    assert bound["pdf_sha256"] == item["pdf_sha256"]
    assert "backend_body_sha256" in bound
    assert verify_content(bound, imported)
    assert not verify_content(bound, imported + "\n更正：原文已撤回")
    with pytest.raises(ValueError):
        bind_content(item, "不含原页的目录摘要")


def test_memory_is_searched_only_after_its_vector_queue_has_completed():
    from app.openviking_pilot import read_memory

    calls = []

    class Client:
        def call(self, method, path, **kwargs):
            calls.append(path)
            if path.endswith("/wait"):
                return {"Embedding": {"processed": 1, "error_count": 0}}
            if path.endswith("/find"):
                return {"memories": [{"uri": "viking://user/pilot-a/memories/preferences/test.md"}]}
            return "保持原表单位，核对报告期"

    result = read_memory(Client())
    assert calls == ["/api/v1/system/wait", "/api/v1/search/find", "/api/v1/content/read"]
    assert result["preference_found"] is True


def test_failed_memory_indexing_is_not_reported_as_a_successful_empty_search():
    from app.openviking_pilot import read_memory

    class Client:
        def call(self, *args, **kwargs):
            return {"Embedding": {"error_count": 1}}

    with pytest.raises(RuntimeError):
        read_memory(Client())
