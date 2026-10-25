"""Experiment orchestration only; reuse frozen live_answers without production changes."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from app.openviking_benchmark import eligible, make_task, resources_for
from app.pdf_cmap_validation import validate_registered_questions
from app.report_evidence_eval import load_corpus, read_json, score_answer
from app.unseen_report_validation import scope_boundaries_ok
from scripts.run_rag_repair_eval import save
from scripts.run_table_hybrid_eval import fragments_for, live_answers

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
OLD = ROOT / "evaluations/turaq/pdf-cmap-v2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unchanged(protocol):
    return all(sha(ROOT / name) == expected for name, expected in protocol["files"].items())


def group(name):
    corpus = load_corpus(OLD / name)
    report_path = OLD / "results" / f"{name}-2026-10-24-v1.json"
    report = read_json(report_path)
    assert report["state"] == "completed" and report["inputs_unchanged"]
    assert all(sha(ROOT / p) == h for p, h in report["inputs_sha256"].items())
    rows = report["retrieval"]["hybrid"]["rows"]
    assert [r["id"] for r in rows] == [c["id"] for c in corpus["cases"]]
    assert scope_boundaries_ok(rows, corpus["cases"])
    registration = read_json(OLD / "protocol.json")
    validate_registered_questions(
        corpus,
        registration["factual_specs"],
        {key: doc["symbol"] for key, doc in corpus["documents"].items()},
    )
    resources = resources_for(corpus)
    for case, row in zip(corpus["cases"], rows, strict=True):
        assert row["error"] is None
        allowed = {r["id"]: r for r in eligible(resources, case)}
        assert row["eligible_resources"] == len(allowed)
        for unit in row["units"]:
            source = allowed[unit["resource_id"]]
            assert (unit["document_id"], unit["page"]) == (
                source["document_id"], source["page"]
            )
            for part in unit["parts"]:
                a, b = part["char_start"], part["char_end"]
                assert type(a) is int and type(b) is int and 0 <= a < b <= len(source["text"])
                assert source["text"][a:b] == part["text"]
    return corpus, report, report_path


class Captured(Exception):
    pass


class CaptureOnly:
    def __init__(self, model):
        self.model, self.sizes = model, []

    def chat(self, messages):
        payload = dict(model=self.model, messages=messages, max_tokens=1024, n=1)
        self.sizes.append(len(json.dumps(payload, ensure_ascii=False)))
        raise Captured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    protocol = read_json(BASE / "protocol.json")
    assert unchanged(protocol), "frozen execution inputs changed"
    loaded = {name: group(name) for name in protocol["order"]}
    if not args.live:
        checks = {}
        for name, (corpus, report, _) in loaded.items():
            model, server = CaptureOnly(protocol["model"]), []
            for case, row in zip(corpus["cases"], report["retrieval"]["hybrid"]["rows"], strict=True):
                try:
                    output = make_task(model, case, corpus, fragments_for(row["units"]))()
                except Captured:
                    continue
                assert all(score_answer(output, case, corpus).values())
                server.append(case["id"])
            assert len(model.sizes) == protocol["groups"][name]["max_actual_calls"]
            assert sum(model.sizes) <= 220000
            checks[name] = dict(
                cases=len(corpus["cases"]), requests_captured_without_HTTP=len(model.sizes),
                expected_request_chars=sum(model.sizes), program_only_passed=server,
            )
        with (BASE / "preflight.json").open("x", encoding="utf-8") as handle:
            json.dump(checks, handle, ensure_ascii=False, indent=2)
        print(json.dumps(checks, ensure_ascii=False))
        return
    assert (BASE / "preflight.json").is_file(), "offline preflight required"
    assert all(not (BASE / f"{name}-live-v1.json").exists() for name in loaded)
    for name, (corpus, source_report, source_path) in loaded.items():
        assert unchanged(protocol), "inputs changed before group"
        path = BASE / f"{name}-live-v1.json"
        report = deepcopy(source_report)
        report.update(
            state="running_answers", model_evaluation_run=True, automatic_promotion=False,
            source_retrieval_result_sha256=sha(source_path),
            answer_protocol_sha256=sha(BASE / "protocol.json"),
            scope=protocol["groups"][name]["scope"],
        )
        with path.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        try:
            live_answers(corpus, report, path)
            report["frozen_execution_inputs_unchanged"] = unchanged(protocol)
            report["state"] = "completed" if unchanged(protocol) else "invalid"
        except Exception as exc:
            report.update(state="incomplete", error_type=type(exc).__name__)
        save(path, report)
        print(json.dumps(dict(group=name, state=report["state"], answers=report.get("answer_summary")), ensure_ascii=False), flush=True)
        if report["state"] != "completed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
