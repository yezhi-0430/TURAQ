"""Frozen diagnostic comparison; optional one budgeted live run after a retrieval gate."""

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit

import httpx

from app.openviking_benchmark import (
    eligible,
    evidence_metrics,
    load_expanded,
    make_task,
    resources_for,
    summarize,
)
from app.openviking_gateway import ModelGate
from app.rag.hybrid import ALIASES, CONFIG, VERSION, HybridRetriever
from app.report_evidence_eval import score_answer
from app.report_fact_task import TASK_VERSION
from scripts.run_rag_repair_eval import BoundedChat, fingerprints, save

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluations/turaq/table-hybrid/results"
CODE = ("app/rag/table_chunks.py", "app/rag/hybrid.py", "scripts/run_table_hybrid_eval.py")


def frozen_fingerprints(corpus):
    result = fingerprints(corpus)
    for name in (
        "app/report_fact_task.py",
        "evaluations/turaq/rag-repair/results/rag-repair-2026-10-24-live-v1.json",
    ):
        result[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return result


def fragments_for(units):
    """Keep separated source spans separated; deduplicate repeated original headers."""
    fragments, seen = [], set()
    for unit in units:
        for part in unit["parts"]:
            key = (unit["resource_id"], part["char_start"], part["char_end"])
            if key not in seen:
                fragments.append(
                    dict(
                        part,
                        document_id=unit["document_id"],
                        page=unit["page"],
                        resource_id=unit["resource_id"],
                    )
                )
                seen.add(key)
    return fragments


def unit_evidence(gold, units):
    return dict(
        at1=evidence_metrics(gold, fragments_for(units[:1]))["at3"]
        if units
        else (False if gold["status"] == "supported" else None),
        at3=any(evidence_metrics(gold, fragments_for([unit]))["at3"] is True for unit in units[:3])
        if gold["status"] == "supported"
        else None,
    )


def audit_index(retriever, resources):
    originals = {r["id"]: r for r in resources}
    covered = {key: set() for key in originals}
    for unit in retriever.units:
        source = originals[unit["resource_id"]]["text"]
        if len(unit["body"]["text"]) > 500 or sum(len(p["text"]) for p in unit["headers"]) > 800:
            raise ValueError("source size limit")
        for part in [unit["body"], *unit["headers"]]:
            start, end = part["char_start"], part["char_end"]
            if not 0 <= start < end <= len(source) or part["text"] != source[start:end]:
                raise ValueError("source coordinate mismatch")
        body = unit["body"]
        covered[unit["resource_id"]].update(range(body["char_start"], body["char_end"]))
    if not all(
        all(i in covered[key] for i, c in enumerate(r["text"]) if not c.isspace())
        for key, r in originals.items()
    ):
        raise ValueError("source coverage lost")
    return dict(
        pages=len(resources),
        units=len(retriever.units),
        table_rows=sum(u["kind"] == "table_row" for u in retriever.units),
        source_spans_verified=True,
        non_whitespace_coverage=True,
    )


def offline(retriever, resources, corpus, report, path):
    report["retrieval"] = {}
    for mode in ("lexical", "hybrid"):
        rows = []
        for case in corpus["cases"]:
            row = dict(id=case["id"], units=[], error=None, evidence=dict(at1=None, at3=None))
            start = time.monotonic()
            try:
                allowed = {r["id"] for r in eligible(resources, case)}
                units = retriever.find(case["question"], allowed, mode=mode)
                if any(u["resource_id"] not in allowed for u in units):
                    raise ValueError("source scope violation")
                parts = fragments_for(units)
                row.update(
                    units=units,
                    evidence=unit_evidence(corpus["gold"][case["id"]], units),
                    visible_characters=sum(len(f["text"]) for f in parts),
                    visible_parts=len(parts),
                    eligible_resources=len(allowed),
                )
            except Exception as exc:
                row["error"] = type(exc).__name__
            row["retrieval_seconds"] = round(time.monotonic() - start, 4)
            rows.append(row)
        positives = [r for r in rows if corpus["gold"][r["id"]]["status"] == "supported"]
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
                median_retrieval_seconds=median(r["retrieval_seconds"] for r in positives),
                median_visible_characters=median(r.get("visible_characters", 0) for r in positives),
                max_visible_characters=max(r.get("visible_characters", 0) for r in rows),
                scope_boundaries_empty=all(
                    not r["units"] and not r["error"]
                    for r in rows
                    if not r.get("eligible_resources", 0)
                ),
            ),
        )
        save(path, report)
        print(mode + " retrieval: " + json.dumps(report["retrieval"][mode]["summary"]), flush=True)


