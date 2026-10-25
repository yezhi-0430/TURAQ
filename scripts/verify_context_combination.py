"""Explicit real native-store acceptance; public sources and synthetic actors only.

Run as a module from the repository. Never invokes a cloud provider or the app DB.
The two reserved acceptance actor IDs are not application user records.
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from app.analysis.evidence import select_evidence
from app.analysis.quality import corpus
from app.config import Settings
from app.context_store import (
    BASE,
    ContextStore,
    ContextUnavailable,
    NativeError,
    ResearchPreferences,
    select_combined_evidence,
)
from app.report_evidence_eval import build_context
from scripts.launch_context_store import status

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evaluations/turaq/context-combination/functional.json"
ACTOR_A, ACTOR_B = 900000001, 900000002


def launcher(*args):
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts/launch_context_store.py"), *args],
        capture_output=True,
        timeout=140,
    )
    if result.returncode:
        raise RuntimeError("Dedicated context service operation failed; inspect local logs")


def persisted_pages(store, contexts):
    """Read every expected original body before any auto-materializing operation."""
    if not store.scope():
        return False
    expected = {}
    for context in contexts:
        for doc in context["documents"]:
            for page in doc["pages"]:
                text_hash = hashlib.sha256(page["text"].encode()).hexdigest()
                uri = f"{BASE}/{doc['pdf_sha256']}/p{page['page']:04d}-{text_hash}.md"
                expected[uri] = page["text"]
    try:
        return bool(expected) and all(
            store.call("GET", "/api/v1/content/read", params={"uri": uri}) == text
            for uri, text in expected.items()
        )
    except ContextUnavailable:
        return False


def main():
    settings = Settings()
    preference = ResearchPreferences(answer_detail="detailed")
    checks = {}
    with ContextStore(settings, ACTOR_A) as store:
        store.save_preferences(preference)
    with ContextStore(settings, ACTOR_B) as store:
        checks["other_actor_has_no_preferences"] = store.read_preferences() is None
        store.scope(create=True)
    data = corpus()
    retrieval = []
    for case in data["cases"]:
        ctx = build_context(case, data)
        with ContextStore(settings, ACTOR_A) as store:
            fragments, mode = store.select(ctx)
        for fragment in fragments:
            document = next(d for d in ctx["documents"] if d["id"] == fragment["document_id"])
            page = next(p for p in document["pages"] if p["page"] == fragment["page"])
            assert page["text"][fragment["char_start"] : fragment["char_end"]] == fragment["text"]
        retrieval.append(
            dict(
                id=case["id"],
                mode=mode,
                evidence_parts=len(fragments),
                eligible_pages=sum(len(d["pages"]) for d in ctx["documents"]),
            )
        )
    checks["public_fact_retrieval"] = all(
        r["mode"] == "openviking_files" for r in retrieval if r["eligible_pages"]
    )
    checks["excluded_contexts_empty"] = all(
        r["evidence_parts"] == 0 for r in retrieval if not r["eligible_pages"]
    )
    # Unique public file belongs to A's native account; B receives no body.
    sample = build_context(next(c for c in data["cases"] if c["symbol"] == "600519.SH"), data)
    doc, page = sample["documents"][0], sample["documents"][0]["pages"][0]
    text_hash = hashlib.sha256(page["text"].encode()).hexdigest()
    uri = f"{BASE}/{doc['pdf_sha256']}/p{page['page']:04d}-{text_hash}.md"
    # Mutate only a disposable acceptance actor mirror and always restore it.
    with ContextStore(settings, ACTOR_A) as store:
        store.scope()
        store.write(
            uri.rsplit("/", 1)[0],
            [{"uri": uri, "content": "synthetic changed mirror", "mode": "upsert"}],
        )
    try:
        with ContextStore(settings, ACTOR_A) as store:
            fragments, mode = store.select(sample)
        checks["changed_native_body_falls_back"] = (
            mode == "local_fallback" and fragments == select_evidence(sample)
        )
    finally:
        with ContextStore(settings, ACTOR_A) as store:
            store.scope()
            store.write(
                uri.rsplit("/", 1)[0], [{"uri": uri, "content": page["text"], "mode": "upsert"}]
            )
    with ContextStore(settings, ACTOR_B) as store:
        store.scope()
        try:
            store.call("GET", "/api/v1/content/read", params={"uri": uri})
        except NativeError as exc:
            checks["native_other_account_cannot_read_page"] = exc.status in (403, 404)
        else:
            checks["native_other_account_cannot_read_page"] = False
    before = status()
    launcher("--stop")
    deadline = time.monotonic() + 20
    while status() is not None:
        if time.monotonic() >= deadline:
            raise RuntimeError("Dedicated service did not stop")
        time.sleep(0.5)
    fragments, mode = select_combined_evidence(sample, settings, ACTOR_A)
    checks["offline_fallback_matches_local"] = (
        mode == "local_fallback" and fragments == select_evidence(sample)
    )
    launcher()
    with ContextStore(Settings(), ACTOR_A) as store:
        checks["public_pages_survive_restart"] = persisted_pages(
            store, [build_context(case, data) for case in data["cases"]]
        )
        checks["preferences_survive_restart"] = store.read_preferences() == preference
        store.clear_preferences()
        checks["explicit_clear_confirmed"] = store.read_preferences() is None
    after = status()
    protocol = json.loads(
        (ROOT / "evaluations/turaq/evidence-id-v2/protocol.json").read_text(encoding="utf-8")
    )
    files = protocol["files"]
    # Protocol is a mapping of paths to digests, not new result interpretation.
    unchanged = all(
        hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
        for path, digest in files.items()
    )
    checks["frozen_method_files_unchanged"] = unchanged
    result = dict(
        state="completed" if all(checks.values()) else "failed",
        checks=checks,
        retrieval=retrieval,
        provider_calls=0,
        model_accuracy_run=False,
        frozen_files=len(files),
        initialization_model_requests_rejected_before_restart=before["rejected_model_requests"],
        initialization_model_requests_rejected_after_restart=after["rejected_model_requests"],
        native_version="0.5.2",
        service_ready=after["ready"],
        preference_data="synthetic typed preference cleared after verification",
        scope="exact-known public report selected pages; not full-corpus or semantic search",
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
