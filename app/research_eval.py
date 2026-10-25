"""Offline mechanism evaluation. Gold is held only by the scoring side."""

import argparse
import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SCORES = {"contract"}
SCORER_VERSION = "contract-v2"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def assess(expected, rows):
    expected_valid = (
        isinstance(expected, list)
        and bool(expected)
        and all(isinstance(i, str) and bool(i) for i in expected)
        and len(set(expected)) == len(expected)
    )
    expected = expected if isinstance(expected, list) else []
    rows_valid = isinstance(rows, list) and all(
        isinstance(r, dict)
        and isinstance(r.get("id"), str)
        and {"scores", "task_error", "scoring_error"} <= r.keys()
        for r in rows
    )
    rows = rows if isinstance(rows, list) else []
    usable = [r for r in rows if isinstance(r, dict) and isinstance(r.get("id"), str)]
    ids = [r["id"] for r in usable]
    complete = (
        expected_valid and rows_valid and len(ids) == len(set(ids)) and set(ids) == set(expected)
    )
    valid = [r for r in usable if r["id"] in expected and ids.count(r["id"]) == 1]
    scored = [
        r
        for r in valid
        if isinstance(r.get("scores"), dict)
        and REQUIRED_SCORES <= r["scores"].keys()
        and all(type(r["scores"][k]) is bool for k in REQUIRED_SCORES)
    ]
    task_errors = sum(r.get("task_error") is not None for r in usable)
    scoring_errors = sum(r.get("scoring_error") is not None for r in usable)
    integrity = complete and len(scored) == len(expected) and not task_errors and not scoring_errors
    passed = sum(
        all(r["scores"][k] for k in REQUIRED_SCORES)
        and r.get("task_error") is None
        and r.get("scoring_error") is None
        for r in scored
    )
    return dict(
        requested=len(expected),
        task_errors=task_errors,
        scoring_errors=scoring_errors,
        scored=len(scored),
        passed=passed,
        integrity_ok=bool(integrity),
        acceptance_ok=bool(integrity and passed == len(expected)),
        success_rate=passed / len(expected) if complete else None,
    )


def scripted_task(value):
    # This deterministic actor is not a quality measurement of any real model.
    from app.agent_loop import run_agent_loop
    from app.llm_types import ToolReply

    if value["kind"] == "reading":
        return reading_task(value)
    replies = iter(value["replies"])
    requests = []

    class Script:
        def chat_with_tools(self, messages, tools):
            requests.append(deepcopy(messages))
            return ToolReply.model_validate(next(replies))

    def deadline():
        if value.get("expired"):
            raise TimeoutError("fixture deadline")

    audits = []
    try:
        result = run_agent_loop(
            Script(),
            [dict(role="user", content=value["prompt"])],
            max_rounds=value["max_rounds"],
            check_deadline=deadline,
            audit_writer=lambda run, record: audits.append(record.model_dump(mode="json")),
        )
        return dict(
            status=result.status,
            tools=[r.status for r in result.executions],
            rounds=result.rounds,
            answer=result.answer,
            audits=audits,
            requests=requests,
        )
    except TimeoutError:
        return dict(status="deadline", tools=[], rounds=len(requests), audits=audits)


def reading_task(value):
    from types import SimpleNamespace

    from app.risk_reading import new_reading, review_step

    docs = deepcopy(value["documents"])
    by_id = {d["document_id"]: d for d in docs}

    class Reader:
        def document(self, key):
            return {**by_id[key], "content_hash": digest(by_id[key])}

    state = dict(reading=new_reading(), evidence=[], coverage={})
    state["reading"].update(
        stage="review",
        documents=[
            dict(
                **d,
                title=d["symbol"] + d["report_period"],
                kinds=["reports"],
                status="extracted",
                content_hash=digest(d),
            )
            for d in docs
        ],
    )
    admission = SimpleNamespace(
        settings=SimpleNamespace(model_provider="qwen", risk_document_chunk_chars=value["budget"])
    )

    def summarize(model, admission, material):
        payload = json.loads(material)
        # Deliberately oversized batch notes force a real reduction step.
        return (
            dict(facts=["合成逐批发现" * 300])
            if "excerpts" in payload
            else dict(facts=["合成汇总"])
        )

    for _ in range(200):
        if state["reading"]["stage"] == "ready":
            break
        review_step(state, None, admission, reader=Reader(), summarizer=summarize)
    return dict(status=state["reading"]["stage"], snapshot=state, documents=docs)


