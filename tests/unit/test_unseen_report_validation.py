"""Pre-registered transfer evaluation checks, without network, model or database."""

import hashlib
from copy import deepcopy
from types import SimpleNamespace

import pytest


def sample(tmp_path):
    (tmp_path / "algorithm.py").write_text("frozen", encoding="utf-8")
    sha = hashlib.sha256(b"frozen").hexdigest()
    specs = [dict(metric=f"metric{i}", period="2024") for i in range(8)]
    protocol = dict(
        issuers=[dict(id="a", symbol="000001.SZ"), dict(id="b", symbol="000002.SZ")],
        report_period="2024",
        selected_pages=list(range(1, 33)),
        factual_specs=specs,
        factual_requests=16,
        boundary_requests=6,
        total_requests=22,
        algorithm_sha256={"algorithm.py": sha},
        prior_sha256={},
    )
    docs, cases, gold, fixtures = {}, [], {}, {}
    for issuer in protocol["issuers"]:
        key, symbol = issuer["id"], issuer["symbol"]
        docs[key] = dict(
            id=key,
            symbol=symbol,
            report_period="2024",
            published_date="2025-03-31",
            selected_pages=list(range(1, 33)),
            url="https://example.invalid/report.pdf",
            pdf_sha256="a" * 64,
            text_pages=[dict(page=i, text="金额 123") for i in range(1, 33)],
        )
        for i, spec in enumerate(specs):
            case = dict(
                id=f"{key}-{i}",
                question="source fact",
                **spec,
                symbol=symbol,
                report_period="2024",
                owner="pilot-a",
                as_of="2025-04-15",
                document_ids=[key],
                context_pages={key: list(range(1, 33))},
                validation_kind="fact",
            )
            cases.append(case)
            anchor = dict(document_id=key, page=1, start=3, end=6, quote="123")
            gold[case["id"]] = dict(
                status="supported", value="123", unit="元", allowed_anchors=[anchor]
            )
            fixtures[case["id"]] = dict(
                status="supported",
                symbol=symbol,
                **spec,
                value="123",
                unit="元",
                reason_code=None,
                citations=[anchor],
            )
    kinds = (
        "future_period",
        "before_publication",
        "wrong_security",
        "wrong_report",
        "other_owner",
        "withdrawn",
    )
    for i, kind in enumerate(kinds):
        case = dict(
            deepcopy(cases[0]), id=f"boundary-{i}", validation_kind="boundary", boundary_kind=kind
        )
        reason = "sources_unavailable"
        if kind == "future_period":
            case["period"], reason = "2026", "period_not_present"
        elif kind == "before_publication":
            case["as_of"], reason = "2025-03-31", "not_yet_public"
        elif kind == "wrong_security":
            case["symbol"], reason = "999999.SH", "wrong_security"
        elif kind == "wrong_report":
            case["report_period"] = "2023"
        elif kind == "other_owner":
            case["owner"] = "other-user"
        else:
            case["withdrawn"] = True
        cases.append(case)
        gold[case["id"]] = dict(status="insufficient", reason_code=reason)
        fixtures[case["id"]] = dict(
            status="insufficient",
            symbol=case["symbol"],
            metric=case["metric"],
            period=case["period"],
            value=None,
            unit=None,
            citations=[],
            reason_code=reason,
        )
    return SimpleNamespace(
        protocol=protocol,
        corpus=dict(documents=docs, cases=cases, gold=gold),
        fixtures=fixtures,
        root=tmp_path,
    )


def test_protocol_accepts_exact_predeclared_cases_sources_and_reference_quotes(tmp_path):
    from app.unseen_report_validation import verify_protocol

    s = sample(tmp_path)
    assert verify_protocol(s.corpus, s.protocol, s.fixtures, repository_root=s.root) == dict(
        factual_requests=16, supported_facts=16, boundary_requests=6, indexed_pages=64
    )


@pytest.mark.parametrize(
    "mutation", ["algorithm", "prefix", "metric", "anchor", "fixture", "boundary"]
)
def test_protocol_rejects_drift_or_inconsistent_reference_data(tmp_path, mutation):
    from app.unseen_report_validation import verify_protocol

    s = sample(tmp_path)
    if mutation == "algorithm":
        (tmp_path / "algorithm.py").write_text("tuned after freeze", encoding="utf-8")
    elif mutation == "prefix":
        s.corpus["documents"]["a"]["selected_pages"][-1] = 40
    elif mutation == "metric":
        s.corpus["cases"][0]["metric"] = "replacement easy metric"
    elif mutation == "anchor":
        s.corpus["gold"]["a-0"]["allowed_anchors"][0]["quote"] = "999"
    elif mutation == "fixture":
        s.fixtures["a-0"]["value"] = "999"
    else:
        s.corpus["cases"][-1]["withdrawn"] = False
    with pytest.raises(ValueError):
        verify_protocol(s.corpus, s.protocol, s.fixtures, repository_root=s.root)


