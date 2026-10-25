import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.report_evidence_eval import load_corpus
from app.report_fact_eval import evaluate_proposals, main

ROOT = Path("evaluations/turaq/public_reports")


def proposals():
    answers = json.loads((ROOT / "fixture_answers.json").read_text(encoding="utf-8"))
    corpus = load_corpus()
    for answer in answers.values():
        for citation in answer["citations"]:
            # Mechanism fixture only: old numeric-only fixture quotes can be ambiguous
            # without their original offsets. Supply the full original table row.
            text = corpus["documents"][citation["document_id"]]["text_pages"][citation["page"] - 1][
                "text"
            ]
            start, end = citation.pop("start"), citation.pop("end")
            if text.count(citation["quote"]) > 1:
                row_start = text.rfind("\n", 0, start) + 1
                row_end = text.find("\n", end)
                citation["quote"] = text[row_start : row_end if row_end >= 0 else len(text)]
    return answers


def test_offline_proposals_use_same_strict_scorer_with_no_quality_claim():
    report = evaluate_proposals(proposals())
    assert report["requested"] == report["passed"] == 10
    assert report["real_model_quality"] == "not_run"
    assert report["provider_calls"] == 0 and report["cost"] is None
    assert report["task_version"] == "quote-only-server-location-v1"
    assert len(report["raw_responses"]) == 8
    assert len(report["decisions"]) == 10
    assert sum(d["source"] == "server_exclusion_rule" for d in report["decisions"]) == 2


def test_bad_original_quote_still_fails_and_gold_does_not_affect_generation():
    answers = proposals()
    answers["moutai-profit-2024"]["citations"][0]["quote"] = "rewritten table quote"
    report = evaluate_proposals(answers)
    assert report["passed"] == 9 and not report["acceptance_ok"]
    corpus = load_corpus()
    corpus["gold"]["moutai-revenue-2024"]["value"] = "999"
    changed = evaluate_proposals(answers, corpus=corpus)
    assert [r["output"] for r in report["cases"]] == [r["output"] for r in changed["cases"]]
    assert changed["passed"] == 8


def test_missing_and_extra_proposals_cannot_hide_denominator_including_server_case():
    answers = proposals()
    answers.pop("wrong-security")
    answers["unexpected"] = {}
    report = evaluate_proposals(answers)
    assert report["requested"] == 10 and report["task_errors"] == 1
    assert report["unexpected_ids"] == ["unexpected"]
    assert not report["integrity_ok"] and not report["acceptance_ok"]


def test_cli_saves_offline_input_hash_and_rejects_all_overwrites(tmp_path):
    input_path = tmp_path / "proposals.json"
    input_path.write_text(json.dumps(proposals()), encoding="utf-8")
    output = tmp_path / "report.json"
    assert main(["--answers", str(input_path), "--output", str(output)]) == 0
    saved = output.read_bytes()
    report = json.loads(saved)
    assert report["input_sha256"] and report["execution_claim"] == "offline_proposals_only"
    for path in (output, input_path, ROOT / "new-frozen-file.json"):
        with pytest.raises(SystemExit):
            main(["--answers", str(input_path), "--output", str(path)])
    assert output.read_bytes() == saved
    assert not (ROOT / "new-frozen-file.json").exists()


def test_live_cli_requires_explicit_opt_in_and_valid_budget(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        main(["--mode", "live", "--output", str(tmp_path / "not-created.json")])
    assert not (tmp_path / "not-created.json").exists()
    for args in (["--seconds", "601"], ["--attempts", "0"]):
        with pytest.raises(SystemExit):
            main([*args, "--output", str(tmp_path / "not-created.json")])


def test_cli_live_uses_new_task_and_records_only_actual_calls(tmp_path, monkeypatch):
    import httpx

    from app import report_fact_eval as module
    from app.llm_client import QwenModelClient
    from app.report_evidence_eval import build_context
    from app.research_eval import digest

    corpus = load_corpus()
    answers = proposals()
    by_context = {
        digest(build_context(case, corpus)): answers[case["id"]] for case in corpus["cases"]
    }
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        context = json.loads(payload["messages"][1]["content"])
        assert "逐字" in payload["messages"][0]["content"]
        answer = deepcopy(by_context[digest(context)])
        return httpx.Response(
            200,
            json={
                "usage": dict(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                "choices": [dict(message=dict(content=json.dumps(answer, ensure_ascii=False)))],
            },
        )

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        module,
        "make_client",
        lambda key, http, model: QwenModelClient(
            key, httpx.Client(transport=transport), model_name=model
        ),
    )
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-not-real")
    output = tmp_path / "mock-live.json"
    assert (
        main(
            [
                "--mode",
                "live",
                "--allow-paid-model",
                "--model",
                "test-only",
                "--attempts",
                "8",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["attempts"] == len(report["attempt_usage"]) == len(requests) == 8
    assert report["model_requested"] == "test-only" and report["model_resolved"] is None
    assert len(report["decisions"]) == 10