def score_output(output, gold):
    if "documents" not in gold:
        ok = all(output.get(k) == gold[k] for k in ("status", "tools", "rounds"))
        audits = output.get("audits", [])
        actual = [
            dict(
                tool_name=a.get("tool_name"),
                status=a.get("status"),
                result=a.get("result"),
                error_kind=(a.get("error") or {}).get("kind"),
            )
            for a in audits
        ]
        ok = ok and actual == gold["audits"] and output.get("answer") == gold["answer"]
        if gold["status"] != "deadline":
            requests = output.get("requests")
            if not isinstance(requests, list) or len(requests) != gold["rounds"]:
                return dict(contract=False)
            for audit_index, audit in enumerate(audits):
                if audit["status"] != "error":
                    continue
                if audit_index + 1 >= len(requests):
                    return dict(contract=False)
                feedback = [
                    json.loads(m["content"])
                    for m in requests[audit_index + 1]
                    if m.get("role") == "tool"
                    and m.get("tool_call_id") == audit.get("tool_call_id")
                ]
                ok = ok and any(
                    m.get("status") == "error"
                    and (m.get("error") or {}).get("kind") == audit["error"]["kind"]
                    for m in feedback
                )
        return dict(contract=ok)
    work = output["snapshot"]["reading"]
    evidence = output["snapshot"]["evidence"]
    ok = output["status"] == gold["status"] and len(work["batch_findings"]) == work["batches"]
    expected_ids = {d["document_id"] for d in gold["documents"]}
    ok = ok and {d["document_id"] for d in output["documents"]} == expected_ids
    ok = ok and {e["document_id"] for e in evidence} == expected_ids
    for expected in gold["documents"]:
        doc = next(d for d in output["documents"] if d["document_id"] == expected["document_id"])
        ok = ok and digest(doc) == expected["content_hash"]
        slices = [e for e in evidence if e["document_id"] == doc["document_id"]]
        ok = ok and all(doc[k] == expected[k] for k in ("symbol", "report_period", "url"))
        ok = ok and {e["page"] for e in slices} == set(expected["pages"])
        ok = ok and all(
            all(e.get(k) == expected[k] for k in ("symbol", "report_period", "url")) for e in slices
        )
        ok = ok and "".join(e["excerpt"] for e in slices) == "".join(
            p["text"] for p in doc["pages"]
        )
        for page in doc["pages"]:
            offset = 0
            for e in (e for e in slices if e["page"] == page["page"]):
                excerpt = e["excerpt"]
                ok = ok and type(e["offset"]) is int and e["offset"] == offset
                ok = ok and isinstance(excerpt, str) and bool(excerpt)
                ok = ok and e.get("content_hash") == expected["content_hash"]
                ok = ok and page["text"][offset : offset + len(excerpt)] == excerpt
                offset += len(excerpt)
            ok = ok and offset == len(page["text"])
    indices = [i for b in work["batch_findings"] for i in b["evidence_indices"]]
    ok = ok and indices == list(range(len(evidence))) and bool(work["reduction_history"])

    def cursor_at(consumed):
        for d_index, doc in enumerate(output["documents"]):
            for p_index, page in enumerate(doc["pages"]):
                if consumed < len(page["text"]):
                    return dict(document=d_index, page=p_index, offset=consumed)
                consumed -= len(page["text"])
        return dict(document=len(output["documents"]), page=0, offset=0) if consumed == 0 else None

    consumed = 0
    for batch in work["batch_findings"]:
        ok = ok and batch["cursor_before"] == cursor_at(consumed)
        consumed += sum(len(evidence[i]["excerpt"]) for i in batch["evidence_indices"])
        ok = ok and batch["cursor_after"] == cursor_at(consumed)
    notes = [b["summary"] for b in work["batch_findings"]]
    for index, batch in enumerate(work["batch_findings"], 1):
        ok = ok and batch["batch"] == index
        ok = ok and all(evidence[i]["review_batch"] == index for i in batch["evidence_indices"])
    for reduction in work["reduction_history"]:
        inputs = reduction["inputs"]
        ok = ok and bool(inputs) and notes[: len(inputs)] == inputs
        notes = [reduction["output"]] + notes[len(inputs) :]
    ok = ok and notes == work["findings"]
    return dict(contract=bool(ok))


