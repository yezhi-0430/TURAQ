"""Re-evaluate the repaired RAG in a fresh index; --live spends a bounded budget."""

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
    index_chroma,
    load_expanded,
    make_task,
    resources_for,
    summarize,
)
from app.openviking_gateway import ModelGate
from app.rag.scoring import relevant_results
from app.report_evidence_eval import score_answer
from app.report_fact_task import TASK_VERSION

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluations/turaq/rag-repair/results"
FROZEN = (
    "app/report_evidence_eval.py",
    "evaluations/turaq/public_reports/results/live-baseline-2026-10-23.json",
    "evaluations/turaq/openviking/expanded/results/comparison-2026-10-24-live-v5.json",
)


def fingerprints(corpus):
    files = [ROOT / name for name in FROZEN]
    files.extend(p for p in corpus["root"].rglob("*") if p.is_file() and "results" not in p.parts)
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(files)
    }


class RepairedComparator:
    """Same scoped top-three query, with genuine cosine and verified source slices."""

    def __init__(self, rag, resources):
        self.rag, self.resources = rag, resources
        self.last_raw = []

    def find(self, case):
        allowed = {r["id"]: r for r in eligible(self.resources, case)}
        self.last_raw = []
        if not allowed:
            return []
        result = self.rag.search(
            case["question"], n_results=3, filter_metadata={"resource_id": {"$in": list(allowed)}}
        )
        if not result.get("success"):
            raise RuntimeError("repaired retrieval failed")
        found = []
        accepted = relevant_results(result["results"])
        for row in result["results"]:
            meta = row.get("metadata", {})
            resource = allowed.get(meta.get("resource_id"))
            start, end = meta.get("char_start"), meta.get("char_end")
            if (
                resource is None
                or meta.get("chunker_version") != "source-slices-v2"
                or type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(resource["text"])
                or row["text"] != resource["text"][start:end]
            ):
                raise ValueError("retrieved source slice mismatch")
            fragment = dict(
                document_id=resource["document_id"],
                page=resource["page"],
                resource_id=resource["id"],
                text=row["text"],
                char_start=start,
                char_end=end,
                similarity=row.get("similarity"),
                distance=row.get("distance"),
            )
            self.last_raw.append(fragment)
            if row in accepted:
                found.append(fragment)
        return found


class BoundedChat:
    """Use the existing budget gate directly: no background server or retries."""

    def __init__(self, gate, model):
        self.gate, self.model, self.last_raw = gate, model, None

    def chat(self, messages):
        self.last_raw = None
        status, response = self.gate.handle(
            "/v1/chat/completions",
            json.dumps(
                dict(model=self.model, messages=messages, max_tokens=1024), ensure_ascii=False
            ).encode(),
        )
        if status != 200:
            raise RuntimeError("bounded gateway HTTP " + str(status))
        self.last_raw = response["choices"][0]["message"]["content"]
        return self.last_raw


