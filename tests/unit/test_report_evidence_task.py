"""Synthetic provenance/output-contract regressions, with the original scorer."""

import json
from copy import deepcopy

import pytest

from app.report_evidence_eval import build_context, score_answer


def sample():
    text = "2024年 单位：元\n营业收入 1,234.50\n营业收入 1,234.50"
    start = text.rindex("营业收入")
    case = dict(
        id="fact",
        symbol="000001.SZ",
        metric="营业收入",
        period="2024",
        as_of="2025-02-01",
        document_ids=["doc"],
        context_pages={"doc": [1]},
        question="提取年度营业收入",
    )
    doc = dict(
        id="doc",
        symbol=case["symbol"],
        published_date="2025-01-01",
        report_period="2024",
        url="https://example.com/public.pdf",
        pdf_sha256="a" * 64,
        text_pages=[dict(page=1, text=text)],
    )
    anchor = dict(
        document_id="doc", page=1, start=start + len("营业收入 "), end=len(text), quote="1,234.50"
    )
    corpus = dict(
        documents={"doc": doc},
        gold={
            "fact": dict(status="supported", value="1234.50", unit="元", allowed_anchors=[anchor])
        },
    )
    fragment = dict(
        document_id="doc", page=1, char_start=start, char_end=len(text), text=text[start:]
    )
    proposal = dict(
        status="supported",
        symbol=case["symbol"],
        metric=case["metric"],
        period=case["period"],
        value="1234.50",
        unit="元",
        reason_code=None,
        evidence_ids=["e1"],
    )
    return corpus, case, build_context(case, corpus), [fragment], proposal


class Reply:
    def __init__(self, proposal):
        self.raw = json.dumps(proposal, ensure_ascii=False)
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return self.raw


def run(client, context, fragments):
    from app.report_evidence_task import evidence_task

    return evidence_task(client, context, fragments)


def test_selected_id_copies_exact_known_position_even_if_text_repeats():
    corpus, case, context, fragments, proposal = sample()
    original = deepcopy((context, fragments, proposal))
    client = Reply(proposal)
    answer = run(client, context, fragments)
    assert all(score_answer(answer, case, corpus).values())
    assert answer["citations"] == [
        dict(
            document_id="doc",
            page=1,
            start=fragments[0]["char_start"],
            end=fragments[0]["char_end"],
            quote=fragments[0]["text"],
        )
    ]
    assert (context, fragments, proposal) == original and len(client.calls) == 1
    payload = json.loads(client.calls[0][1]["content"])
    assert payload["evidence"][0]["id"] == "e1"
    assert payload["evidence"][0]["text"] == fragments[0]["text"]
    assert "documents" not in payload and "gold" not in payload
    schema = client.calls[0][0]["content"]
    assert '"quote"' not in schema and '"start"' not in schema and '"end"' not in schema
    assert "人民币" in schema and "千分位" in schema


@pytest.mark.parametrize(
    "value",
    ["1,234.50", "21.29%", "NaN", "Infinity", "1e3", " 1234.50", "+1234.50", "01.2", 1234.5, True],
)
def test_non_decimal_protocol_values_are_rejected_without_repair(value):
    _, _, context, fragments, proposal = sample()
    proposal["value"] = value
    client = Reply(proposal)
    with pytest.raises(ValueError):
        run(client, context, fragments)
    assert len(client.calls) == 1 and json.loads(client.raw)["value"] == value


@pytest.mark.parametrize("unit", ["人民币元", "人民币百万元", "元人民币", "unknown"])
def test_noncanonical_unit_labels_are_rejected_not_silently_converted(unit):
    _, _, context, fragments, proposal = sample()
    proposal["unit"] = unit
    with pytest.raises(ValueError):
        run(Reply(proposal), context, fragments)


@pytest.mark.parametrize(
    "bad",
    [
        "unknown",
        "duplicate",
        "empty",
        "extra_quote",
        "identity",
        "supported_reason",
        "missing_value",
        "insufficient_value",
    ],
)
def test_bad_identity_or_evidence_selection_is_rejected(bad):
    _, _, context, fragments, proposal = sample()
    if bad == "unknown":
        proposal["evidence_ids"] = ["e99"]
    elif bad == "duplicate":
        proposal["evidence_ids"] = ["e1", "e1"]
    elif bad == "empty":
        proposal["evidence_ids"] = []
    elif bad == "extra_quote":
        proposal["citations"] = [dict(quote="made up quotation", start=0)]
    elif bad == "identity":
        proposal["symbol"] = "600519.SH"
    elif bad == "supported_reason":
        proposal["reason_code"] = "evidence_not_found"
    elif bad == "missing_value":
        proposal["value"] = None
    else:
        proposal.update(status="insufficient", reason_code="evidence_not_found")
    with pytest.raises(ValueError):
        run(Reply(proposal), context, fragments)


@pytest.mark.parametrize(
    "bad",
    [
        "document",
        "page",
        "start",
        "end",
        "text",
        "bool_offset",
        "empty",
        "foreign_symbol",
        "too_long",
    ],
)
def test_unverified_source_spans_fail_before_any_model_call(bad):
    _, _, context, fragments, proposal = sample()
    f = fragments[0]
    if bad == "document":
        f["document_id"] = "other"
    elif bad == "page":
        f["page"] = 999
    elif bad == "start":
        f["char_start"] = -1
    elif bad == "end":
        f["char_end"] += 1
    elif bad == "text":
        f["text"] = f["text"].replace("1,234.50", "9,999.99")
    elif bad == "bool_offset":
        f["char_start"] = True
    elif bad == "empty":
        fragments = []
    elif bad == "foreign_symbol":
        context["documents"][0]["symbol"] = "600519.SH"
    else:
        context["documents"][0]["pages"][0]["text"] = "x" * 4801
        fragments = [dict(f, char_start=0, char_end=4801, text="x" * 4801)]
    client = Reply(proposal)
    with pytest.raises(ValueError):
        run(client, context, fragments)
    assert client.calls == []


def test_unknown_period_abstention_needs_no_citation_or_value():
    _, _, context, fragments, proposal = sample()
    proposal.update(
        status="insufficient",
        value=None,
        unit=None,
        reason_code="period_not_present",
        evidence_ids=[],
    )
    answer = run(Reply(proposal), context, fragments)
    assert answer["citations"] == [] and answer["value"] is None
    assert answer["reason_code"] == "period_not_present"


@pytest.mark.parametrize("field,value", [("value", "9999"), ("unit", "百万元")])
def test_source_ids_do_not_certify_wrong_financial_number_or_magnitude(field, value):
    corpus, case, context, fragments, proposal = sample()
    proposal[field] = value
    answer = run(Reply(proposal), context, fragments)
    scores = score_answer(answer, case, corpus)
    assert scores["evidence"] and not scores["value"]


def test_duplicate_input_spans_share_one_id_and_duplicate_json_keys_are_rejected():
    _, _, context, fragments, proposal = sample()
    client = Reply(proposal)
    run(client, context, fragments * 2)
    assert len(json.loads(client.calls[0][1]["content"])["evidence"]) == 1
    client.raw = client.raw.replace('"value": "1234.50"', '"value": "0", "value": "1234.50"')
    with pytest.raises(ValueError, match="duplicate"):
        run(client, context, fragments)
