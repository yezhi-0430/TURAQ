"""Offline replay/audit of saved public proposals. Never calls a model or edits results."""

import hashlib
import json
from pathlib import Path

from app.openviking_benchmark import make_task, summarize
from app.report_evidence_eval import load_corpus, read_json, score_answer
from scripts.run_table_hybrid_eval import fragments_for

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
OLD = ROOT / "evaluations/turaq/pdf-cmap-v2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Replay:
    def __init__(self, raw):
        self.raw, self.calls = raw, 0

    def chat(self, messages):
        assert self.raw is not None
        assert "allowed_anchors" not in messages[-1]["content"]
        self.calls += 1
        return self.raw


def main():
    protocol = read_json(BASE / "protocol.json")
    assert all(sha(ROOT / p) == h for p, h in protocol["files"].items())
    analysis = dict(
        scope="Offline replay only; no schema/quote/value repair, score changes or retries",
        by_company={}, groups={}, failures=[],
        aggregate=dict(facts_requested=0, facts_scored=0, facts_passed=0, task_errors=0,
                       model_future_requested=0, model_future_passed=0,
                       program_boundaries_requested=0, program_boundaries_passed=0,
                       attempts=0, request_chars=0, known_total_tokens=0,
                       unknown_usage_attempts=0, cost=None),
    )
    aggregate = analysis["aggregate"]
    for name in protocol["order"]:
        corpus = load_corpus(OLD / name)
        path = BASE / f"{name}-live-v1.json"
        report = read_json(path)
        assert report["state"] == "completed" and report["frozen_execution_inputs_unchanged"]
        assert report["generation_model"] == protocol["model"]
        assert report["answer_protocol_sha256"] == sha(BASE / "protocol.json")
        assert [r["id"] for r in report["answers"]] == [c["id"] for c in corpus["cases"]]
        assert report["usage"]["attempts"] <= protocol["groups"][name]["max_actual_calls"]
        assert report["usage"]["request_chars"] <= 220000
        for key in ("attempts", "request_chars", "known_total_tokens", "unknown_usage_attempts"):
            aggregate[key] += report["usage"][key]
        assert all(r["status"] == 200 for r in report["usage"]["records"])
        replay_rows = []
        for case, row, retrieved in zip(corpus["cases"], report["answers"],
                                         report["retrieval"]["hybrid"]["rows"], strict=True):
            replay = Replay(row["raw_model_proposal"])
            replay_error, detail = None, None
            try:
                answer = make_task(replay, case, corpus, fragments_for(retrieved["units"]))()
            except Exception as exc:
                replay_error, detail = type(exc).__name__, str(exc)[:300]
            else:
                assert answer == row["output"]
                scores = score_answer(answer, case, corpus)
                assert dict(**scores, contract=all(scores.values())) == row["scores"]
            assert replay_error == row["task_error"] and replay.calls == row["model_attempts"]
            replay_rows.append(row)
            fact = case["validation_kind"] == "fact"
            passed = row["scores"].get("contract") is True
            if fact:
                aggregate["facts_requested"] += 1
                aggregate["facts_scored"] += bool(row["scores"])
                aggregate["facts_passed"] += passed
                aggregate["task_errors"] += bool(row["task_error"])
                doc = case["document_ids"][0]
                company = analysis["by_company"].setdefault(doc, dict(
                    requested=0, scored=0, passed=0, task_errors=0,
                    dimension_passed=dict(identity=0, value=0, evidence=0, abstention=0),
                ))
                company["requested"] += 1
                company["scored"] += bool(row["scores"])
                company["passed"] += passed
                company["task_errors"] += bool(row["task_error"])
                for key in company["dimension_passed"]:
                    company["dimension_passed"][key] += row["scores"].get(key) is True
                if not passed:
                    analysis["failures"].append(dict(
                        group=name, id=case["id"], metric=case["metric"],
                        period=case["period"], scores=row["scores"], replay_error=replay_error,
                        error_detail=detail,
                        expected={k: corpus["gold"][case["id"]][k] for k in ("value", "unit")},
                        output=row.get("output"),
                    ))
            else:
                kind = "model_future" if case["boundary_kind"] == "future_period" else "program_boundaries"
                assert replay.calls == (1 if kind == "model_future" else 0)
                aggregate[kind + "_requested"] += 1
                aggregate[kind + "_passed"] += passed
        assert summarize(replay_rows, [c["id"] for c in corpus["cases"]]) == report["answer_summary"]["all_cases"]
        analysis["groups"][name] = dict(
            raw_result_sha256=sha(path), summary=report["answer_summary"],
            usage={k: v for k, v in report["usage"].items() if k != "records"},
            provider_elapsed_seconds=sum(r["elapsed_seconds"] for r in report["usage"]["records"]),
            replay_matches_saved_results=True,
        )
    assert aggregate["facts_requested"] == 24
    assert aggregate["attempts"] <= 26 and aggregate["request_chars"] <= 440000
    analysis["all_registered_inputs_unchanged"] = all(
        sha(ROOT / p) == h for p, h in protocol["files"].items()
    )
    analysis["automatic_promotion"] = False
    analysis["readiness"] = "Not ready for automatic business adoption; strict format/quote failures retained"
    with (BASE / "analysis.json").open("x", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)
    print(json.dumps(dict(by_company=analysis["by_company"], aggregate=aggregate,
                          failures=[dict(id=r["id"], error=r["error_detail"]) for r in analysis["failures"]]), ensure_ascii=False))


if __name__ == "__main__":
    main()
