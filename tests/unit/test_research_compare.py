from copy import deepcopy

from app.research_compare import compare_reports
from app.research_eval import run_suite


def test_same_version_self_comparison_is_no_regression_not_improvement():
    report = run_suite()
    result = compare_reports(report, deepcopy(report))
    assert result["accepted"]
    assert result["decision"] == "no_mechanism_regression"
    assert result["improved"] == [] and result["regressed"] == []
    assert len(result["unchanged"]) == report["requested"]
    assert result["real_model_quality"] == "not_run"


def test_candidate_wrong_result_rejected_even_with_forged_success_scores():
    baseline = run_suite()
    bad = deepcopy(baseline)
    bad["cases"][0]["output"]["audits"][0]["result"]["change_percent"] = "999"
    result = compare_reports(baseline, bad)
    assert not result["accepted"]
    assert result["regressed"] == ["tool-calculate-v1"]
    assert "tool-calculate-v1" in result["score_mismatches"]["candidate"]


def test_missing_cases_and_scores_cannot_hide_behind_summary():
    baseline = run_suite()
    for mutation in ("missing_case", "duplicate", "missing_score", "task_error", "scoring_error"):
        bad = deepcopy(baseline)
        if mutation == "missing_case":
            bad["cases"].pop()
        elif mutation == "duplicate":
            bad["cases"].append(deepcopy(bad["cases"][0]))
        elif mutation == "missing_score":
            bad["cases"][0]["scores"] = {}
        else:
            bad["cases"][0][mutation] = "RuntimeError"
        result = compare_reports(baseline, bad)
        assert not result["accepted"], mutation
        assert result["candidate"]["requested"] == baseline["requested"]


def test_different_fixture_or_scorer_rejected_but_app_change_allowed():
    from app.research_eval import digest

    baseline = run_suite()
    for key in ("fixtures", "scorer_code", "scorer", "tool_schema", "prompts"):
        other = deepcopy(baseline)
        other["fingerprints"][key] = "different"
        assert not compare_reports(baseline, other)["compatible"], key
    other = deepcopy(baseline)
    other["fingerprints"]["source_files"]["app/candidate.py"] = "b" * 64
    other["fingerprints"]["app_sources"] = digest(other["fingerprints"]["source_files"])
    assert compare_reports(baseline, other)["accepted"]


def test_bad_baseline_or_empty_manifest_not_accepted():
    report = run_suite()
    assert not compare_reports({}, report)["accepted"]
    bad = deepcopy(report)
    bad["expected_ids"] = []
    assert not compare_reports(bad, bad)["accepted"]


def test_improvement_cannot_excuse_another_case_regression():
    import json
    from pathlib import Path

    from app.research_eval import score_output

    baseline = run_suite()
    candidate = deepcopy(baseline)
    baseline["cases"][0]["output"]["answer"] = "错误"
    gold = json.loads(Path("evaluations/turaq/gold.json").read_text(encoding="utf-8"))
    baseline["cases"][0]["scores"] = score_output(
        baseline["cases"][0]["output"], gold["tool-calculate-v1"]
    )
    candidate["cases"][1]["output"]["answer"] = "错误"
    candidate["cases"][1]["scores"] = score_output(
        candidate["cases"][1]["output"], gold["unknown-tool-recovery-v1"]
    )
    result = compare_reports(baseline, candidate)
    assert result["improved"] == ["tool-calculate-v1"]
    assert result["regressed"] == ["unknown-tool-recovery-v1"]
    assert not result["accepted"]


def test_malformed_rows_reject_without_crashing():
    baseline = run_suite()
    for rows in ([None], [{}], [{"id": [], "scores": {}}], "invalid", None):
        bad = deepcopy(baseline)
        bad["cases"] = rows
        assert not compare_reports(baseline, bad)["accepted"]


def test_missing_or_wrong_recovery_history_rejects_candidate():
    baseline = run_suite()
    for mutation in ("missing", "empty", "wrong_feedback"):
        bad = deepcopy(baseline)
        row = next(r for r in bad["cases"] if r["id"] == "unknown-tool-recovery-v1")
        if mutation == "missing":
            row["output"].pop("requests")
        elif mutation == "empty":
            row["output"]["requests"] = []
        else:
            for request in row["output"]["requests"]:
                request[:] = [m for m in request if m["role"] != "tool"]
        assert not compare_reports(baseline, bad)["accepted"], mutation
