import base64
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def test_incomplete_data_has_no_safety_score_and_zero_is_present():
    from app.analysis.quality import analyze_pages

    result = analyze_pages([dict(page=1, text="营业收入 0\n净利润 0")], "公司", "a" * 64)
    assert result["indicators"]["revenue"] == 0
    assert result["quality"]["completeness"]["found"] == 2
    assert result["report"]["score"] is None
    assert any(c["status"] == "not_evaluable" for c in result["report"]["rule_checks"])
    assert result["quality"]["model"]["state"] == "not_run"
    assert not result["quality"]["model"]["available"]


def test_quote_locations_match_exact_page_and_do_not_claim_semantic_verification():
    from app.analysis.quality import analyze_pages

    pages = [dict(page=1, text="封面"), dict(page=2, text="营业收入 1,234.56\n净利润 25.0")]
    result = analyze_pages(pages, "公司", "a" * 64)
    refs = result["quality"]["citations"]
    assert refs["state"] == "located_unverified" and refs["located"] == 2
    for citation in refs["items"]:
        text = pages[citation["page"] - 1]["text"]
        assert text[citation["start"] : citation["end"]] == citation["quote"]
    assert result["indicators"]["revenue"] == 1234.56


def test_known_document_requires_exact_hash_and_demo_cannot_run_benchmark():
    from app.analysis.quality import analyze_pages, benchmark_for

    sha = "5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30"
    profile = benchmark_for(sha)
    assert profile["available"] and profile["case_count"] == 5
    assert not benchmark_for("a" * 64)["available"]
    result = analyze_pages([dict(page=1, text="营业收入 1")], "公司", sha, kind="demo")
    assert not result["quality"]["model"]["available"]


def make_client(monkeypatch):
    from app.analysis import api
    from app.auth.dependencies import Actor, require_actor

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_actor] = lambda: Actor(1, "test@example.invalid", False)
    return TestClient(app), app, api


def test_upload_failure_never_becomes_mock_success(monkeypatch):
    client, _, api = make_client(monkeypatch)

    def fail(_):
        raise ValueError("PDF文本提取失败")

    monkeypatch.setattr(api, "parse_pdf", fail)
    response = client.post(
        "/api/analysis/upload",
        json=dict(
            filename="bad.pdf",
            company_name="公司",
            content_base64=base64.b64encode(b"%PDF-invalid").decode(),
        ),
    )
    assert response.status_code == 422
    assert "indicators" not in response.json()


def test_upload_json_and_demo_have_separate_provenance(monkeypatch):
    client, _, api = make_client(monkeypatch)
    monkeypatch.setattr(api, "parse_pdf", lambda _: [dict(page=1, text="营业收入 0\n净利润 2")])
    result = client.post(
        "/api/analysis/upload",
        json=dict(
            filename="report.pdf",
            company_name="公司",
            content_base64=base64.b64encode(b"%PDF-test").decode(),
        ),
    ).json()
    assert result["source"]["kind"] == "uploaded" and result["source"]["page_count"] == 1
    demo = client.get("/api/analysis/test").json()
    assert demo["source"]["kind"] == "demo"
    assert not demo["quality"]["model"]["available"]


@pytest.mark.parametrize(
    "filename,content", [("fake.txt", "JVBERi0="), ("fake.pdf", "@@@@"), ("fake.pdf", "aGVsbG8=")]
)
def test_upload_rejects_invalid_pdf_before_parsing(filename, content, monkeypatch):
    client, _, api = make_client(monkeypatch)
    monkeypatch.setattr(api, "parse_pdf", lambda _: pytest.fail("must not parse invalid file"))
    response = client.post(
        "/api/analysis/upload",
        json=dict(
            filename=filename,
            content_base64=content,
            company_name="公司",
        ),
    )
    assert response.status_code == 422


def test_analysis_endpoints_require_authenticated_actor(monkeypatch):
    client, app, _ = make_client(monkeypatch)
    from app.auth.dependencies import require_actor

    def denied():
        raise HTTPException(401, "请先登录")

    app.dependency_overrides[require_actor] = denied
    assert client.get("/api/analysis/test").status_code == 401
    assert client.post("/api/analysis/upload", json={}).status_code == 401
    assert client.post("/api/analysis/evaluate", json={}).status_code == 401


def fixture_client():
    import json
    from pathlib import Path

    from app.report_evidence_eval import build_context, load_corpus
    from app.research_eval import digest

    corpus = load_corpus()
    answers = json.loads(
        Path("evaluations/turaq/quote_task/fixture-proposals.json").read_text("utf-8")
    )
    indexed = {digest(build_context(c, corpus)): answers[c["id"]] for c in corpus["cases"]}
    by_question = {
        (c["symbol"], c["metric"], c["period"], c["as_of"], c["question"]): c
        for c in corpus["cases"]
    }

    class Model:
        def chat(self, messages):
            payload = json.loads(messages[1]["content"])
            if "evidence" in payload:
                # This isolated fixture simulates a valid model selection; gold never
                # enters the application's request or its real generation adapter.
                case = by_question[
                    tuple(payload[k] for k in ("symbol", "metric", "period", "as_of", "question"))
                ]
                proposal = deepcopy(answers[case["id"]])
                proposal.pop("citations")
                proposal["evidence_ids"] = []
                if proposal["status"] == "supported":
                    for evidence in payload["evidence"]:
                        source = corpus["documents"][evidence["document_id"]]["text_pages"]
                        text = source[evidence["page"] - 1]["text"]
                        start = text.find(evidence["text"])
                        if any(
                            evidence["document_id"] == a["document_id"]
                            and evidence["page"] == a["page"]
                            and start <= a["start"] < a["end"] <= start + len(evidence["text"])
                            for a in corpus["gold"][case["id"]]["allowed_anchors"]
                        ):
                            proposal["evidence_ids"] = [evidence["id"]]
                            break
                return json.dumps(proposal, ensure_ascii=False)
            context_hash = digest(payload)
            return json.dumps(deepcopy(indexed[context_hash]))

    return Model()