def load_fixtures(root=None):
    root = Path(root) if root else ROOT / "evaluations/turaq"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8-sig"))
    for name in ("cases.json", "gold.json", "documents.json"):
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if manifest["files"].get(name) != actual:
            raise ValueError("fixture fingerprint mismatch: " + name)
    cases, gold, docs = [
        json.loads((root / name).read_text(encoding="utf-8-sig"))
        for name in ("cases.json", "gold.json", "documents.json")
    ]
    expected = [c["id"] for c in cases]
    if not expected or len(set(expected)) != len(expected) or set(gold) != set(expected):
        raise ValueError("invalid expected case/gold set")
    return manifest, cases, gold, docs


def run_suite(*, root=None, task=scripted_task, scorer=score_output):
    manifest, cases, gold, docs = load_fixtures(root)
    expected = [c["id"] for c in cases]
    rows = []
    for case in cases:
        row = dict(id=case["id"], scores={}, task_error=None, scoring_error=None)
        value = deepcopy(case["input"])
        if value["kind"] == "reading":
            value["documents"] = [d for d in docs if d["document_id"] in value["document_ids"]]
        try:
            row["output"] = task(value)
        except Exception as exc:
            row["task_error"] = type(exc).__name__
        else:
            try:
                scores = scorer(row["output"], gold[case["id"]])
                if not isinstance(scores, dict) or not REQUIRED_SCORES <= scores.keys():
                    raise ValueError("missing required score")
                if any(type(scores[k]) is not bool for k in REQUIRED_SCORES):
                    raise ValueError("invalid score type")
                row["scores"] = scores
            except Exception as exc:
                row["scoring_error"] = type(exc).__name__
        rows.append(row)
    from app.tools.registry import tool_definitions

    sources = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "app").rglob("*.py"))
    }
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    fingerprints = dict(
        app_commit=commit,
        app_sources=digest(sources),
        source_files=sources,
        tool_schema=digest(tool_definitions()),
        prompts=digest([c["input"]["prompt"] for c in cases]),
        fixtures=manifest,
        scorer=SCORER_VERSION,
        scorer_code=sources["app/research_eval.py"],
    )
    report = dict(
        mode="scripted_mechanism_only",
        expected_ids=expected,
        cases=rows,
        fingerprints=fingerprints,
        cost=None,
        real_model_quality="not_run",
        **assess(expected, rows),
    )
    from app.observability import emit

    emit(
        "experiment",
        status="completed" if report["acceptance_ok"] else "error",
        integrity_ok=report["integrity_ok"],
        app_fingerprint=fingerprints["app_sources"],
        dataset_fingerprint=digest(manifest),
        scorer_fingerprint=fingerprints["scorer_code"],
        requested=report["requested"],
        passed=report["passed"],
        scored=report["scored"],
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_suite()
    from app.observability import finish_cli_export

    report["trace_export"] = finish_cli_export()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("requested", "passed", "integrity_ok", "mode")}))
    return 0 if report["acceptance_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
