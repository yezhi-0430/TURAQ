"""Offline retrieval only: known parse regression or predeclared fresh-issuer corpus."""

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

from app.document_parser import PARSER_VERSION
from app.openviking_benchmark import resources_for
from app.pdf_cmap_validation import validate_registered_questions
from app.rag.hybrid import HybridRetriever
from app.report_evidence_eval import load_corpus, read_json, score_answer
from scripts.run_rag_repair_eval import save
from scripts.run_table_hybrid_eval import audit_index
from scripts.run_unseen_report_eval import measure_retrieval

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evaluations/turaq/pdf-cmap-v2"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", choices=["regression", "fresh"], required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,32}", args.run_id):
        raise SystemExit("invalid run id")
    frozen_method = read_json(BASE / "method-freeze.json")
    for name, expected in frozen_method["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise SystemExit("method changed after freeze")
    corpus = load_corpus(BASE / args.corpus)
    registration = read_json(BASE / "protocol.json")
    if args.corpus == "fresh":
        issuer = registration["fresh_issuer"]
        identities = {issuer["id"]: issuer["symbol"]}
    else:
        original = load_corpus(ROOT / registration["known_corpus"])
        identities = {key: doc["symbol"] for key, doc in original["documents"].items()}
        if corpus["cases"] != original["cases"]:
            raise SystemExit("known regression questions changed")
    validate_registered_questions(corpus, registration["factual_specs"], identities)
    fixtures = read_json(corpus["root"] / "fixture_answers.json")
    if not all(all(score_answer(fixtures[c["id"]], c, corpus).values()) for c in corpus["cases"]):
        raise SystemExit("reference fixtures invalid")
    expected = 64 if args.corpus == "regression" else 32
    resources = resources_for(corpus)
    if len(resources) != expected or any(not 1 <= r["page"] <= 32 for r in resources):
        raise SystemExit("corpus outside fixed prefix")
    for doc in corpus["documents"].values():
        if any(
            p.get("extraction", {}).get("parser_version") != PARSER_VERSION
            for p in doc["text_pages"]
        ):
            raise SystemExit("unexpected extraction version")
    target = BASE / "results" / f"{args.corpus}-2026-10-24-{args.run_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    paths = [p for p in corpus["root"].rglob("*") if p.is_file()]
    paths += [BASE / "protocol.json", BASE / "method-freeze.json"]
    before = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }
    report = dict(
        state="indexing",
        corpus=args.corpus,
        parser_version=PARSER_VERSION,
        inputs_sha256=before,
        method=frozen_method,
        model_evaluation_run=False,
        scope="Known repair regression"
        if args.corpus == "regression"
        else "Fresh issuer after method freeze; same-author references; first32pages only",
        usage=dict(attempts=0, total_tokens=0, cost=None),
        automatic_promotion=False,
    )
    with target.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2))
    try:
        os.environ.update(
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
        )
        from app.rag.embeddings import get_embedding_service

        start = time.monotonic()
        retriever = HybridRetriever(resources, get_embedding_service())
        report["index_audit"] = audit_index(retriever, resources)
        report["index_setup_seconds"] = round(time.monotonic() - start, 3)
        measure_retrieval(retriever, resources, corpus, report, target)
        report["inputs_unchanged"] = all(
            hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == sha for p, sha in before.items()
        )
        report["method_unchanged"] = all(
            hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == sha
            for p, sha in frozen_method["files"].items()
        )
        report["state"] = (
            "completed" if report["inputs_unchanged"] and report["method_unchanged"] else "invalid"
        )
    except Exception as exc:
        report.update(state="incomplete", error_type=type(exc).__name__)
    save(target, report)
    print(
        json.dumps(
            dict(
                state=report["state"],
                summaries={
                    key: value["summary"] for key, value in report.get("retrieval", {}).items()
                },
            ),
            ensure_ascii=False,
        )
    )
    if report["state"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
