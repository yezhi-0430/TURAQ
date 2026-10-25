"""Offline replay only: compare v1/v2 raw outcomes with the unchanged strict scorer."""

import hashlib
import json
import runpy
from pathlib import Path

from app.report_evidence_eval import read_json, score_answer
from app.report_evidence_task import EvidenceAnswer

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
PRIOR = ROOT / "evaluations/turaq/pdf-answer-acceptance-2026-10-25"
runner = runpy.run_path(str(BASE / "run.py"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Replay:
    def __init__(self, raw, model):
        self.raw, self.model, self.calls, self.chars = raw, model, 0, 0

    def chat(self, messages):
        assert self.raw is not None
        assert "allowed_anchors" not in messages[-1]["content"]
        self.calls += 1
        self.chars += len(
            json.dumps(
                dict(model=self.model, messages=messages, max_tokens=1024, n=1), ensure_ascii=False
            )
        )
        return self.raw


def main():
    protocol = read_json(BASE / "protocol.json")
    assert all(sha(ROOT / p) == h for p, h in protocol["files"].items())
    analysis = dict(
        task_version=protocol["version"],
        by_company={},
        groups={},
        failures=[],
        aggregate=dict(
            factual_requested=0,
            factual_passed=0,
            baseline_factual_passed=0,
            model_future_requested=0,
            model_future_passed=0,
            program_requested=0,
            program_passed=0,
            cases=0,
            strict_passed=0,
            scored=0,
            task_errors=0,
            attempts=0,
            request_chars=0,
            known_total_tokens=0,
            unknown_usage_attempts=0,
            monetary_cost=None,
        ),
        scope="Known repair set; no normalization, score changes or extra live calls",
    )
    total = analysis["aggregate"]
    for name in protocol["order"]:
        corpus, frozen, _ = runner["group"](name)
        path = BASE / f"{name}-live-v2.json"
        report, prior = read_json(path), read_json(PRIOR / f"{name}-live-v1.json")
        assert report["state"] == "completed" and report["candidate_inputs_unchanged"]
        assert report["candidate_protocol_sha256"] == sha(BASE / "protocol.json")
        assert report["generation_model"] == protocol["model"]
        assert report["retrieval"] == prior["retrieval"] == frozen["retrieval"]
        assert [r["id"] for r in report["answers"]] == [c["id"] for c in corpus["cases"]]
        request_chars = 0
        for case, row, previous, retrieved in zip(
            corpus["cases"],
            report["answers"],
            prior["answers"],
            report["retrieval"]["hybrid"]["rows"],
            strict=True,
        ):
            replay = Replay(row["raw_model_proposal"], protocol["model"])
            output = runner["answer"](replay, case, corpus, retrieved)
            assert output == row["output"] and replay.calls == row["model_attempts"]
            scores = score_answer(output, case, corpus)
            assert dict(**scores, contract=all(scores.values())) == row["scores"]
            assert row["task_error"] is None and row["scoring_error"] is None
            request_chars += replay.chars
            if replay.calls:
                proposal = EvidenceAnswer.model_validate_json(row["raw_model_proposal"])
                assert proposal.value == output["value"] and proposal.unit == output["unit"]
            for citation in output["citations"]:
                doc = corpus["documents"][citation["document_id"]]
                text = doc["text_pages"][citation["page"] - 1]["text"]
                assert text[citation["start"] : citation["end"]] == citation["quote"]
            passed = row["scores"]["contract"]
            total["cases"] += 1
            total["strict_passed"] += passed
            total["scored"] += 1
            if case["validation_kind"] == "fact":
                total["factual_requested"] += 1
                total["factual_passed"] += passed
                total["baseline_factual_passed"] += previous["scores"].get("contract") is True
                key = case["document_ids"][0]
                company = analysis["by_company"].setdefault(
                    key,
                    dict(
                        requested=0,
                        baseline_passed=0,
                        v2_passed=0,
                        dimensions=dict(identity=0, value=0, evidence=0, abstention=0),
                    ),
                )
                company["requested"] += 1
                company["baseline_passed"] += previous["scores"].get("contract") is True
                company["v2_passed"] += passed
                for dimension in company["dimensions"]:
                    company["dimensions"][dimension] += scores[dimension]
                if not passed:
                    analysis["failures"].append(
                        dict(
                            id=case["id"],
                            group=name,
                            scores=scores,
                            output=output,
                            expected={k: corpus["gold"][case["id"]][k] for k in ("value", "unit")},
                        )
                    )
            elif case["boundary_kind"] == "future_period":
                assert replay.calls == 1
                total["model_future_requested"] += 1
                total["model_future_passed"] += passed
            else:
                assert replay.calls == 0
                total["program_requested"] += 1
                total["program_passed"] += passed
        usage = report["usage"]
        assert request_chars == usage["request_chars"]
        assert usage["attempts"] <= protocol["groups"][name]["max_actual_calls"]
        assert all(r["status"] == 200 for r in usage["records"])
        for key in ("attempts", "request_chars", "known_total_tokens", "unknown_usage_attempts"):
            total[key] += usage[key]
        analysis["groups"][name] = dict(
            result_sha256=sha(path),
            summary=report["answer_summary"],
            usage={k: v for k, v in usage.items() if k != "records"},
            offline_replay_matches=True,
        )
    analysis["registered_files_unchanged"] = all(
        sha(ROOT / p) == h for p, h in protocol["files"].items()
    )
    analysis["automatic_promotion"] = False
    analysis["remaining_issue"] = (
        "CMB EPS unit 元/股 vs frozen元; value/citation correct, strict failure retained"
    )
    with (BASE / "analysis.json").open("x", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)
    print(json.dumps(dict(aggregate=total, by_company=analysis["by_company"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
