"""Frozen, source-scoped retrieval and answer comparison; never production routing."""

import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path

from app.openviking_pilot import allowed_resources, prepare_resources
from app.report_evidence_eval import FactAnswer, build_context, load_corpus
from app.report_fact_task import QuoteFactAnswer, _unique_pairs, resolve_proposal, system_prompt

EXPANDED = Path(__file__).resolve().parents[1] / "evaluations/turaq/openviking/expanded"


def load_expanded():
    return load_corpus(EXPANDED)


def resources_for(corpus):
    return prepare_resources(corpus, owner="pilot-a")


def eligible(resources, case):
    if case.get("withdrawn"):
        return []
    selected = allowed_resources(
        resources, owner=case["owner"], symbol=case["symbol"], as_of=case["as_of"]
    )
    return [
        r
        for r in selected
        if r["report_period"] == case["report_period"] and r["document_id"] in case["document_ids"]
    ]


def evidence_metrics(gold, fragments):
    if gold["status"] != "supported":
        return dict(at1=None, at3=None)

    def hit(items):
        return any(
            f["document_id"] == a["document_id"]
            and f["page"] == a["page"]
            and a["quote"] in f["text"]
            for f in items
            for a in gold["allowed_anchors"]
        )

    return dict(at1=hit(fragments[:1]), at3=hit(fragments[:3]))


def _empty_reason(case, corpus):
    docs = [corpus["documents"][key] for key in case["document_ids"]]
    if all(d["symbol"] != case["symbol"] for d in docs):
        return "wrong_security"
    if all(
        date.fromisoformat(d["published_date"]) >= date.fromisoformat(case["as_of"]) for d in docs
    ):
        return "not_yet_public"
    if not eligible(resources_for(corpus), case):
        return "sources_unavailable"
    return "evidence_not_found"


def make_task(client, case, corpus, fragments):
    """Only retrieved text reaches the model; original pages locate quotes server-side."""
    allowed = {(r["document_id"], r["page"]) for r in eligible(resources_for(corpus), case)}
    if any((f["document_id"], f["page"]) not in allowed for f in fragments):
        raise ValueError("fragment outside authorized source scope")
    source_context = build_context(case, corpus)
    context = {k: deepcopy(source_context[k]) for k in source_context if k != "documents"}
    context["documents"] = []
    for doc in source_context["documents"]:
        selected = [f for f in fragments if f["document_id"] == doc["id"]]
        if selected:
            context["documents"].append(
                dict(
                    **{k: deepcopy(v) for k, v in doc.items() if k != "pages"},
                    pages=[dict(page=f["page"], text=f["text"]) for f in selected],
                )
            )

    def run():
        if not fragments:
            return FactAnswer(
                status="insufficient",
                symbol=case["symbol"],
                metric=case["metric"],
                period=case["period"],
                value=None,
                unit=None,
                citations=[],
                reason_code=_empty_reason(case, corpus),
            ).model_dump()
        raw = client.chat(
            [
                dict(role="system", content=system_prompt()),
                dict(role="user", content=json.dumps(context, ensure_ascii=False)),
            ]
        )
        proposal = QuoteFactAnswer.model_validate(json.loads(raw, object_pairs_hook=_unique_pairs))
        for citation in proposal.citations:
            if not any(
                citation.document_id == f["document_id"]
                and citation.page == f["page"]
                and citation.quote in f["text"]
                for f in fragments
            ):
                raise ValueError("unseen quote outside retrieved fragment")
        answer, _ = resolve_proposal(proposal.model_dump(), source_context)
        return answer

    return run


def summarize(rows, expected_ids):
    expected = set(expected_ids)
    ids = [r["id"] for r in rows]
    scored = [r for r in rows if type((r.get("scores") or {}).get("contract")) is bool]
    missing = sorted(expected - set(ids))
    errors = sum(bool(r.get("task_error") or r.get("scoring_error")) for r in rows)
    return dict(
        requested=len(expected_ids),
        scored=len(scored),
        passed=sum(r["scores"]["contract"] for r in scored),
        missing=missing,
        task_or_scoring_errors=errors,
        integrity_ok=not missing
        and len(ids) == len(set(ids))
        and set(ids) == expected
        and errors == 0
        and len(scored) == len(expected_ids),
    )


class ChromaComparator:
    """Existing RAGSystem search with its research wrapper's 0.5 similarity gate."""

    def __init__(self, rag, resources):
        self.rag = rag
        self.resources = resources
        self.last_raw = []

    def find(self, case):
        allowed = {r["id"]: r for r in eligible(self.resources, case)}
        if not allowed:
            self.last_raw = []
            return []
        result = self.rag.search(
            case["question"], n_results=3, filter_metadata={"resource_id": {"$in": list(allowed)}}
        )
        if not result.get("success"):
            raise RuntimeError("existing Chroma search failed")
        found = []
        self.last_raw = []
        for row in result["results"]:
            resource = allowed.get(row.get("metadata", {}).get("resource_id"))
            if resource is None:
                continue
            fragment = dict(
                document_id=resource["document_id"],
                page=resource["page"],
                text=row["text"],
                resource_id=resource["id"],
            )
            self.last_raw.append(fragment)
            distance = row.get("distance")
            if isinstance(distance, (int, float)) and 1 - distance >= 0.5:
                found.append(fragment)
        return found


def index_chroma(rag, resources):
    stored = rag.collection.get(include=["metadatas"])["metadatas"]
    by_id = {}
    for row in stored:
        by_id.setdefault(row.get("resource_id"), []).append(row)
    result = dict(reused_pages=0, indexed_pages=0)
    for resource in resources:
        rows = by_id.get(resource["id"], [])
        if rows:
            totals = {r.get("total_chunks") for r in rows}
            if (
                len(totals) != 1
                or type(next(iter(totals))) is not int
                or {r.get("chunk_index") for r in rows} != set(range(next(iter(totals))))
            ):
                raise ValueError("partial Chroma page requires an independent rebuild")
            result["reused_pages"] += 1
            continue
        added = rag.add_text(
            resource["text"],
            doc_id=resource["id"],
            metadata=dict(
                resource_id=resource["id"],
                document_id=resource["document_id"],
                page=resource["page"],
            ),
        )
        if not added.get("success"):
            raise RuntimeError(
                "local Chroma index failed: " + str(added.get("error", "unknown"))[:300]
            )
        result["indexed_pages"] += 1
    return result


def invalidate_resource(identity, *catalogues):
    for catalogue in catalogues:
        for resource in catalogue:
            if resource["id"] == identity:
                resource["active"] = False


def completed_import(initial, finished):
    if initial.get("task_id"):
        if finished.get("status") != "completed":
            raise ValueError("import task is not completed")
        result = finished.get("result") or {}
    else:
        result = initial
    if result.get("errors") or not result.get("root_uri"):
        raise ValueError("import did not produce a complete root")
    return result


def physical_page(item):
    if item.get("isDir"):
        return None
    name = item.get("uri", "").rstrip("/").rsplit("/", 1)[-1]
    match = re.fullmatch(r"p(\d{4})\.md", name)
    return int(match[1]) if match else None
