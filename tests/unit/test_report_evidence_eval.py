import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.report_evidence_eval import build_context, evaluate_answers, load_corpus, score_answer

ROOT = Path("evaluations/turaq/public_reports")


def test_corpus_pdf_hashes_and_fixtures_are_valid():
    corpus = load_corpus()
    answers = json.loads((ROOT / "fixture_answers.json").read_text(encoding="utf-8"))
    report = evaluate_answers(answers, corpus=corpus, mode="fixture")
    assert report["requested"] == report["passed"] == 10
    assert report["integrity_ok"] and report["acceptance_ok"]
    assert report["real_model_quality"] == "not_run"
    assert report["mode"] == "fixture"


def test_gold_and_future_or_wrong_security_documents_not_in_context():
    corpus = load_corpus()
    for case in corpus["cases"]:
        context = build_context(case, corpus)
        assert "gold" not in context and "anchor" not in context
        for doc in context["documents"]:
            assert doc["symbol"] == case["symbol"]
            assert doc["published_date"] < case["as_of"]
            assert all(p["page"] in case["context_pages"][doc["id"]] for p in doc["pages"])
    assert build_context(corpus["cases"][-1], corpus)["documents"] == []
    assert build_context(corpus["cases"][-2], corpus)["documents"] == []


@pytest.mark.parametrize(
    "field,bad",
    [
        ("symbol", "999999.SZ"),
        ("period", "2023"),
        ("unit", "百万元"),
        ("value", "999"),
        ("metric", "其他指标"),
    ],
)
def test_wrong_identity_period_unit_or_number_fails(field, bad):
    corpus = load_corpus()
    case = corpus["cases"][0]
    answer = json.loads((ROOT / "fixture_answers.json").read_text(encoding="utf-8"))[case["id"]]
    answer[field] = bad
    assert not all(score_answer(answer, case, corpus).values())


@pytest.mark.parametrize(
    "field,bad",
    [
        ("page", 6),
        ("start", 99999),
        ("end", -1),
        ("quote", "伪原文"),
        ("document_id", "pingan-2024"),
    ],
)
def test_invalid_citation_fails(field, bad):
    corpus = load_corpus()
    case = corpus["cases"][0]
    answer = json.loads((ROOT / "fixture_answers.json").read_text(encoding="utf-8"))[case["id"]]
    answer["citations"][0][field] = bad
    assert score_answer(answer, case, corpus)["evidence"] is False


def test_insufficient_answer_cannot_invent_value_or_cite_hidden_material():
    corpus = load_corpus()
    case = corpus["cases"][-2]
    answer = dict(
        status="supported",
        symbol=case["symbol"],
        metric=case["metric"],
        period=case["period"],
        value="146695",
        unit="百万元",
        reason_code=None,
        citations=[dict(document_id="pingan-2024", page=16, start=0, end=1, quote="平")],
    )
    assert score_answer(answer, case, corpus)["abstention"] is False


def test_missing_extra_and_bad_answers_stay_in_denominator():
    corpus = load_corpus()
    answers = json.loads((ROOT / "fixture_answers.json").read_text(encoding="utf-8"))
    answers.pop(corpus["cases"][0]["id"])
    answers["unexpected"] = {}
    report = evaluate_answers(answers, corpus=corpus, mode="score")
    assert report["requested"] == 10 and report["task_errors"] == 1
    assert not report["integrity_ok"] and not report["acceptance_ok"]
    assert report["unexpected_ids"] == ["unexpected"]


def test_task_and_scoring_errors_are_distinct():
    corpus = load_corpus()

    def broken(*args):
        raise RuntimeError("private content")

    task = evaluate_answers({}, corpus=corpus, task=broken)
    assert task["task_errors"] == 10 and task["scoring_errors"] == 0
    scoring = evaluate_answers({}, corpus=corpus, task=lambda _: {}, scorer=broken)
    assert scoring["scoring_errors"] == 10 and scoring["task_errors"] == 0


