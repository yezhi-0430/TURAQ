"""Bounded source selection for exact-known public-document evaluation contexts."""

from app.rag.hybrid import bm25, label, metric_groups, period_compatibility
from app.rag.table_chunks import table_units
from app.report_evidence_eval import FactAnswer
from app.report_evidence_task import evidence_task
from app.report_fact_task import fact_task

VERSION = "document-bm25-source-spans-v1"


def select_evidence(context):
    units = []
    for doc in context["documents"]:
        for page in doc["pages"]:
            for unit in table_units(page["text"]):
                units.append(dict(unit, document_id=doc["id"], page=page["page"]))
    if not units:
        return []
    groups = metric_groups(context["metric"])
    query = context["question"] + " " + context["period"]
    expanded = query + " " + " ".join(alias for group in groups for alias in group)
    scores = bm25(expanded, [u["search_text"] for u in units])

    def rank(i):
        u = units[i]
        coverage = sum(any(a in label(u["body"]["text"]) for a in group) for group in groups)
        return (
            -coverage,
            -period_compatibility(query, u),
            -int(u["kind"] == "table_row"),
            -scores[i],
            u["document_id"],
            u["page"],
            u["body"]["char_start"],
        )

    selected, fragments, seen = [], [], set()
    for i in sorted((i for i, score in enumerate(scores) if score > 0), key=rank):
        unit, duplicate = units[i], False
        body = unit["body"]
        for old in selected:
            if (old["document_id"], old["page"]) == (unit["document_id"], unit["page"]):
                other = old["body"]
                overlap = max(
                    0,
                    min(body["char_end"], other["char_end"])
                    - max(body["char_start"], other["char_start"]),
                )
                if overlap >= 0.8 * min(len(body["text"]), len(other["text"])):
                    duplicate = True
        if duplicate:
            continue
        additions = []
        for part in [*unit["headers"], body]:
            key = (unit["document_id"], unit["page"], part["char_start"], part["char_end"])
            if key not in seen:
                additions.append(dict(part, document_id=unit["document_id"], page=unit["page"]))
        if (
            len(fragments) + len(additions) > 20
            or sum(len(f["text"]) for f in fragments + additions) > 4800
        ):
            continue
        fragments.extend(additions)
        seen.update(
            (f["document_id"], f["page"], f["char_start"], f["char_end"]) for f in additions
        )
        selected.append(unit)
        if len(selected) == 3:
            break
    return fragments


def application_task(client, *, selector=None):
    """Only trusted build_context data reaches this adapter; no reference annotations."""
    excluded_task = fact_task(client)

    def run(context):
        decision = dict(state="started")
        run.decisions.append(decision)
        try:
            if not context["documents"]:
                decision["source"] = "server_exclusion_rule"
                answer = excluded_task(context)
            else:
                if selector is None:
                    fragments = select_evidence(context)
                else:
                    fragments, decision["retrieval"] = selector(context)
                decision.update(source="source_evidence_ids", evidence_parts=len(fragments))
                if fragments:
                    answer = evidence_task(client, context, fragments)
                else:
                    answer = FactAnswer(
                        status="insufficient",
                        **{k: context[k] for k in ("symbol", "metric", "period")},
                        value=None,
                        unit=None,
                        reason_code="evidence_not_found",
                        citations=[],
                    ).model_dump()
        except Exception as exc:
            decision.update(state="task_error", error=type(exc).__name__)
            raise
        decision["state"] = "completed"
        return answer

    run.decisions = []
    return run