def save(path, report):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def exercise(comparator, corpus, report, path, model=None):
    for case in corpus["cases"]:
        row = dict(
            id=case["id"],
            scores={},
            task_error=None,
            scoring_error=None,
            evidence=dict(at1=None, at3=None),
            fragments=[],
        )
        before = len(model.gate.records) if model else 0
        if model:
            model.last_raw = None
        start = time.monotonic()
        try:
            fragments = comparator.find(case)
            row.update(
                retrieval_seconds=round(time.monotonic() - start, 4),
                fragments=fragments,
                evidence=evidence_metrics(corpus["gold"][case["id"]], fragments),
                raw_evidence=evidence_metrics(corpus["gold"][case["id"]], comparator.last_raw),
            )
            if model:
                answer_start = time.monotonic()
                row["output"] = make_task(model, case, corpus, fragments)()
                row["answer_seconds"] = round(time.monotonic() - answer_start, 4)
                try:
                    scores = score_answer(row["output"], case, corpus)
                    row["scores"] = dict(**scores, contract=all(scores.values()))
                except Exception as exc:
                    row["scoring_error"] = type(exc).__name__
        except Exception as exc:
            row["task_error"] = type(exc).__name__
        row.setdefault("retrieval_seconds", round(time.monotonic() - start, 4))
        if model:
            row["raw_model_proposal"] = model.last_raw
            row["model_attempts"] = len(model.gate.records) - before
            report["usage"] = model.gate.snapshot()
        report["rows"].append(row)
        save(path, report)
        print("Evaluated " + case["id"], flush=True)
    positives = [r for r in report["rows"] if corpus["gold"][r["id"]]["status"] == "supported"]
    boundaries = [r for r in report["rows"] if corpus["gold"][r["id"]]["status"] != "supported"]
    report["summary"] = dict(
        evidence=dict(
            denominator=len(positives),
            at1=sum(r["evidence"]["at1"] is True for r in positives),
            at3=sum(r["evidence"]["at3"] is True for r in positives),
        ),
        median_retrieval_seconds=median(r["retrieval_seconds"] for r in positives),
        retrieval_errors=sum(bool(r["task_error"]) for r in report["rows"]) if not model else None,
    )
    if model:
        report["summary"].update(
            all_cases=summarize(report["rows"], [c["id"] for c in corpus["cases"]]),
            facts=summarize(positives, [r["id"] for r in positives]),
            boundaries=summarize(boundaries, [r["id"] for r in boundaries]),
            program_only_boundaries=sum(r["model_attempts"] == 0 for r in boundaries),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch("[a-z0-9-]{1,32}", args.run_id):
        raise SystemExit("invalid run id")
    path = RESULTS / f"rag-repair-2026-10-24-{args.run_id}.json"
    directory = ROOT / ".local-backups" / f"rag-repair-2026-10-24-{args.run_id}" / "chroma"
    if directory.exists() or path.exists():
        raise SystemExit("preserve the existing index and result; use a new run id")
    corpus = load_expanded()
    frozen = fingerprints(corpus)
    report = dict(
        state="indexing",
        live=args.live,
        automatic_promotion=False,
        task_version=TASK_VERSION,
        frozen_sha256=frozen,
        rows=[],
        cost=None,
        scope="3 reports, same 48 selected pages / 20 cases; not a blind full-report test",
        chunker_version="source-slices-v2",
        similarity_gate="actual cosine >= 0.5",
        budget=dict(max_calls=24, max_chars=220000, max_output_tokens=1024, seconds=480),
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    # Claim the result exclusively before constructing models or making paid calls.
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2))
    try:
        os.environ.update(
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
        )
        from app.rag.core import RAGSystem

        resources = resources_for(corpus)
        start = time.monotonic()
        rag = RAGSystem(persist_directory=str(directory), collection_name="repaired_benchmark")
        report["index"] = index_chroma(rag, resources)
        report["index_setup_seconds"] = round(time.monotonic() - start, 3)
        comparator = RepairedComparator(rag, resources)
        if args.live:
            from app.config import Settings

            settings = Settings()
            upstream = settings.model_base_url.rstrip("/")
            if (
                settings.model_provider != "qwen"
                or not settings.dashscope_api_key
                or urlsplit(upstream).scheme != "https"
                or urlsplit(upstream).hostname != "dashscope.aliyuncs.com"
            ):
                raise ValueError("existing DashScope HTTPS configuration is required")
            key = settings.dashscope_api_key.get_secret_value()
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
                    send,
                    chat_model=settings.model_name,
                    max_calls=24,
                    max_chars=220000,
                    seconds=480,
                )
                exercise(comparator, corpus, report, path, BoundedChat(gate, settings.model_name))
        else:
            exercise(comparator, corpus, report, path)
        report["frozen_unchanged"] = fingerprints(load_expanded()) == frozen
        report["state"] = "completed" if report["frozen_unchanged"] else "invalid"
    except Exception as exc:
        report.update(state="incomplete", error_type=type(exc).__name__)
    save(path, report)
    print(
        json.dumps(dict(state=report["state"], summary=report.get("summary")), ensure_ascii=False)
    )
    if report["state"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
