"""Expanded frozen-source comparison. --live enables one bounded provider run."""

import argparse
import hashlib
import io
import json
import os
import re
import time
import zipfile
from pathlib import Path
from statistics import median

import httpx

from app.openviking_benchmark import (
    ChromaComparator,
    completed_import,
    eligible,
    evidence_metrics,
    index_chroma,
    invalidate_resource,
    load_expanded,
    make_task,
    physical_page,
    resources_for,
    summarize,
)
from app.openviking_pilot import (
    PilotClient,
    bind_content,
    lexical_find,
    resolve_hits,
    verify_content,
)
from app.report_evidence_eval import read_json, score_answer
from app.report_fact_task import TASK_VERSION
from scripts import run_openviking_pilot as runtime

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluations/turaq/openviking/expanded/results"


class GateChat:
    def __init__(self, config):
        self.url = config["api_base"] + "/chat/completions"
        self.key = config["api_key"]
        self.model = config["model"]

    def chat(self, messages):
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            response = client.post(
                self.url,
                headers={"Authorization": "Bearer " + self.key},
                json=dict(model=self.model, messages=messages, max_tokens=1024),
                timeout=35,
            )
        if response.status_code != 200:
            raise RuntimeError("bounded model gateway HTTP " + str(response.status_code))
        return response.json()["choices"][0]["message"]["content"]


def install_pages(client, resources, corpus, report):
    bindings, roots = {}, {}
    selected = []
    fingerprint = hashlib.sha256(
        json.dumps(corpus["manifest"], sort_keys=True).encode()
    ).hexdigest()[:12]
    for doc_id in corpus["documents"]:
        report["stage"] = "upload_archive:" + doc_id
        runtime.save(report)
        pages = [r for r in resources if r["document_id"] == doc_id]
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for page in pages:
                heading = f"# {page['symbol']} {page['report_period']} PDF page {page['page']}\n\n"
                archive.writestr(f"p{page['page']:04d}.md", heading + page["text"])
        uploaded = client.call(
            "POST",
            "/api/v1/resources/temp_upload",
            files={"file": ("pages.zip", payload.getvalue(), "application/zip")},
        )
        report["stage"] = "import_archive:" + doc_id
        runtime.save(report)
        imported = client.call(
            "POST",
            "/api/v1/resources",
            json=dict(
                temp_file_id=uploaded["temp_file_id"],
                to=f"viking://~/resources/expanded-{fingerprint}/{doc_id}",
                create_parent=True,
                wait=True,
                processing_mode="vectors_only",
            ),
        )
        finished = runtime.wait_task(client, imported, seconds=180)
        imported = completed_import(imported, finished)
        report["stage"] = "verify_import:" + doc_id
        runtime.save(report)
        root_uri = imported.get("root_uri")
        if not root_uri:
            raise RuntimeError("missing imported document root")
        roots[doc_id] = root_uri
        files = client.call("GET", "/api/v1/fs/ls", params=dict(uri=root_uri, recursive=True))
        for item in files:
            number = physical_page(item)
            if number is None:
                continue
            page = next((p for p in pages if p["page"] == number), None)
            if page is None:
                raise RuntimeError("unexpected imported physical page")
            content = client.call("GET", "/api/v1/content/read", params={"uri": item["uri"]})
            bound = bind_content(page, content)
            bound["backend_uri"] = item["uri"]
            selected.append(bound)
            bindings[item["uri"]] = page["id"]
        if len([p for p in selected if p["document_id"] == doc_id]) != 16:
            raise RuntimeError("document did not preserve all 16 selected pages")
        report["imported_pages"] = len(selected)
        runtime.save(report)
        print(f"Imported {doc_id}: 16 verified pages", flush=True)
    queues = client.call("POST", "/api/v1/system/wait")
    if any(x.get("error_count", 0) for x in queues.values() if isinstance(x, dict)):
        raise RuntimeError("index queues reported errors")
    return selected, bindings, roots


def viking_find(client, case, resources, bindings, roots):
    allowed = eligible(resources, case)
    if not allowed:
        return []
    docs = {r["document_id"] for r in allowed}
    if len(docs) != 1:
        raise ValueError("this frozen benchmark requires one source report per question")
    hits = runtime.find(client, case["question"], roots[next(iter(docs))], limit=3)[:3]
    ranked = resolve_hits(hits, bindings, allowed)
    verified = []
    for resource in ranked:
        content = client.call(
            "GET", "/api/v1/content/read", params={"uri": resource["backend_uri"]}
        )
        if verify_content(resource, content):
            verified.append(
                dict(
                    document_id=resource["document_id"],
                    page=resource["page"],
                    text=resource["text"],
                    resource_id=resource["id"],
                )
            )
    return verified


