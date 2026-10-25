from copy import deepcopy

import pytest

from app.research_eval import assess, run_suite


def test_frozen_suite_runs_offline_with_expected_denominator():
    report = run_suite()
    assert report["integrity_ok"]
    assert report["requested"] >= 7
    assert report["passed"] == report["requested"]
    assert report["mode"] == "scripted_mechanism_only"
    assert report["fingerprints"]["tool_schema"]
    assert report["cost"] is None


def test_missing_duplicate_and_missing_score_fail_closed():
    report = run_suite()
    rows = deepcopy(report["cases"])
    assert not assess(report["expected_ids"], rows[:-1])["integrity_ok"]
    assert not assess(report["expected_ids"], rows + rows[:1])["integrity_ok"]
    rows[0]["scores"] = {}
    checked = assess(report["expected_ids"], rows)
    assert not checked["integrity_ok"]
    assert checked["requested"] == report["requested"]
    assert checked["passed"] < checked["requested"]


def test_task_and_scorer_errors_remain_separate():
    def broken(_):
        raise RuntimeError("private failure")

    task = run_suite(task=broken)
    assert task["task_errors"] == task["requested"]
    assert task["scoring_errors"] == 0
    scoring = run_suite(scorer=lambda *_: broken(None))
    assert scoring["task_errors"] == 0
    assert scoring["scoring_errors"] == scoring["requested"]
    assert not scoring["integrity_ok"]


def test_gold_never_passed_to_task():
    seen = []

    def task(value):
        seen.append(value)
        return {}

    run_suite(task=task)
    assert seen and all("gold" not in value and "expected" not in value for value in seen)


def test_document_hash_tampering_rejected(tmp_path):
    import json
    from pathlib import Path

    source = Path("evaluations/turaq")
    for name in ("cases.json", "gold.json", "documents.json", "manifest.json"):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    docs = json.loads((tmp_path / "documents.json").read_text(encoding="utf-8"))
    docs[0]["pages"][0]["text"] += "changed"
    (tmp_path / "documents.json").write_text(json.dumps(docs), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        run_suite(root=tmp_path)


def test_scores_reject_wrong_security_period_and_source_in_evidence():
    import json
    from pathlib import Path

    from app.research_eval import score_output

    report = run_suite()
    row = next(r for r in report["cases"] if r["id"] == "security-period-source-v1")
    gold = json.loads(Path("evaluations/turaq/gold.json").read_text(encoding="utf-8"))[row["id"]]
    for field, wrong in (
        ("symbol", "999999.SZ"),
        ("report_period", "1900年度"),
        ("url", "https://example.invalid/wrong"),
    ):
        output = deepcopy(row["output"])
        output["snapshot"]["evidence"][0][field] = wrong
        assert score_output(output, gold) == {"contract": False}


def test_invalid_scorer_return_is_scoring_error():
    report = run_suite(scorer=lambda *_: None)
    assert not report["integrity_ok"]
    assert report["scoring_errors"] == report["requested"]


def test_empty_and_duplicate_expected_sets_cannot_pass():
    assert not assess([], [])["acceptance_ok"]
    assert not assess(["a", "a"], [{"id": "a", "scores": {"contract": True}}])["integrity_ok"]


def test_wrong_calculation_and_answer_do_not_pass():
    import json
    from pathlib import Path

    from app.research_eval import score_output

    report = run_suite()
    row = report["cases"][0]
    gold = json.loads(Path("evaluations/turaq/gold.json").read_text(encoding="utf-8"))[row["id"]]
    for field in ("result", "answer"):
        output = deepcopy(row["output"])
        if field == "result":
            output["audits"][0]["result"] = {"change_percent": "999.0000"}
        else:
            output["answer"] = "上涨999%"
        assert score_output(output, gold) == {"contract": False}


def test_document_text_and_summary_archive_tampering_do_not_pass():
    import json
    from pathlib import Path

    from app.research_eval import score_output

    row = next(r for r in run_suite()["cases"] if r["id"] == "full-document-lineage-v1")
    gold = json.loads(Path("evaluations/turaq/gold.json").read_text(encoding="utf-8"))[row["id"]]
    text = deepcopy(row["output"])
    text["documents"][0]["pages"][0]["text"] = "编造正文"
    for e in text["snapshot"]["evidence"]:
        if e["document_id"] == text["documents"][0]["document_id"] and e["page"] == 1:
            e["excerpt"] = "编造正文" if e["offset"] == 0 else ""
    assert score_output(text, gold) == {"contract": False}
    archive = deepcopy(row["output"])
    archive["snapshot"]["reading"]["batch_findings"][0]["summary"] = {"facts": ["篡改"]}
    assert score_output(archive, gold) == {"contract": False}


def test_wrong_page_offset_hash_or_batch_cursor_rejected():
    import json
    from pathlib import Path

    from app.research_eval import score_output

    row = next(r for r in run_suite()["cases"] if r["id"] == "full-document-lineage-v1")
    gold = json.loads(Path("evaluations/turaq/gold.json").read_text(encoding="utf-8"))[row["id"]]
    for key, wrong in (("page", 2), ("offset", 999999), ("content_hash", "wrong")):
        output = deepcopy(row["output"])
        output["snapshot"]["evidence"][0][key] = wrong
        assert score_output(output, gold) == {"contract": False}, key
    output = deepcopy(row["output"])
    output["snapshot"]["reading"]["batch_findings"][0]["cursor_after"]["offset"] = 999999
    assert score_output(output, gold) == {"contract": False}