def retrieval_gate(report):
    summary = report["retrieval"]["hybrid"]["summary"]
    return (
        summary["requested"] == summary["recorded"] == 20
        and not summary["errors"]
        and summary["evidence"]["at3"] >= 9
        and summary["scope_boundaries_empty"]
    )


def live_answers(corpus, report, path):
    from app.config import Settings

    settings = Settings()
    upstream = settings.model_base_url.rstrip("/")
    if (
        settings.model_provider != "qwen"
        or not settings.dashscope_api_key
        or urlsplit(upstream).scheme != "https"
        or urlsplit(upstream).hostname != "dashscope.aliyuncs.com"
    ):
        raise ValueError("existing DashScope HTTPS configuration required")
    key = settings.dashscope_api_key.get_secret_value()
    rows = []
    report["generation_model"] = settings.model_name
    with httpx.Client(trust_env=False, follow_redirects=False) as provider:

        def send(endpoint, payload, timeout):
            response = provider.post(
                upstream + endpoint,
                json=payload,
                timeout=timeout,
                headers={"Authorization": "Bearer " + key},
            )
            return response.status_code, response.json()

        gate = ModelGate(
            send, chat_model=settings.model_name, max_calls=24, max_chars=220000, seconds=480
        )
        model = BoundedChat(gate, settings.model_name)
        for case, retrieved in zip(
            corpus["cases"], report["retrieval"]["hybrid"]["rows"], strict=True
        ):
            row = dict(id=case["id"], scores={}, task_error=None, scoring_error=None)
            model.last_raw = None
            before = len(gate.records)
            try:
                row["output"] = make_task(model, case, corpus, fragments_for(retrieved["units"]))()
                try:
                    scores = score_answer(row["output"], case, corpus)
                    row["scores"] = dict(**scores, contract=all(scores.values()))
                except Exception as exc:
                    row["scoring_error"] = type(exc).__name__
            except Exception as exc:
                row["task_error"] = type(exc).__name__
            row.update(raw_model_proposal=model.last_raw, model_attempts=len(gate.records) - before)
            rows.append(row)
            report["answers"] = rows
            report["usage"] = gate.snapshot()
            save(path, report)
            print("Answered " + case["id"], flush=True)
    positives = [r for r in rows if corpus["gold"][r["id"]]["status"] == "supported"]
    boundaries = [r for r in rows if corpus["gold"][r["id"]]["status"] != "supported"]
    report["answer_summary"] = dict(
        all_cases=summarize(rows, [c["id"] for c in corpus["cases"]]),
        facts=summarize(positives, [r["id"] for r in positives]),
        boundaries=summarize(boundaries, [r["id"] for r in boundaries]),
        program_only_boundaries=sum(r["model_attempts"] == 0 for r in boundaries),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--live-if-ready", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,32}", args.run_id):
        raise SystemExit("invalid run id")
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"table-hybrid-2026-10-24-{args.run_id}.json"
    if path.exists():
        raise SystemExit("preserve existing results")
    corpus = load_expanded()
    frozen = frozen_fingerprints(corpus)
    report = dict(
        state="indexing",
        version=VERSION,
        task_version=TASK_VERSION,
        config=CONFIG,
        aliases=ALIASES,
        frozen_sha256=frozen,
        automatic_promotion=False,
        code_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CODE},
        scope="same 3 reports / 48 selected pages / 20 cases; known diagnostic set, not held out",
        model_evaluation_run=False,
        cost=None,
        budget=dict(max_calls=24, max_chars=220000, max_output_tokens=1024, seconds=480),
    )
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2))
    try:
        os.environ.update(
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
        )
        from app.rag.embeddings import get_embedding_service

        resources = resources_for(corpus)
        start = time.monotonic()
        retriever = HybridRetriever(resources, get_embedding_service())
        report["index_audit"] = audit_index(retriever, resources)
        report["index_setup_seconds"] = round(time.monotonic() - start, 3)
        offline(retriever, resources, corpus, report, path)
        report["retrieval_gate_passed"] = retrieval_gate(report)
        if args.live_if_ready and report["retrieval_gate_passed"]:
            report["model_evaluation_run"] = True
            live_answers(corpus, report, path)
        report["frozen_unchanged"] = frozen_fingerprints(load_expanded()) == frozen
        report["state"] = "completed" if report["frozen_unchanged"] else "invalid"
    except Exception as exc:
        report.update(state="incomplete", error_type=type(exc).__name__)
    save(path, report)
    print(
        json.dumps(
            dict(
                state=report["state"],
                gate=report.get("retrieval_gate_passed"),
                answers=report.get("answer_summary"),
            ),
            ensure_ascii=False,
        )
    )
    if report["state"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