def chroma_setup(resources, report):
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    from app.rag.core import RAGSystem

    start = time.monotonic()
    previous = ROOT / ".local-backups/openviking-expanded-2026-10-24-live-v1/chroma"
    directory = previous if previous.exists() else runtime.WORK / "chroma"
    rag = RAGSystem(persist_directory=str(directory), collection_name="expanded_benchmark")
    report["chroma_index"] = index_chroma(rag, resources)
    report["chroma_setup_seconds"] = round(time.monotonic() - start, 3)
    return ChromaComparator(rag, resources)


def record_case(engine, case, corpus, retrieve, model, report, gate):
    row = dict(
        id=case["id"],
        task_error=None,
        scoring_error=None,
        scores={},
        evidence=dict(at1=False, at3=False),
        fragments=[],
    )
    start = time.monotonic()
    before = None
    try:
        fragments = retrieve()
        row["retrieval_seconds"] = round(time.monotonic() - start, 4)
        row["evidence"] = evidence_metrics(corpus["gold"][case["id"]], fragments)
        row["fragments"] = fragments
        row["context_characters"] = sum(len(f["text"]) for f in fragments)
        if engine == "lexical":
            return row
        before = len(gate.records)
        answer_start = time.monotonic()
        row["output"] = make_task(model, case, corpus, fragments)()
        row["answer_seconds"] = round(time.monotonic() - answer_start, 4)
        scores = score_answer(row["output"], case, corpus)
        row["scores"] = dict(**scores, contract=all(scores.values()))
    except Exception as exc:
        row["task_error"] = type(exc).__name__
        row.setdefault("retrieval_seconds", round(time.monotonic() - start, 4))
    finally:
        attempts = gate.snapshot()["records"][before:] if before is not None else []
        attempts = [a for a in attempts if a.get("kind") == "chat"]
        tokens = [(a.get("usage") or {}).get("total_tokens") for a in attempts]
        row["model_attempts"] = len(attempts)
        row["model_tokens"] = sum(tokens) if all(t is not None for t in tokens) else None
        row["unknown_model_usage_attempts"] = sum(t is None for t in tokens)
        report["engines"][engine].append(row)
        runtime.save(report)
    return row


def exercise(base, root_key, resources, corpus, report, *, resume, memory_only, gate):
    if not resume:
        raise ValueError("expanded live run must reuse the isolated pilot workspace")
    with PilotClient(base, root_key) as root:
        key = root.call("POST", "/api/v1/admin/accounts/pilotlab/users/pilot-a/key", json={})[
            "user_key"
        ]
    cfg = json.loads((runtime.WORK / "ov.conf").read_text(encoding="utf-8"))
    model = GateChat(cfg["vlm"])
    chroma = chroma_setup(resources, report)
    report["engines"] = dict(chroma_bge=[], lexical=[], openviking=[])
    with PilotClient(base, key) as client:
        start = time.monotonic()
        bound, bindings, roots = install_pages(client, resources, corpus, report)
        report["openviking_setup_seconds"] = round(time.monotonic() - start, 3)
        report["setup_usage"] = gate.snapshot()
        for case in corpus["cases"]:
            record_case(
                "chroma_bge", case, corpus, lambda case=case: chroma.find(case), model, report, gate
            )
            report["engines"]["chroma_bge"][-1]["raw_evidence_without_similarity_gate"] = (
                evidence_metrics(corpus["gold"][case["id"]], chroma.last_raw)
            )
            record_case(
                "lexical",
                case,
                corpus,
                lambda case=case: [
                    dict(
                        document_id=r["document_id"],
                        page=r["page"],
                        text=r["text"],
                        resource_id=r["id"],
                    )
                    for r in lexical_find(case["question"], eligible(resources, case))
                ],
                model,
                report,
                gate,
            )
            record_case(
                "openviking",
                case,
                corpus,
                lambda case=case: viking_find(client, case, bound, bindings, roots),
                model,
                report,
                gate,
            )
            print("Compared " + case["id"], flush=True)
        report["lifecycle"] = lifecycle(client, chroma, bound, bindings, roots, corpus)
    expected = [c["id"] for c in corpus["cases"]]
    report["summaries"] = {}
    for engine, rows in report["engines"].items():
        summary = (
            summarize(rows, expected) if engine != "lexical" else dict(requested=len(expected))
        )
        positive = [r for r in rows if corpus["gold"][r["id"]]["status"] == "supported"]
        summary["evidence"] = dict(
            denominator=14,
            at1=sum(r.get("evidence", {}).get("at1") is True for r in positive),
            at3=sum(r.get("evidence", {}).get("at3") is True for r in positive),
        )
        summary["median_retrieval_seconds"] = median(r["retrieval_seconds"] for r in positive)
        summary["model_tokens_known"] = sum(r.get("model_tokens") or 0 for r in rows)
        report["summaries"][engine] = summary
    report["state"] = "completed"
    report["automatic_promotion"] = False
    runtime.save(report)


