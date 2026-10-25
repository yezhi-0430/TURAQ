"""One frozen first-transfer run. Paid answering is conditional and explicitly opt-in."""

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from statistics import median

from app.openviking_benchmark import eligible, resources_for
from app.rag.hybrid import ALIASES, CONFIG, VERSION, HybridRetriever
from app.unseen_report_validation import (
    load_transfer_corpus,
    located_unit_evidence,
    scope_boundaries_ok,
    transfer_gate,
)
from scripts.run_rag_repair_eval import save
from scripts.run_table_hybrid_eval import audit_index, fragments_for, live_answers, unit_evidence

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluations/turaq/unseen-reports/results"
HARNESS = ("app/unseen_report_validation.py", "scripts/run_unseen_report_eval.py")


def measure_retrieval(retriever, resources, corpus, report, path):
    """Use stricter position-aware metrics; historical substring metrics are diagnostic only."""
    report["retrieval"] = {}
    for mode in ("lexical", "hybrid"):
        rows = []
        for case in corpus["cases"]:
            start = time.monotonic()
            row = dict(
                id=case["id"],
                units=[],
                error=None,
                eligible_resources=0,
                evidence=dict(at1=None, at3=None),
            )
            try:
                allowed = {r["id"]: r for r in eligible(resources, case)}
                row["eligible_resources"] = len(allowed)
                units = retriever.find(case["question"], set(allowed), mode=mode)
                for unit in units:
                    source = allowed.get(unit["resource_id"])
                    if (
                        source is None
                        or source["document_id"] != unit["document_id"]
                        or source["page"] != unit["page"]
                    ):
                        raise ValueError("retrieved source outside authorized scope")
                    for part in unit["parts"]:
                        a, b = part["char_start"], part["char_end"]
                        if (
                            not 0 <= a < b <= len(source["text"])
                            or source["text"][a:b] != part["text"]
                        ):
                            raise ValueError("retrieved source coordinates mismatch")
                parts = fragments_for(units)
                row.update(
                    units=units,
                    evidence=located_unit_evidence(corpus["gold"][case["id"]], units),
                    substring_evidence=unit_evidence(corpus["gold"][case["id"]], units),
                    visible_characters=sum(len(p["text"]) for p in parts),
                    visible_parts=len(parts),
                )
            except Exception as exc:
                row["error"] = type(exc).__name__
            row["retrieval_seconds"] = round(time.monotonic() - start, 4)
            rows.append(row)
        positives = [r for r in rows if corpus["gold"][r["id"]]["status"] == "supported"]
        blocked = [r for r in rows if r["eligible_resources"] == 0]
        report["retrieval"][mode] = dict(
            rows=rows,
            summary=dict(
                requested=len(corpus["cases"]),
                recorded=len(rows),
                errors=sum(bool(r["error"]) for r in rows),
                evidence=dict(
                    denominator=len(positives),
                    at1=sum(r["evidence"]["at1"] is True for r in positives),
                    at3=sum(r["evidence"]["at3"] is True for r in positives),
                ),
                metric="located-source-span-v1",
                median_retrieval_seconds=median(r["retrieval_seconds"] for r in positives),
                median_visible_characters=median(r.get("visible_characters", 0) for r in positives),
                max_visible_characters=max(r.get("visible_characters", 0) for r in rows),
                scope_boundary_count=len(blocked),
                scope_boundaries_empty=scope_boundaries_ok(rows, corpus["cases"]),
            ),
        )
        save(path, report)
        print(mode + ": " + json.dumps(report["retrieval"][mode]["summary"]), flush=True)


def fingerprint(corpus, protocol):
    paths = [p for p in corpus["root"].rglob("*") if p.is_file() and "results" not in p.parts]
    paths.extend(
        ROOT / name for group in ("algorithm_sha256", "prior_sha256") for name in protocol[group]
    )
    paths.extend(ROOT / name for name in HARNESS)
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(set(paths))
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--live-if-ready", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,32}", args.run_id):
        raise SystemExit("invalid run id")
    corpus, protocol, counts = load_transfer_corpus()
    frozen = fingerprint(corpus, protocol)
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"unseen-reports-2026-10-24-{args.run_id}.json"
    report = dict(
        state="indexing",
        version=VERSION,
        config=CONFIG,
        aliases=ALIASES,
        frozen_sha256=frozen,
        registered_counts=counts,
        budget=protocol["limits"],
        scope=protocol["scope"],
        automatic_promotion=False,
        model_evaluation_run=False,
        retrieval_metric="located-source-span-v1",
        parsing_warning="CMB main-table labels are garbled; original extracted text retained",
        cost=None,
    )
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2))
    try:
        os.environ.update(
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
        )
        from app.rag.embeddings import get_embedding_service

        start = time.monotonic()
        resources = resources_for(corpus)
        retriever = HybridRetriever(resources, get_embedding_service())
        report["index_audit"] = audit_index(retriever, resources)
        report["index_setup_seconds"] = round(time.monotonic() - start, 3)
        measure_retrieval(retriever, resources, corpus, report, path)
        report["retrieval_gate_passed"] = transfer_gate(
            report["retrieval"]["hybrid"]["summary"], supported_count=counts["supported_facts"]
        )
        if args.live_if_ready and report["retrieval_gate_passed"]:
            report["model_evaluation_run"] = True
            live_answers(corpus, report, path)
        else:
            report["usage"] = dict(
                attempts=0,
                request_chars=0,
                total_tokens=0,
                known_total_tokens=0,
                unknown_usage_attempts=0,
                cost=None,
            )
        verified_corpus, verified_protocol, _ = load_transfer_corpus()
        report["frozen_unchanged"] = fingerprint(verified_corpus, verified_protocol) == frozen
        report["state"] = "completed" if report["frozen_unchanged"] else "invalid"
    except Exception as exc:
        report.update(state="incomplete", error_type=type(exc).__name__)
    save(path, report)
    print(
        json.dumps(
            dict(
                state=report["state"],
                gate=report.get("retrieval_gate_passed"),
                model_run=report["model_evaluation_run"],
                answers=report.get("answer_summary"),
            ),
            ensure_ascii=False,
        )
    )
    if report["state"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