def test_benchmark_uses_strict_scorer_same_trace_and_no_prompt_or_gold_export(monkeypatch):
    from app import observability
    from app.analysis.evaluation import evaluate_document

    events = []
    monkeypatch.setattr(
        observability,
        "emit",
        lambda kind, **kw: events.append((kind, kw, observability.TRACE.get())),
    )
    admission = SimpleNamespace(
        settings=SimpleNamespace(model_provider="qwen"),
        remaining=lambda: 30,
        model_attempt_usage=[],
    )
    result = evaluate_document(
        "5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30",
        fixture_client(),
        admission,
    )
    assert result["requested"] == result["passed"] == 5
    assert result["scorer_version"] == "public-fact-citation-v1"
    assert len({e[2] for e in events}) == 1 and events[0][2] == result["trace_id"]
    assert "gold" not in str(events) and "raw_response" not in str(events)
    assert result["cost"] is None and result["usage"]["total_tokens"] is None
    assert observability.TRACE.get() is None


def test_benchmark_errors_stay_in_denominator_and_fake_mode_not_quality():
    from app.analysis.evaluation import evaluate_document

    class Broken:
        def chat(self, _):
            raise RuntimeError("private exception")

    admission = SimpleNamespace(
        settings=SimpleNamespace(model_provider="qwen"),
        remaining=lambda: 30,
        model_attempt_usage=[],
    )
    sha = "5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30"
    result = evaluate_document(sha, Broken(), admission)
    assert result["requested"] == result["task_errors"] == 5
    assert not result["integrity_ok"] and result["passed"] == 0
    assert "private exception" not in str(result)
    admission.settings.model_provider = "fake"
    with pytest.raises(ValueError, match="真实模型"):
        evaluate_document(sha, Broken(), admission)


def test_evaluate_endpoint_uses_shared_admission_and_model_dependencies(monkeypatch):
    client, app, api = make_client(monkeypatch)
    admission = SimpleNamespace(
        settings=SimpleNamespace(model_provider="qwen"),
        remaining=lambda: 30,
        model_attempt_usage=[],
    )
    released = []

    def admitted():
        try:
            yield admission
        finally:
            released.append(True)

    app.dependency_overrides[api.model_admission] = admitted
    app.dependency_overrides[api.get_model_client] = fixture_client
    response = client.post(
        "/api/analysis/evaluate",
        json=dict(
            source_sha256="5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30",
        ),
    )
    assert response.status_code == 200 and response.json()["passed"] == 5
    assert released == [True]
    response = client.post("/api/analysis/evaluate", json=dict(source_sha256="a" * 64))
    assert response.status_code == 422 and released == [True, True]


def test_model_rate_limit_blocks_evaluation_before_any_provider_call(monkeypatch):
    client, app, api = make_client(monkeypatch)

    def denied():
        raise HTTPException(429, "模型额度已满")

    app.dependency_overrides[api.model_admission] = denied
    app.dependency_overrides[api.get_model_client] = lambda: pytest.fail("must not create model")
    assert (
        client.post(
            "/api/analysis/evaluate",
            json=dict(
                source_sha256="5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30",
            ),
        ).status_code
        == 429
    )


@pytest.mark.parametrize("kind,status", [("quota", 429), ("unavailable", 503), ("deadline", 504)])
def test_runtime_limits_keep_http_status_partial_denominator_and_stop_more_calls(
    kind, status, monkeypatch
):
    from app.model_limits import LimitsUnavailable, ModelDeadlineExceeded, RateLimited

    client, app, api = make_client(monkeypatch)
    error = {
        "quota": RateLimited(17),
        "unavailable": LimitsUnavailable("private exception"),
        "deadline": ModelDeadlineExceeded("private exception"),
    }[kind]
    calls = []

    class Failed:
        def chat(self, messages):
            calls.append(True)
            raise error

    admission = SimpleNamespace(
        settings=SimpleNamespace(model_provider="qwen"),
        remaining=lambda: 30,
        model_attempt_usage=[],
    )
    app.dependency_overrides[api.model_admission] = lambda: admission
    app.dependency_overrides[api.get_model_client] = Failed
    response = client.post(
        "/api/analysis/evaluate",
        json=dict(
            source_sha256="5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30",
        ),
    )
    assert response.status_code == status
    partial = response.json()["partial"]
    assert partial["requested"] == partial["task_errors"] == 5
    assert not partial["integrity_ok"] and len(calls) == 1
    assert "private exception" not in response.text
    if kind == "quota":
        assert response.headers["Retry-After"] == "17"
