"""Locate batch fact quotations; location is not semantic or numeric verification."""

from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.risk_summary import RiskSummary


class FactCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    fact_index: int = Field(ge=0, le=11)
    document_id: str = Field(min_length=1, max_length=100)
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=1000)


class DocumentBatchSummary(RiskSummary):
    model_config = ConfigDict(extra="forbid", strict=True)
    facts: list[str] = Field(max_length=12)
    fact_citations: list[FactCitation] = Field(default_factory=list, max_length=36)


def _locate(citation, excerpts):
    scoped = [
        (i, e)
        for i, e in enumerate(excerpts)
        if e["document_id"] == citation.document_id and e["page"] == citation.page
    ]
    matches = []
    for index, excerpt in scoped:
        start = excerpt["excerpt"].find(citation.quote)
        while start >= 0:
            matches.append((index, excerpt, start))
            if len(matches) > 1:
                return None, "ambiguous_quote"
            start = excerpt["excerpt"].find(citation.quote, start + 1)
    if not matches:
        return None, "quote_not_in_batch"
    index, excerpt, start = matches[0]
    if not excerpt.get("content_hash"):
        return None, "missing_content_hash"
    offset = excerpt.get("offset")
    if type(offset) is not int or offset < 0:
        return None, "invalid_source_offset"
    return dict(
        excerpt_index=index,
        document_id=citation.document_id,
        page=citation.page,
        start=offset + start,
        end=offset + start + len(citation.quote),
        quote=citation.quote,
        content_hash=excerpt["content_hash"],
        symbol=excerpt.get("symbol"),
        report_period=excerpt.get("report_period"),
        url=excerpt.get("url"),
    ), None


def locate_fact_citations(summary, excerpts, *, batch):
    result = deepcopy(summary)
    references = result.pop("fact_citations", [])
    grouped = {i: [] for i in range(len(result["facts"]))}
    rejected = []
    for raw in references:
        try:
            reference = FactCitation.model_validate(raw)
        except ValidationError:
            rejected.append("invalid_reference")
            continue
        if reference.fact_index not in grouped:
            rejected.append("fact_index_out_of_range")
        else:
            grouped[reference.fact_index].append(reference)
    checks = []
    unresolved = 0
    for index, refs in grouped.items():
        links, reasons = [], []
        for reference in refs:
            link, reason = _locate(reference, excerpts)
            if reason:
                reasons.append(reason)
            elif link not in links:
                links.append(link)
        if not refs:
            reasons.append("missing_reference")
        located = bool(links) and not reasons
        checks.append(
            dict(
                fact_index=index,
                claim_id=f"reading:{batch}:fact:{index}",
                state="quote_located" if located else "unresolved",
                reasons=sorted(set(reasons)),
                links=links if located else [],
            )
        )
        if not located:
            unresolved += 1
            result["facts"][index] = "[引用未定位]" + result["facts"][index]
    if unresolved:
        result.setdefault("unknowns", []).append(
            f"本批{unresolved}条事实的引文未定位，需核对原文。"
        )
    result["citation_checks"] = checks
    result["rejected_references"] = rejected
    result["citation_scope"] = "quote_location_only_not_semantic_verification"
    return result


def citation_coverage(work):
    located = unresolved = legacy = 0
    for batch in work.get("batch_findings", []):
        summary = batch["summary"]
        if "citation_checks" not in summary:
            legacy += len(summary.get("facts", []))
            continue
        located += sum(c["state"] == "quote_located" for c in summary["citation_checks"])
        unresolved += sum(c["state"] == "unresolved" for c in summary["citation_checks"])
    # Older ready snapshots may never re-enter review_step, so infer missing history here too.
    unarchived = max(0, work.get("batches", 0) - len(work.get("batch_findings", [])))
    return dict(
        quote_located=located,
        unresolved=unresolved,
        legacy_unverified=legacy,
        unarchived_batches=unarchived,
        legacy_history_incomplete=bool(work.get("legacy_findings_unavailable") or unarchived),
        final_claims_verified=False,
        scope="batch_quote_location_only",
    )