@pytest.mark.parametrize(
    "change,expected",
    [
        ({}, True),
        ({"hits": 11}, False),
        ({"denominator": 15}, False),
        ({"recorded": 21}, False),
        ({"errors": 1}, False),
        ({"scope": False}, False),
        ({"hits": 17}, False),
    ],
)
def test_live_gate_keeps_all_new_cases_and_supported_denominator(change, expected):
    from app.unseen_report_validation import transfer_gate

    options = dict(hits=12, denominator=16, recorded=22, errors=0, scope=True)
    options.update(change)
    summary = dict(
        requested=22,
        recorded=options["recorded"],
        errors=options["errors"],
        scope_boundaries_empty=options["scope"],
        evidence=dict(at3=options["hits"], denominator=options["denominator"]),
    )
    assert transfer_gate(summary, supported_count=16) is expected


def test_real_frozen_set_contains_only_new_issuers_and_fixed_prefix():
    from app.openviking_benchmark import resources_for
    from app.unseen_report_validation import load_transfer_corpus

    corpus, protocol, counts = load_transfer_corpus()
    assert {doc["symbol"] for doc in corpus["documents"].values()} == {"000333.SZ", "600036.SH"}
    assert counts == dict(
        factual_requests=16, supported_facts=16, boundary_requests=6, indexed_pages=64
    )
    resources = resources_for(corpus)
    assert len(resources) == 64
    assert all(1 <= r["page"] <= 32 for r in resources)
    assert len(corpus["cases"]) == protocol["total_requests"] == 22


@pytest.mark.parametrize(
    "case_id,wrong_start", [("cmb-2024-fact-06", 565), ("cmb-2024-fact-07", 815)]
)
def test_repeated_same_page_values_require_the_registered_metric_position(case_id, wrong_start):
    from app.unseen_report_validation import load_transfer_corpus, located_unit_evidence
    from scripts.run_table_hybrid_eval import unit_evidence

    corpus, _, _ = load_transfer_corpus()
    gold = corpus["gold"][case_id]
    anchor = gold["allowed_anchors"][0]
    quote = anchor["quote"]
    source = corpus["documents"]["cmb-2024"]["text_pages"][13]["text"]
    assert source[wrong_start : wrong_start + len(quote)] == quote
    wrong = dict(
        document_id="cmb-2024",
        page=14,
        resource_id="same-page",
        parts=[dict(text=quote, char_start=wrong_start, char_end=wrong_start + len(quote))],
    )
    assert unit_evidence(gold, [wrong]) == dict(at1=True, at3=True)
    assert located_unit_evidence(gold, [wrong]) == dict(at1=False, at3=False)
    correct = deepcopy(wrong)
    correct["parts"][0].update(char_start=anchor["start"], char_end=anchor["end"])
    assert located_unit_evidence(gold, [wrong, correct]) == dict(at1=False, at3=True)
    assert located_unit_evidence(gold, [wrong] * 3 + [correct]) == dict(at1=False, at3=False)


def test_location_metrics_do_not_join_parts_or_trust_inconsistent_coordinates():
    from app.unseen_report_validation import located_unit_evidence

    gold = dict(
        status="supported",
        allowed_anchors=[dict(document_id="d", page=1, start=10, end=14, quote="5.66")],
    )
    unit = dict(
        document_id="d",
        page=1,
        parts=[
            dict(text="5.", char_start=10, char_end=12),
            dict(text="66", char_start=12, char_end=14),
        ],
    )
    assert located_unit_evidence(gold, [unit]) == dict(at1=False, at3=False)
    unit["parts"] = [dict(text="5.66", char_start=10, char_end=99)]
    assert located_unit_evidence(gold, [unit]) == dict(at1=False, at3=False)


def test_transfer_runner_uses_location_metrics_for_the_actual_gate_summary(tmp_path):
    from app.openviking_benchmark import resources_for
    from app.unseen_report_validation import load_transfer_corpus
    from scripts.run_unseen_report_eval import measure_retrieval

    corpus, _, _ = load_transfer_corpus()
    case = next(c for c in corpus["cases"] if c["id"] == "cmb-2024-fact-06")
    corpus = dict(corpus, cases=[case])
    resources = resources_for(corpus)
    page = next(r for r in resources if r["page"] == 14)
    wrong = dict(
        resource_id=page["id"],
        document_id="cmb-2024",
        page=14,
        parts=[dict(text="5.66", char_start=565, char_end=569)],
    )
    retriever = SimpleNamespace(find=lambda *args, **kwargs: [wrong])
    report = {}
    measure_retrieval(retriever, resources, corpus, report, tmp_path / "result.json")
    for mode in ("lexical", "hybrid"):
        assert report["retrieval"][mode]["summary"]["evidence"]["at3"] == 0
        assert report["retrieval"][mode]["rows"][0]["substring_evidence"]["at3"] is True