def lifecycle(client, chroma, resources, bindings, roots, corpus):
    target = next(r for r in resources if r["document_id"] == "moutai-2023" and r["page"] == 5)
    uri = target["backend_uri"]
    original = client.call("GET", "/api/v1/content/read", params={"uri": uri})
    client.call(
        "POST",
        "/api/v1/content/write",
        json=dict(
            uri=uri,
            mode="replace",
            wait=True,
            processing_mode="vectors_only",
            content=original + "\n合成测试：此版本撤回，不代表公司真实更正。",
        ),
    )
    changed = client.call("GET", "/api/v1/content/read", params={"uri": uri})
    output = dict(
        synthetic_only=True, appended_correction_rejected=not verify_content(target, changed)
    )
    invalidate_resource(target["id"], resources, chroma.resources)
    check_case = next(c for c in corpus["cases"] if c["id"] == "moutai23-revenue-2023")
    after_correction = dict(
        chroma=chroma.find(check_case),
        openviking=viking_find(client, check_case, resources, bindings, roots),
    )
    output["after_correction_old_page_blocked"] = {
        key: all(f["resource_id"] != target["id"] for f in found)
        for key, found in after_correction.items()
    }
    client.call("DELETE", "/api/v1/fs", params=dict(uri=uri, wait=True))
    output["deleted_direct_read_status"] = client.http.get(
        "/api/v1/content/read", params={"uri": uri}
    ).status_code
    deleted = chroma.rag.delete_document(target["id"])
    output["chroma_native_delete_success"] = deleted.get("success") is True
    after_deletion = dict(
        chroma=chroma.find(check_case),
        openviking=viking_find(client, check_case, resources, bindings, roots),
    )
    output["after_deletion_old_page_blocked"] = {
        key: all(f["resource_id"] != target["id"] for f in found)
        for key, found in after_deletion.items()
    }
    output["application_excludes_withdrawn_page"] = target["id"] not in {
        r["id"] for r in eligible(resources, check_case)
    }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-id", default="v1")
    args = parser.parse_args()
    if not re.fullmatch("[a-z0-9-]{1,32}", args.run_id):
        raise SystemExit("invalid run id")
    runtime.WORK = ROOT / ".local-backups" / ("openviking-expanded-2026-10-24-" + args.run_id)
    runtime.OUTPUT = RESULTS / ("comparison-2026-10-24-" + args.run_id + ".json")
    if runtime.OUTPUT.exists():
        raise SystemExit("preserve existing result before another run")
    corpus = load_expanded()
    resources = resources_for(corpus)
    fixtures = read_json(corpus["root"] / "fixture_answers.json")
    assert all(all(score_answer(fixtures[c["id"]], c, corpus).values()) for c in corpus["cases"])
    report = dict(
        state="validated",
        corpus_fingerprint=hashlib.sha256(
            json.dumps(corpus["manifest"], sort_keys=True).encode()
        ).hexdigest(),
        requested=20,
        resource_pages=48,
        task_version=TASK_VERSION,
        live=args.live,
        automatic_promotion=False,
        comparison_scope="3 reports / 48 selected pages; BGE512 vs Qwen1024; system comparison",
        chroma_similarity_gate="existing research wrapper: 1-distance >= 0.5",
        cost=None,
    )
    runtime.save(report)
    if args.live:
        report["state"] = "running"
        previous = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in RESULTS.glob("comparison-*.json")
            if p != runtime.OUTPUT
        ]
        used_calls = sum(r.get("usage", {}).get("attempts", 0) for r in previous)
        used_chars = sum(r.get("usage", {}).get("request_chars", 0) for r in previous)
        if used_calls >= 200 or used_chars >= 1200000:
            raise SystemExit("expanded experiment total budget exhausted")
        report["prior_provider_attempts"] = used_calls
        try:
            runtime.run_live(
                report,
                corpus,
                resources,
                resume="memory-check",
                runner=exercise,
                budget=dict(
                    max_calls=200 - used_calls, max_chars=1200000 - used_chars, seconds=1200
                ),
            )
        except Exception as exc:
            report.update(state="incomplete", error_type=type(exc).__name__)
            report["error_code"] = getattr(exc, "api_code", None)
            report["error_message"] = getattr(exc, "api_message", None) or (
                str(exc)[:300] if isinstance(exc, RuntimeError) else None
            )
            runtime.save(report)
            print("Expanded comparison incomplete: " + type(exc).__name__, flush=True)
            raise SystemExit(1) from None
    print(
        json.dumps(
            dict(state=report["state"], summaries=report.get("summaries")), ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
