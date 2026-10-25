import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.risk_reading import document_summary, new_reading, review_step
from tests.unit.admission import offline_admission


def run_batch(summary):
    from app.llm_client import FakeModelClient

    pages = json.loads(
        Path("evaluations/turaq/public_reports/sources/moutai-2024.pages.json").read_text(
            encoding="utf-8"
        )
    )
    text = pages[4]["text"]
    admitted = offline_admission()
    admitted.settings.model_provider = "qwen"
    state = dict(reading=new_reading(), evidence=[], coverage={})
    state["reading"].update(
        stage="review",
        documents=[
            dict(
                document_id="a" * 24,
                title="茅台2024年报",
                symbol="600519.SH",
                report_period="2024",
                published_date="2025-04-03",
                url="https://example.invalid/a",
                kinds=["reports"],
                status="extracted",
                content_hash="frozen",
            )
        ],
    )

    class Reader:
        def document(self, key):
            return dict(content_hash="frozen", pages=[dict(page=5, text=text)])

    review_step(
        state, FakeModelClient(json.dumps(summary, ensure_ascii=False)), admitted, reader=Reader()
    )
    return state, text


def sample():
    return dict(
        facts=["[茅台2024年报/5]2024营业收入为170,899,152,276.34元"],
        inferences=[],
        unknowns=[],
        risk_level="unknown",
        sources=["茅台2024年报"],
        fact_citations=[
            dict(fact_index=0, document_id="a" * 24, page=5, quote="170,899,152,276.34")
        ],
    )


def test_production_batch_locates_quote_and_links_evidence():
    summary = sample()
    state, text = run_batch(summary)
    batch = state["reading"]["batch_findings"][0]
    assert batch["raw_summary"] == summary
    check = batch["summary"]["citation_checks"][0]
    assert check["state"] == "quote_located"
    link = check["links"][0]
    assert text[link["start"] : link["end"]] == "170,899,152,276.34"
    assert link["symbol"] == "600519.SH" and link["report_period"] == "2024"
    assert link["content_hash"] == "frozen"
    assert state["evidence"][0]["conclusion_refs"] == [check["claim_id"]]
    assert state["evidence"][0]["verification"] == "source_retrieved"


@pytest.mark.parametrize("mutation", ["missing", "wrong_quote", "wrong_page", "wrong_document"])
def test_missing_or_invalid_citation_is_explicit_not_linked(mutation):
    summary = sample()
    if mutation == "missing":
        summary.pop("fact_citations")
    else:
        key, value = {
            "wrong_quote": ("quote", "编造"),
            "wrong_page": ("page", 99),
            "wrong_document": ("document_id", "b" * 24),
        }[mutation]
        summary["fact_citations"][0][key] = value
    state, _ = run_batch(summary)
    check = state["reading"]["batch_findings"][0]["summary"]["citation_checks"][0]
    assert check["state"] == "unresolved"
    assert state["evidence"][0]["conclusion_refs"] == []
    assert state["reading"]["findings"][0]["facts"][0].startswith("[引用未定位]")
    assert state["reading"]["findings"][0]["unknowns"]


def test_locator_rejects_ambiguous_and_cross_batch_quotes_and_missing_hash():
    from app.document_citations import locate_fact_citations

    excerpt = dict(
        document_id="a" * 24, page=5, offset=37, excerpt="123 and 123", content_hash="frozen"
    )
    summary = sample()
    summary["fact_citations"][0]["quote"] = "123"
    result = locate_fact_citations(summary, [excerpt], batch=2)
    assert result["citation_checks"][0]["reasons"] == ["ambiguous_quote"]
    excerpt["excerpt"] = "123 only"
    result = locate_fact_citations(summary, [excerpt], batch=2)
    assert result["citation_checks"][0]["links"][0]["start"] == 37
    excerpt["content_hash"] = None
    assert locate_fact_citations(summary, [excerpt], batch=2)["citation_checks"][0]["reasons"] == [
        "missing_content_hash"
    ]
    excerpt["excerpt"] = "from another batch"
    assert (
        locate_fact_citations(summary, [excerpt], batch=2)["citation_checks"][0]["state"]
        == "unresolved"
    )


def test_all_references_for_a_fact_must_resolve_and_out_of_range_is_rejected():
    from app.document_citations import locate_fact_citations

    excerpt = dict(
        document_id="a" * 24, page=5, offset=0, excerpt="123 only", content_hash="frozen"
    )
    summary = sample()
    summary["fact_citations"][0]["quote"] = "123"
    summary["fact_citations"].append(dict(fact_index=0, document_id="b" * 24, page=5, quote="123"))
    result = locate_fact_citations(summary, [excerpt], batch=1)
    assert result["citation_checks"][0]["links"] == []
    summary["fact_citations"] = [dict(fact_index=9, document_id="a" * 24, page=5, quote="123")]
    assert locate_fact_citations(summary, [excerpt], batch=1)["rejected_references"] == [
        "fact_index_out_of_range"
    ]


