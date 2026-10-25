import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.report_quote_replay import replay_report

PARENT = Path("evaluations/turaq/public_reports/results/live-baseline-2026-10-23.json")


def parent():
    return json.loads(PARENT.read_text(encoding="utf-8"))


def test_captured_real_outputs_replay_without_provider_or_answer_edits():
    baseline = parent()
    before = deepcopy(baseline)
    result = replay_report(baseline)
    assert baseline == before
    assert result["requested"] == result["scored"] == 10
    assert result["passed"] == 8 and result["additional_provider_calls"] == 0
    assert result["real_model_quality"] == "cached_live_outputs_not_new_model_run"
    original = {r["id"]: r["output"] for r in baseline["cases"]}
    for row in result["cases"]:
        a, b = original[row["id"]], row["output"]
        assert {k: v for k, v in a.items() if k != "citations"} == {
            k: v for k, v in b.items() if k != "citations"
        }
        assert len(a["citations"]) == len(b["citations"])
        for old, new in zip(a["citations"], b["citations"], strict=True):
            assert all(old[k] == new[k] for k in ("document_id", "page", "quote"))


def test_nonexact_quote_and_wrong_abstention_reason_remain_failures():
    result = replay_report(parent())
    rows = {r["id"]: r for r in result["cases"]}
    assert not rows["moutai-profit-2024"]["scores"]["evidence"]
    assert not rows["wrong-security"]["scores"]["contract"]
    assert result["parent_usage"]["total_tokens"] == 28803
    assert result["cost"] is None


def test_incompatible_and_duplicate_parent_cases_fail_closed():
    baseline = parent()
    for key in ("corpus", "scorer", "scorer_code"):
        bad = deepcopy(baseline)
        bad["fingerprints"][key] = "different"
        with pytest.raises(ValueError):
            replay_report(bad)
    bad = deepcopy(baseline)
    bad["cases"].append(deepcopy(bad["cases"][0]))
    with pytest.raises(ValueError):
        replay_report(bad)


def test_gold_cannot_change_repaired_outputs():
    from app.report_evidence_eval import load_corpus

    a = replay_report(parent())
    corpus = load_corpus()
    corpus["gold"]["moutai-revenue-2024"]["value"] = "999"
    b = replay_report(parent(), corpus=corpus)
    assert [r["output"] for r in a["cases"]] == [r["output"] for r in b["cases"]]
    assert b["passed"] == 7


def test_parent_errors_and_missing_outputs_keep_full_denominator():
    baseline = parent()
    baseline["cases"][0].update(task_error="TimeoutError")
    baseline["cases"][0].pop("output")
    baseline["cases"][1].update(scoring_error="ValueError")
    result = replay_report(baseline)
    assert result["requested"] == 10
    assert result["scored"] == 8
    assert result["task_errors"] == result["scoring_errors"] == 1
    assert result["passed"] == 6
    assert not result["integrity_ok"] and not result["acceptance_ok"]
    baseline["cases"].pop()
    with pytest.raises(ValueError):
        replay_report(baseline)


def test_duplicate_citations_are_preserved_and_unknown_usage_stays_unknown():
    baseline = parent()
    citations = baseline["cases"][0]["output"]["citations"]
    citations.append(deepcopy(citations[0]))
    baseline["attempt_usage"][0]["usage"] = None
    result = replay_report(baseline)
    replayed = result["cases"][0]["output"]["citations"]
    assert len(replayed) == 2 and replayed[0] == replayed[1]
    assert result["parent_usage"]["total_tokens"] is None


def test_invalid_original_citation_is_preserved_as_failed_answer():
    baseline = parent()
    baseline["cases"][0]["output"]["citations"] = [123]
    result = replay_report(baseline)
    assert result["requested"] == 10 and result["passed"] == 7
    assert result["cases"][0]["output"]["citations"] == [123]
    assert result["diagnostics"][0]["state"] == "invalid_original_answer"


def test_cli_rejects_overwriting_parent_or_frozen_corpus(tmp_path):
    from app.report_quote_replay import CORPUS, main

    for output in (PARENT, CORPUS / "cases.json"):
        with pytest.raises(SystemExit) as exc:
            main(["--input", str(PARENT), "--output", str(output)])
        assert exc.value.code == 2
    output = tmp_path / "replay.json"
    assert main(["--input", str(PARENT), "--output", str(output)]) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] == 8


def test_locator_rejected_citation_keeps_entire_original_answer():
    baseline = parent()
    citations = baseline["cases"][0]["output"]["citations"]
    citations.append(dict(citations[0], quote="x" * 1001))
    result = replay_report(baseline)
    assert result["cases"][0]["output"] == baseline["cases"][0]["output"]
    assert result["diagnostics"][0]["state"] == "unresolved"
    assert "invalid_reference" in result["diagnostics"][0]["reasons"]


@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong_attempt_count"])
def test_incomplete_attempt_ledger_does_not_claim_known_total(mutation):
    baseline = parent()
    if mutation == "missing":
        baseline["attempt_usage"].pop()
    elif mutation == "extra":
        baseline["attempt_usage"].append(deepcopy(baseline["attempt_usage"][0]))
    else:
        baseline["attempts"] += 1
    result = replay_report(baseline)
    assert result["parent_usage"] == dict(
        prompt_tokens=None, completion_tokens=None, total_tokens=None
    )