def test_corpus_tampering_is_rejected(tmp_path):
    import shutil

    shutil.copytree(ROOT, tmp_path / "corpus")
    file = tmp_path / "corpus/sources/moutai-2024.pdf"
    file.write_bytes(b"%PDF-tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        load_corpus(tmp_path / "corpus")


def test_live_cli_needs_explicit_opt_in(tmp_path):
    from app.report_evidence_eval import main

    with pytest.raises(SystemExit):
        main(["--mode", "live", "--output", str(tmp_path / "out.json")])
    assert not (tmp_path / "out.json").exists()


def test_live_task_uses_only_public_context_and_records_provider_usage():
    import httpx

    from app.llm_client import QwenModelClient
    from app.report_evidence_eval import EvaluationBudget, live_task

    corpus = load_corpus()
    case = corpus["cases"][0]
    expected = json.loads((ROOT / "fixture_answers.json").read_text(encoding="utf-8"))[case["id"]]
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        assert "gold" not in body["messages"][1]["content"]
        assert "annotation" not in body["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "usage": {"prompt_tokens": 45, "completion_tokens": 20},
                "choices": [{"message": {"content": json.dumps(expected, ensure_ascii=False)}}],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        client = QwenModelClient("test-only", http)
        budget = EvaluationBudget(seconds=5, attempts=1)
        client.admission = budget
        output = live_task(client)(build_context(case, corpus))
    assert all(score_answer(output, case, corpus).values())
    assert budget.attempts == 1 and len(seen) == 1
    assert client.attempt_usage[0]["usage"]["completion_tokens"] == 20
    with pytest.raises(RuntimeError, match="attempt limit"):
        budget.before_attempt()
    budget.deadline = 0
    with pytest.raises(TimeoutError):
        budget.before_attempt()


def test_cli_cannot_overwrite_manifest(tmp_path, monkeypatch):
    import shutil

    from app import report_evidence_eval as module

    root = tmp_path / "corpus"
    shutil.copytree(ROOT, root)
    monkeypatch.setattr(module, "CORPUS", root)
    original = (root / "manifest.json").read_bytes()
    with pytest.raises(SystemExit):
        module.main(["--mode", "validate", "--output", str(root / "manifest.json")])
    assert (root / "manifest.json").read_bytes() == original


def test_valid_but_irrelevant_quote_and_missing_required_scores_fail():
    corpus = load_corpus()
    case = corpus["cases"][0]
    answer = json.loads((ROOT / "fixture_answers.json").read_text(encoding="utf-8"))[case["id"]]
    text = corpus["documents"]["moutai-2024"]["text_pages"][4]["text"]
    answer["citations"] = [dict(document_id="moutai-2024", page=5, start=0, end=2, quote=text[:2])]
    assert score_answer(answer, case, corpus)["evidence"] is False
    report = evaluate_answers(
        {}, corpus=corpus, task=lambda _: {}, scorer=lambda *_: {"value": True}
    )
    assert report["scoring_errors"] == 10 and not report["integrity_ok"]


def test_live_client_does_not_import_application_database(tmp_path):
    import subprocess
    import sys

    code = """
import sys,json,httpx
from app.llm_client import QwenModelClient
from app.report_evidence_eval import EvaluationBudget
transport=httpx.MockTransport(lambda r: httpx.Response(200,
    json={"choices":[{"message":{"content":"ok"}}]}))
with httpx.Client(transport=transport) as http:
    client=QwenModelClient("offline",http)
    client.admission=EvaluationBudget(seconds=5,attempts=1)
    assert client.chat([])=="ok"
assert "app.database" not in sys.modules
assert "app.model_limits" not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_alternative_correct_table_references_are_accepted():
    corpus = load_corpus()
    answers = json.loads((ROOT / "fixture_answers.json").read_text(encoding="utf-8"))
    for key, page, value, occurrence in [
        ("pingan-revenue-2024", 16, "146,695", 1),
        ("pingan-profit-2024", 17, "44,508", 0),
        ("pingan-npl-2024", 19, "1.06", 0),
    ]:
        case = next(c for c in corpus["cases"] if c["id"] == key)
        text = corpus["documents"]["pingan-2024"]["text_pages"][page - 1]["text"]
        positions = []
        index = text.find(value)
        while index >= 0:
            positions.append(index)
            index = text.find(value, index + len(value))
        start = positions[occurrence]
        answer = deepcopy(answers[key])
        answer["citations"] = [
            dict(
                document_id="pingan-2024",
                page=page,
                start=start,
                end=start + len(value),
                quote=value,
            )
        ]
        assert score_answer(answer, case, corpus)["evidence"], key


def test_live_task_keeps_invalid_raw_reply_for_local_review():
    from app.report_evidence_eval import live_task

    class BrokenJSON:
        def chat(self, messages):
            return "{invalid public model response"

    task = live_task(BrokenJSON())
    with pytest.raises(json.JSONDecodeError):
        task({"question": "public"})
    assert task.raw_responses[0]["raw_response"] == "{invalid public model response"