def test_progress_and_final_material_do_not_certify_merged_claims():
    from app.risk_reading import final_material, progress

    state, _ = run_batch(sample())
    coverage = progress(state)["citation_coverage"]
    assert coverage["quote_located"] == 1 and coverage["final_claims_verified"] is False
    state.update(context={}, facts=[])
    material = json.loads(final_material(state))
    assert material["reading_progress"]["citation_coverage"] == coverage


def test_production_schema_is_batch_only_and_rejects_spoofed_verification():
    from app.llm_client import FakeModelClient
    from app.risk_summary import RiskSummaryParseError

    a = offline_admission()
    summary = sample()
    summary["fact_citations"][0]["state"] = "verified"
    with pytest.raises(RiskSummaryParseError):
        document_summary(FakeModelClient(json.dumps(summary)), a, json.dumps({"excerpts": []}))
    old = sample()
    old.pop("fact_citations")
    final = document_summary(FakeModelClient(json.dumps(old)), a, "{}", final=True)
    assert "fact_citations" not in final and final == old


def test_reduction_retains_batch_links_without_certifying_merged_facts():
    summary = sample()
    pages = json.loads(
        Path("evaluations/turaq/public_reports/sources/moutai-2024.pages.json").read_text(
            encoding="utf-8"
        )
    )
    summary["facts"] = summary["facts"] * 12
    summary["fact_citations"] = [
        dict(fact_index=i, document_id="a" * 24, page=5, quote=pages[4]["text"][:900])
        for i in range(12)
    ]
    state, _ = run_batch(summary)
    assert state["reading"]["stage"] == "reduce"
    evidence = deepcopy(state["evidence"])
    a = offline_admission()
    a.settings.model_provider = "qwen"
    review_step(
        state,
        None,
        a,
        summarizer=lambda *args: dict(
            facts=["合并发现"], inferences=[], unknowns=[], sources=[], risk_level="unknown"
        ),
    )
    assert state["reading"]["findings"][0]["citation_scope"] == "merged_claims_unverified"
    assert state["reading"]["findings"][0]["unknowns"]
    assert state["evidence"] == evidence
    assert len(state["evidence"][0]["conclusion_refs"]) == 12


def test_multiple_quotes_in_same_excerpt_do_not_duplicate_claim_reference():
    summary = sample()
    summary["fact_citations"].append(
        dict(fact_index=0, document_id="a" * 24, page=5, quote="147,693,604,994.14")
    )
    state, _ = run_batch(summary)
    checks = state["reading"]["batch_findings"][0]["summary"]["citation_checks"]
    assert len(checks[0]["links"]) == 2
    assert state["evidence"][0]["conclusion_refs"] == [checks[0]["claim_id"]]


def test_ready_legacy_snapshot_exposes_missing_history_before_any_review():
    from app.document_citations import citation_coverage

    work = dict(batches=2, batch_findings=[], findings=[dict(facts=["旧结论"])])
    coverage = citation_coverage(work)
    assert coverage["legacy_history_incomplete"]
    assert coverage["unarchived_batches"] == 2
    assert coverage["quote_located"] == 0 and coverage["final_claims_verified"] is False


def test_final_material_omits_quote_payload_without_mutating_durable_checks():
    from app.risk_reading import final_material

    state, _ = run_batch(sample())
    state.update(context={}, facts=[])
    original = deepcopy(state["reading"]["findings"])
    material = json.loads(final_material(state))
    assert "citation_checks" not in material["full_document_findings"][0]
    assert "rejected_references" not in material["full_document_findings"][0]
    assert material["reading_progress"]["citation_coverage"]["quote_located"] == 1
    assert state["reading"]["findings"] == original


def test_invalid_model_reference_does_not_advance_or_persist_partial_batch():
    from app.llm_client import FakeModelClient
    from app.risk_summary import RiskSummaryParseError

    a = offline_admission()
    a.settings.model_provider = "qwen"
    state = dict(reading=new_reading(), evidence=[], coverage={})
    state["reading"].update(
        stage="review",
        documents=[
            dict(
                document_id="a" * 24,
                title="fixture",
                published_date="2025-04-03",
                url="https://example.invalid/a",
                kinds=["reports"],
                status="extracted",
                content_hash="frozen",
            )
        ],
    )

    class Reader:
        def document(self, key):
            return dict(content_hash="frozen", pages=[dict(page=5, text="123")])

    before = deepcopy(state)
    summary = sample()
    summary["fact_citations"][0]["quote"] = ""
    with pytest.raises(RiskSummaryParseError):
        review_step(state, FakeModelClient(json.dumps(summary)), a, reader=Reader())
    assert state == before
