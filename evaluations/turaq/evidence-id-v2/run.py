"""One bounded v2 generation comparison on exactly the prior frozen source spans."""

import argparse
import hashlib
import json
import runpy
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.openviking_benchmark import make_task, summarize
from app.openviking_gateway import ModelGate
from app.report_evidence_eval import build_context, read_json, score_answer
from app.report_evidence_task import TASK_VERSION, evidence_task
from scripts.run_rag_repair_eval import BoundedChat, save
from scripts.run_table_hybrid_eval import fragments_for

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
PRIOR = ROOT / "evaluations/turaq/pdf-answer-acceptance-2026-10-25"
group = runpy.run_path(str(PRIOR / "run.py"))["group"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unchanged(protocol):
    return all(sha(ROOT / p) == h for p, h in protocol["files"].items())


def answer(client, case, corpus, retrieved):
    fragments = fragments_for(retrieved["units"])
    if not fragments:
        return make_task(client, case, corpus, [])()
    return evidence_task(client, build_context(case, corpus), fragments)


class Captured(Exception):
    pass


class CaptureOnly:
    def __init__(self, model):
        self.model, self.sizes = model, []

    def chat(self, messages):
        self.sizes.append(
            len(
                json.dumps(
                    dict(model=self.model, messages=messages, max_tokens=1024, n=1),
                    ensure_ascii=False,
                )
            )
        )
        raise Captured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    protocol = read_json(BASE / "protocol.json")
    assert unchanged(protocol), "registered method/input changed"
    loaded = {name: group(name) for name in protocol["order"]}
    if not args.live:
        checks = {}
        for name, (corpus, source, _) in loaded.items():
            client, server = CaptureOnly(protocol["model"]), []
            for case, row in zip(
                corpus["cases"], source["retrieval"]["hybrid"]["rows"], strict=True
            ):
                try:
                    output = answer(client, case, corpus, row)
                except Captured:
                    continue
                assert all(score_answer(output, case, corpus).values())
                server.append(case["id"])
            assert len(client.sizes) == protocol["groups"][name]["max_actual_calls"]
            assert sum(client.sizes) <= 220000
            checks[name] = dict(
                requests=len(client.sizes),
                request_chars=sum(client.sizes),
                program_only_passed=server,
            )
        with (BASE / "preflight.json").open("x", encoding="utf-8") as handle:
            json.dump(checks, handle, ensure_ascii=False, indent=2)
        print(json.dumps(checks, ensure_ascii=False))
        return
    assert (BASE / "preflight.json").is_file()
    assert all(not (BASE / f"{name}-live-v2.json").exists() for name in loaded)
    settings = Settings()
    upstream = settings.model_base_url.rstrip("/")
    if (
        not settings.model_enabled
        or settings.model_provider != "qwen"
        or settings.model_name != protocol["model"]
        or not settings.dashscope_api_key
        or urlsplit(upstream).scheme != "https"
        or urlsplit(upstream).hostname != "dashscope.aliyuncs.com"
    ):
        raise ValueError("registered existing enabled DashScope configuration required")
    key = settings.dashscope_api_key.get_secret_value()
    for name, (corpus, source, source_path) in loaded.items():
        assert unchanged(protocol)
        path = BASE / f"{name}-live-v2.json"
        report = deepcopy(source)
        report.update(
            state="running_answers",
            model_evaluation_run=True,
            automatic_promotion=False,
            task_version=TASK_VERSION,
            generation_model=settings.model_name,
            candidate_protocol_sha256=sha(BASE / "protocol.json"),
            source_retrieval_result_sha256=sha(source_path),
            scope="Known repair comparison after observing v1 errors; first32pages/report",
            answers=[],
        )
        with path.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
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
                corpus["cases"], source["retrieval"]["hybrid"]["rows"], strict=True
            ):
                row = dict(id=case["id"], scores={}, task_error=None, scoring_error=None)
                before, model.last_raw = len(gate.records), None
                try:
                    row["output"] = answer(model, case, corpus, retrieved)
                    try:
                        scores = score_answer(row["output"], case, corpus)
                        row["scores"] = dict(**scores, contract=all(scores.values()))
                    except Exception as exc:
                        row["scoring_error"] = type(exc).__name__
                except Exception as exc:
                    row["task_error"] = type(exc).__name__
                row.update(
                    raw_model_proposal=model.last_raw, model_attempts=len(gate.records) - before
                )
                report["answers"].append(row)
                report["usage"] = gate.snapshot()
                save(path, report)
                print("Answered " + case["id"], flush=True)
        facts = [r for r in report["answers"] if corpus["gold"][r["id"]]["status"] == "supported"]
        boundaries = [
            r for r in report["answers"] if corpus["gold"][r["id"]]["status"] != "supported"
        ]
        report["answer_summary"] = dict(
            all_cases=summarize(report["answers"], [c["id"] for c in corpus["cases"]]),
            facts=summarize(facts, [r["id"] for r in facts]),
            boundaries=summarize(boundaries, [r["id"] for r in boundaries]),
            program_only_boundaries=sum(r["model_attempts"] == 0 for r in boundaries),
        )
        report["candidate_inputs_unchanged"] = unchanged(protocol)
        report["state"] = "completed" if unchanged(protocol) else "invalid"
        save(path, report)
        print(
            json.dumps(
                dict(group=name, state=report["state"], summary=report["answer_summary"]),
                ensure_ascii=False,
            ),
            flush=True,
        )
        if report["state"] != "completed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
