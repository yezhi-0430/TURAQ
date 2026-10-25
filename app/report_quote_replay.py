"""Replay cached live answers through the existing exact quotation locator, offline."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError

from app.document_citations import locate_fact_citations
from app.report_evidence_eval import (
    CORPUS,
    SCORER,
    FactAnswer,
    build_context,
    evaluate_answers,
    load_corpus,
    read_json,
)
from app.research_eval import assess, digest


def replay_report(parent, *, corpus=None):
    corpus = corpus or load_corpus()
    expected = [c["id"] for c in corpus["cases"]]
    fp = parent.get("fingerprints", {})
    grader = Path(__file__).with_name("report_evidence_eval.py")
    required = dict(
        corpus=digest(corpus["manifest"]),
        scorer=SCORER,
        scorer_code=hashlib.sha256(grader.read_bytes()).hexdigest(),
    )
    if parent.get("mode") != "live" or any(fp.get(k) != v for k, v in required.items()):
        raise ValueError("parent is not a compatible frozen live report")
    rows = parent.get("cases", [])
    if (
        parent.get("expected_ids") != expected
        or not isinstance(rows, list)
        or any(not isinstance(r, dict) or not isinstance(r.get("id"), str) for r in rows)
        or len(rows) != len(expected)
        or {r["id"] for r in rows} != set(expected)
    ):
        raise ValueError("parent case identity set is incomplete or duplicated")
    cases = {c["id"]: c for c in corpus["cases"]}
    answers, diagnostics = {}, []
    for row in rows:
        diag = dict(
            id=row["id"],
            parent_task_error=row.get("task_error"),
            parent_scoring_error=row.get("scoring_error"),
        )
        if "output" not in row:
            diagnostics.append(diag)
            continue
        answer = deepcopy(row["output"])
        original = deepcopy(answer)
        try:
            parsed = FactAnswer.model_validate(answer)
        except ValidationError:
            diag["state"] = "invalid_original_answer"
        else:
            if parsed.status == "supported":
                context = build_context(cases[row["id"]], corpus)
                excerpts = [
                    dict(
                        document_id=d["id"],
                        page=p["page"],
                        offset=0,
                        excerpt=p["text"],
                        content_hash=d["pdf_sha256"],
                        symbol=d["symbol"],
                        report_period=d["report_period"],
                        url=d["url"],
                    )
                    for d in context["documents"]
                    for p in d["pages"]
                ]
                summary = dict(
                    facts=[parsed.metric],
                    fact_citations=[
                        dict(fact_index=0, document_id=c.document_id, page=c.page, quote=c.quote)
                        for c in parsed.citations
                    ],
                )
                located = locate_fact_citations(summary, excerpts, batch=1)
                check = located["citation_checks"][0]
                if located["rejected_references"]:
                    check.update(
                        state="unresolved",
                        reasons=sorted(set(check["reasons"] + located["rejected_references"])),
                    )
                diag.update(state=check["state"], reasons=check["reasons"])
                if check["state"] == "quote_located":
                    locations = {
                        (link["document_id"], link["page"], link["quote"]): link
                        for link in check["links"]
                    }
                    for citation in answer["citations"]:
                        location = locations[
                            (citation["document_id"], citation["page"], citation["quote"])
                        ]
                        citation.update(start=location["start"], end=location["end"])
            else:
                diag["state"] = "abstention_unchanged"
        # Never edit a number, unit, quote, identity, period, status, or reason.
        if answer != original:
            assert {k: v for k, v in answer.items() if k != "citations"} == {
                k: v for k, v in original.items() if k != "citations"
            }
            for a, b in zip(
                answer.get("citations", []), original.get("citations", []), strict=True
            ):
                assert {k: v for k, v in a.items() if k not in {"start", "end"}} == {
                    k: v for k, v in b.items() if k not in {"start", "end"}
                }
        answers[row["id"]] = answer
        diagnostics.append(diag)
    report = evaluate_answers(answers, corpus=corpus, mode="cached_live_output_location_replay")
    original_errors = {r["id"]: r for r in rows}
    for row in report["cases"]:
        original = original_errors[row["id"]]
        if original.get("task_error") is not None or original.get("scoring_error") is not None:
            row.update(
                task_error=original.get("task_error"),
                scoring_error=original.get("scoring_error"),
                scores={},
            )
    report.update(assess(expected, report["cases"]))
    usage = parent.get("attempt_usage", [])
    attempts = parent.get("attempts")
    ledger_complete = (
        type(attempts) is int
        and attempts >= 0
        and isinstance(usage, list)
        and len(usage) == attempts
        and all(isinstance(a, dict) for a in usage)
    )
    totals = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [
            a["usage"].get(key) if isinstance(a.get("usage"), dict) else None
            for a in usage
        ] if ledger_complete else []
        totals[key] = (
            sum(values) if values and all(type(v) is int and v >= 0 for v in values) else None
        )
    report.update(
        real_model_quality="cached_live_outputs_not_new_model_run",
        additional_provider_calls=0,
        parent_usage=totals,
        parent_usage_ledger_complete=ledger_complete,
        parent_report_digest=digest(parent),
        diagnostics=diagnostics,
        adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        automatic_promotion=False,
        scope="same_cached_live_answers_exact_quotes_only; current strict grader unchanged",
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output == args.input.resolve() or (
        output.is_relative_to(CORPUS.resolve())
        and not output.is_relative_to((CORPUS / "results").resolve())
    ):
        parser.error("output must not overwrite the parent report or frozen corpus")
    report = replay_report(read_json(args.input))
    report["parent_file_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("requested", "passed", "additional_provider_calls")}))
    return 0 if report["acceptance_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
