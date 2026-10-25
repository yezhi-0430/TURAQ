"""Application wiring, literal source selection and separate unit-label explanations."""

import json
from copy import deepcopy

import pytest


def context():
    return dict(
        question="提取2024年基本每股收益",
        symbol="000001.SZ",
        metric="基本每股收益",
        period="2024",
        as_of="2025-05-01",
        excluded_sources=[],
        documents=[
            dict(
                id="doc",
                symbol="000001.SZ",
                pages=[
                    dict(
                        page=1,
                        text=(
                            "2024年 单位：人民币元\n每股计（人民币元）\n"
                            "基本每股收益 5.66 5.63\n营业收入 100.00 90.00\n"
                        ),
                    )
                ],
            )
        ],
    )


class Model:
    def __init__(self):
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        payload = json.loads(messages[1]["content"])
        ref = next(e for e in payload["evidence"] if "基本每股收益 5.66" in e["text"])
        return json.dumps(
            dict(
                status="supported",
                symbol=payload["symbol"],
                metric=payload["metric"],
                period=payload["period"],
                value="5.66",
                unit="元/股",
                reason_code=None,
                evidence_ids=[ref["id"]],
            ),
            ensure_ascii=False,
        )


def test_source_selector_is_bounded_deterministic_literal_and_needs_no_embedding(monkeypatch):
    import builtins

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("torch", "sentence_transformers")):
            pytest.fail("selection must not require an embedding runtime")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    from app.analysis.evidence import select_evidence

    ctx = context()
    before = deepcopy(ctx)
    fragments = select_evidence(ctx)
    assert fragments and fragments == select_evidence(ctx) and ctx == before
    assert len(fragments) <= 20 and sum(len(f["text"]) for f in fragments) <= 4800
    source = ctx["documents"][0]["pages"][0]["text"]
    for f in fragments:
        assert f["document_id"] == "doc" and f["page"] == 1
        assert source[f["char_start"] : f["char_end"]] == f["text"]
    assert any("基本每股收益 5.66" in f["text"] for f in fragments)


def test_application_factory_uses_ids_and_excludes_reference_annotations():
    from app.analysis.evidence import application_task

    client, ctx = Model(), context()
    ctx["gold"] = "PRIVATE_REFERENCE_SENTINEL"
    task = application_task(client)
    output = task(ctx)
    assert output["value"] == "5.66" and output["unit"] == "元/股"
    assert output["citations"] and len(client.calls) == 1
    assert "PRIVATE_REFERENCE_SENTINEL" not in str(client.calls)
    assert "evidence_ids" in client.calls[0][0]["content"]
    assert len(task.decisions) == 1


@pytest.mark.parametrize("reason", ["wrong_security", "not_yet_public"])
def test_excluded_sources_make_no_model_request(reason):
    from app.analysis.evidence import application_task

    ctx, model = context(), Model()
    ctx.update(documents=[], excluded_sources=[dict(document_id="doc", reason=reason)])
    answer = application_task(model)(ctx)
    assert answer["status"] == "insufficient" and answer["reason_code"] == reason
    assert model.calls == []


def test_no_relevant_source_declines_without_a_model_request():
    from app.analysis.evidence import application_task

    ctx, model = context(), Model()
    ctx["documents"][0]["pages"][0]["text"] = "无相关资料。"
    ctx.update(question="carbon", metric="carbon", period="2099")
    answer = application_task(model)(ctx)
    assert answer["reason_code"] == "evidence_not_found" and model.calls == []


def note_inputs(unit="元/股", metric="基本每股收益", reference_unit="元"):
    row = dict(
        output=dict(status="supported", value="5.66", unit=unit),
        scores=dict(identity=True, evidence=True, abstention=True, value=False, contract=False),
        task_error=None,
        scoring_error=None,
    )
    return row, dict(metric=metric), dict(status="supported", value="5.66", unit=reference_unit)


@pytest.mark.parametrize(
    "unit,metric,reference,reason",
    [
        ("元/股", "基本每股收益", "元", "eps_per_share"),
        ("元", "稀释每股收益", "元／股", "eps_per_share"),
        ("人民币元", "营业收入", "元", "currency_label"),
        ("元／股", "基本每股收益", "元/股", "slash_typography"),
    ],
)
def test_equivalent_unit_metadata_never_changes_strict_scores_or_raw_answer(
    unit, metric, reference, reason
):
    from app.analysis.units import unit_note

    args = note_inputs(unit, metric, reference)
    before = deepcopy(args)
    note = unit_note(*args)
    assert note["status"] == "equivalent" and note["reason"] == reason
    assert note["model_unit"] == unit and note["reference_unit"] == reference
    assert args == before and args[0]["scores"]["contract"] is False


