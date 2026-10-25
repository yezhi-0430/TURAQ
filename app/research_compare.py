"""Re-score local mechanism reports before comparing a baseline with a candidate."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from app.research_eval import ROOT, SCORER_VERSION, assess, digest, load_fixtures, score_output
from app.tools.registry import tool_definitions


def check_report(report, expected, gold):
    if not isinstance(report, dict):
        report = {}
    rows = deepcopy(report.get("cases", []))
    if not isinstance(rows, list):
        rows = []
    declared = assess(expected, rows)
    mismatches = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] not in gold:
            continue
        if row.get("task_error") is not None or row.get("scoring_error") is not None:
            continue
        try:
            actual = score_output(row["output"], gold[row["id"]])
            if row.get("scores") != actual:
                mismatches.append(row["id"])
            row["scores"] = actual
        except (KeyError, TypeError, ValueError, IndexError, StopIteration, AttributeError):
            row["scores"] = {}
            row["scoring_error"] = "InvalidArtifact"
    checked = assess(expected, rows)
    checked["integrity_ok"] = (
        checked["integrity_ok"]
        and declared["integrity_ok"]
        and not mismatches
        and report.get("expected_ids") == expected
    )
    checked["acceptance_ok"] = checked["integrity_ok"] and checked["passed"] == len(expected)
    return checked, rows, mismatches


def compare_reports(baseline, candidate, *, root=None):
    manifest, cases, gold, _ = load_fixtures(root)
    expected = [c["id"] for c in cases]
    required = dict(
        fixtures=manifest,
        scorer=SCORER_VERSION,
        scorer_code=hashlib.sha256((ROOT / "app/research_eval.py").read_bytes()).hexdigest(),
        tool_schema=digest(tool_definitions()),
        prompts=digest([c["input"]["prompt"] for c in cases]),
    )
    compatibility_errors = []
    summaries, rows_by_side, mismatches = {}, {}, {}
    for side, report in (("baseline", baseline), ("candidate", candidate)):
        if not isinstance(report, dict):
            report = {}
        fp = report.get("fingerprints", {})
        if not isinstance(fp, dict):
            fp = {}
        for key, value in required.items():
            if fp.get(key) != value:
                compatibility_errors.append(f"{side}:{key}")
        sources = fp.get("source_files")
        if (
            not isinstance(sources, dict)
            or digest(sources) != fp.get("app_sources")
            or sources.get("app/research_eval.py") != fp.get("scorer_code")
        ):
            compatibility_errors.append(f"{side}:app_fingerprint")
        if report.get("mode") != "scripted_mechanism_only":
            compatibility_errors.append(f"{side}:mode")
        summaries[side], rows_by_side[side], mismatches[side] = check_report(report, expected, gold)

    def outcomes(rows):
        return {
            r["id"]: r.get("scores", {}).get("contract")
            for r in rows
            if isinstance(r, dict)
            and isinstance(r.get("id"), str)
            and isinstance(r.get("scores"), dict)
            and r.get("task_error") is None
            and r.get("scoring_error") is None
        }

    before, after = outcomes(rows_by_side["baseline"]), outcomes(rows_by_side["candidate"])
    improved, regressed, unchanged = [], [], []
    for case_id in expected:
        a, b = before.get(case_id), after.get(case_id)
        if type(a) is not bool or type(b) is not bool:
            continue
        if not a and b:
            improved.append(case_id)
        elif a and not b:
            regressed.append(case_id)
        else:
            unchanged.append(case_id)
    compatible = not compatibility_errors
    accepted = (
        compatible
        and summaries["baseline"]["integrity_ok"]
        and summaries["candidate"]["acceptance_ok"]
        and not regressed
    )
    decision = (
        ("mechanism_improved" if improved else "no_mechanism_regression") if accepted else "reject"
    )
    return dict(
        accepted=bool(accepted),
        decision=decision,
        compatible=compatible,
        compatibility_errors=compatibility_errors,
        score_mismatches=mismatches,
        baseline=summaries["baseline"],
        candidate=summaries["candidate"],
        improved=improved,
        regressed=regressed,
        unchanged=unchanged,
        real_model_quality="not_run",
        automatic_promotion=False,
        note="Local mechanism comparison; report execution authenticity is not attested.",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {args.baseline.resolve(), args.candidate.resolve()}:
        parser.error("output must not overwrite either input report")
    try:
        baseline, candidate = [
            json.loads(p.read_text(encoding="utf-8-sig")) for p in (args.baseline, args.candidate)
        ]
        report = compare_reports(baseline, candidate)
    except (ValueError, OSError, TypeError) as exc:
        report = dict(accepted=False, decision="reject", artifact_error=type(exc).__name__)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("accepted", "decision")}))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
