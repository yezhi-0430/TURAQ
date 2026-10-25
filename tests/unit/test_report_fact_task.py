import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.report_evidence_eval import build_context, load_corpus, score_answer
from app.report_fact_task import fact_task, resolve_proposal

ROOT = Path("evaluations/turaq/public_reports")


def example(case_id="moutai-profit-2024"):
    corpus = load_corpus()
    case = next(c for c in corpus["cases"] if c["id"] == case_id)
    answer = json.loads((ROOT / "fixture_answers.json").read_text(encoding="utf-8"))[case_id]
    for citation in answer["citations"]:
        citation.pop("start")
        citation.pop("end")
    return corpus, case, build_context(case, corpus), answer


class Reply:
    def __init__(self, proposal):
        self.proposal, self.calls = proposal, []

    def chat(self, messages):
        self.calls.append(messages)
        return json.dumps(self.proposal, ensure_ascii=False)


def test_exact_wrapped_profit_quote_resolves_without_model_offsets():
    corpus, case, context, proposal = example()
    original = deepcopy(proposal)
    answer, check = resolve_proposal(proposal, context)
    assert proposal == original
    assert all(score_answer(answer, case, corpus).values())
    assert check["state"] == "quote_located"
    assert check["scope"] == "quote_location_only_not_semantic_verification"
    assert answer["citations"][0]["quote"] == proposal["citations"][0]["quote"]


def test_captured_rewritten_quote_remains_unverified():
    corpus, case, context, _ = example()
    parent = json.loads((ROOT / "results/live-baseline-2026-10-23.json").read_text("utf-8"))
    proposal = next(r["output"] for r in parent["cases"] if r["id"] == case["id"])
    for citation in proposal["citations"]:
        citation.pop("start")
        citation.pop("end")
    answer, check = resolve_proposal(proposal, context)
    assert answer["value"] == proposal["value"] and answer["status"] == "supported"
    assert answer["citations"] == []
    assert check["state"] == "unresolved" and "quote_not_in_batch" in check["reasons"]
    assert not score_answer(answer, case, corpus)["evidence"]


@pytest.mark.parametrize("bad", ["ambiguous", "mixed", "missing", "wrong_page"])
def test_unlocatable_quotes_never_get_invented_or_partial_coordinates(bad):
    _, _, context, proposal = example()
    citation = proposal["citations"][0]
    if bad == "ambiguous":
        doc = next(d for d in context["documents"] if d["id"] == citation["document_id"])
        page = next(p for p in doc["pages"] if p["page"] == citation["page"])
        page["text"] += "\n" + citation["quote"]
    elif bad == "mixed":
        proposal["citations"].append(dict(citation, quote="missing quotation"))
    elif bad == "missing":
        proposal["citations"] = []
    else:
        citation["page"] = 999
    answer, check = resolve_proposal(proposal, context)
    assert check["state"] == "unresolved" and answer["citations"] == []


@pytest.mark.parametrize("field,value", [("value", "999"), ("unit", "百万元")])
def test_locator_does_not_certify_wrong_number_or_unit(field, value):
    corpus, case, context, proposal = example()
    proposal[field] = value
    answer, check = resolve_proposal(proposal, context)
    assert check["state"] == "quote_located"
    assert not score_answer(answer, case, corpus)["value"]


@pytest.mark.parametrize(
    "case_id,reason",
    [("wrong-security", "wrong_security"), ("before-publication", "not_yet_public")],
)
def test_server_exclusions_abstain_with_correct_reason_without_model(case_id, reason):
    corpus, case, context, _ = example(case_id)
    client = Reply({"must": "not be called"})
    task = fact_task(client)
    answer = task(context)
    assert not client.calls and not task.raw_responses
    assert answer["reason_code"] == reason
    assert all(score_answer(answer, case, corpus).values())
    assert task.decisions[0]["source"] == "server_exclusion_rule"


def test_mixed_or_missing_exclusion_reasons_do_not_guess_specific_reason():
    _, _, context, _ = example("wrong-security")
    client = Reply({})
    for excluded in ([], context["excluded_sources"] + [dict(reason="not_yet_public")]):
        context["excluded_sources"] = excluded
        assert fact_task(client)(context)["reason_code"] == "sources_unavailable"
    assert client.calls == []


def test_visible_sources_are_used_despite_other_exclusions_and_raw_proposal_kept():
    corpus, case, context, proposal = example()
    context["excluded_sources"] = [dict(document_id="other", reason="wrong_security")]
    client = Reply(proposal)
    task = fact_task(client)
    answer = task(context)
    assert len(client.calls) == 1 and all(score_answer(answer, case, corpus).values())
    assert json.loads(task.raw_responses[0]["raw_response"]) == proposal
    assert task.decisions[0]["source"] == "model_proposal"
    prompt = client.calls[0][0]["content"]
    assert "逐字" in prompt and "换行" in prompt
    assert '"start"' not in prompt and '"end"' not in prompt
    assert "gold" not in client.calls[0][1]["content"]


@pytest.mark.parametrize("mutation", ["identity", "offsets", "abstention_payload"])
def test_malformed_or_inconsistent_proposal_is_rejected(mutation):
    _, _, context, proposal = example()
    if mutation == "identity":
        proposal["symbol"] = "999999.SZ"
    elif mutation == "offsets":
        proposal["citations"][0]["start"] = 0
    else:
        proposal["status"] = "insufficient"
        proposal["reason_code"] = "period_not_present"
    with pytest.raises(ValueError):
        resolve_proposal(proposal, context)


def test_invalid_raw_response_kept_before_json_parse():
    _, _, context, _ = example()

    class Invalid:
        def chat(self, messages):
            return "{invalid response"

    task = fact_task(Invalid())
    with pytest.raises(json.JSONDecodeError):
        task(context)
    assert task.raw_responses[0]["raw_response"] == "{invalid response"


def test_captured_live_percentage_format_is_not_silently_corrected():
    corpus, case, context, _ = example("pingan-npl-2024")
    report = json.loads(
        Path("evaluations/turaq/quote_task/results/live-quote-only-2026-10-24.json").read_text(
            encoding="utf-8"
        )
    )
    from app.research_eval import digest

    response = next(r for r in report["raw_responses"] if r["context_sha256"] == digest(context))
    proposal = json.loads(response["raw_response"])
    answer, check = resolve_proposal(proposal, context)
    assert proposal["value"] == answer["value"] == "1.06%"
    assert answer["unit"] == "%" and check["state"] == "quote_located"
    scores = score_answer(answer, case, corpus)
    assert scores["evidence"] and not scores["value"]
    assert answer == next(r["output"] for r in report["cases"] if r["id"] == case["id"])