@pytest.mark.parametrize(
    "unit,metric,reference",
    [
        ("元/股", "营业收入", "元"),
        ("百万元", "营业收入", "元"),
        ("千元", "基本每股收益", "元"),
        ("%", "基本每股收益", "元"),
        ("港元", "营业收入", "元"),
    ],
)
def test_magnitude_currency_and_metric_mismatches_are_not_equivalent(unit, metric, reference):
    from app.analysis.units import unit_note

    assert unit_note(*note_inputs(unit, metric, reference))["status"] == "different"


@pytest.mark.parametrize(
    "mutation",
    [
        "value",
        "commas",
        "percent",
        "identity",
        "evidence",
        "abstention",
        "insufficient",
        "task_error",
    ],
)
def test_unit_note_cannot_rescue_other_financial_or_pipeline_errors(mutation):
    from app.analysis.units import unit_note

    row, case, reference = note_inputs()
    if mutation == "value":
        row["output"]["value"] = "56.6"
    elif mutation == "commas":
        row["output"]["value"] = "5,66"
    elif mutation == "percent":
        row["output"]["value"] = "5.66%"
    elif mutation in {"identity", "evidence", "abstention"}:
        row["scores"][mutation] = False
    elif mutation == "insufficient":
        row["output"]["status"] = "insufficient"
    else:
        row["task_error"] = "ValueError"
    assert unit_note(row, case, reference) is None


def test_evaluation_endpoint_core_uses_v2_and_keeps_unit_equivalence_separate(monkeypatch):
    from types import SimpleNamespace

    from app.analysis import evaluation

    ctx = context()
    page = ctx["documents"][0]["pages"][0]
    start = page["text"].index("5.66")
    case = dict(
        id="eps",
        **{k: ctx[k] for k in ("question", "symbol", "metric", "period", "as_of")},
        document_ids=["doc"],
        context_pages={"doc": [1]},
    )
    doc = dict(
        id="doc",
        symbol=ctx["symbol"],
        report_period="2024",
        published_date="2025-01-01",
        url="https://example.com/public.pdf",
        pdf_sha256="a" * 64,
        text_pages=[page],
    )
    reference = dict(
        status="supported",
        value="5.66",
        unit="元",
        allowed_anchors=[dict(document_id="doc", page=1, start=start, end=start + 4, quote="5.66")],
    )
    data = dict(documents={"doc": doc}, cases=[case], gold={"eps": reference}, manifest={})
    monkeypatch.setattr(evaluation, "corpus", lambda: data)
    monkeypatch.setattr(
        evaluation,
        "benchmark_for",
        lambda _: dict(available=True, document_id="doc", scope="synthetic endpoint wiring"),
    )
    admission = SimpleNamespace(
        settings=SimpleNamespace(model_provider="qwen"),
        remaining=lambda: 30,
        model_attempt_usage=[],
    )
    result = evaluation.evaluate_document("a" * 64, Model(), admission)
    assert result["requested"] == result["scored"] == 1
    assert result["task_version"] == "source-evidence-ids-v2"
    assert result["evidence_mode"] == "document-bm25-source-spans-v1"
    assert result["scorer_version"] == "public-fact-citation-v1"
    assert result["passed"] == 0 and result["acceptance_ok"] is False
    row = result["cases"][0]
    assert row["output"]["unit"] == "元/股" and row["scores"]["value"] is False
    assert row["unit_note"]["status"] == "equivalent"


def test_registered_application_fact_contexts_retain_allowed_source_positions():
    from app.analysis.evidence import select_evidence
    from app.report_evidence_eval import build_context, load_corpus

    corpus = load_corpus()
    checked = 0
    for case in corpus["cases"]:
        reference = corpus["gold"][case["id"]]
        if reference["status"] != "supported":
            continue
        fragments = select_evidence(build_context(case, corpus))
        assert any(
            f["document_id"] == a["document_id"]
            and f["page"] == a["page"]
            and f["char_start"] <= a["start"] < a["end"] <= f["char_end"]
            for f in fragments
            for a in reference["allowed_anchors"]
        ), case["id"]
        checked += 1
    assert checked == 7


def test_saved_eps_real_response_keeps_strict_failure_and_adds_only_unit_note():
    from pathlib import Path

    from app.analysis.units import unit_note
    from app.report_evidence_eval import load_corpus, score_answer

    corpus = load_corpus(Path("evaluations/turaq/pdf-cmap-v2/regression"))
    report = json.loads(
        Path("evaluations/turaq/evidence-id-v2/regression-live-v2.json").read_text(encoding="utf-8")
    )
    row = next(r for r in report["answers"] if r["id"] == "cmb-2024-fact-06")
    case = next(c for c in corpus["cases"] if c["id"] == row["id"])
    before = deepcopy(row)
    scores = score_answer(row["output"], case, corpus)
    assert scores["evidence"] and not scores["value"]
    note = unit_note(row, case, corpus["gold"][row["id"]])
    assert note["status"] == "equivalent" and note["reason"] == "eps_per_share"
    assert row == before and row["scores"]["contract"] is False
