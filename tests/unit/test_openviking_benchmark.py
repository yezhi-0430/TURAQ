from copy import deepcopy

import pytest

from app.openviking_benchmark import (
    EXPANDED,
    eligible,
    evidence_metrics,
    load_expanded,
    make_task,
    resources_for,
    summarize,
)


def test_frozen_expansion_has_real_old_report_distractors_and_twenty_cases():
    corpus = load_expanded()
    assert corpus["root"] == EXPANDED
    assert len(corpus["documents"]) == 3
    assert len(corpus["cases"]) == 20
    resources = resources_for(corpus)
    assert len(resources) == 48
    assert {r["report_period"] for r in resources} == {"2023", "2024"}
    assert len({r["page"] for r in resources if r["document_id"] == "moutai-2023"}) == 16
    assert all("gold" not in r and "value" not in r for r in resources)


def test_scope_filters_owner_report_security_disclosure_and_active_version():
    corpus = load_expanded()
    resources = resources_for(corpus)
    case = corpus["cases"][0]
    selected = eligible(resources, case)
    assert len(selected) == 16
    assert all(r["document_id"] in case["document_ids"] for r in selected)
    for changed in (
        dict(owner="other-user"),
        dict(as_of="2000-01-01"),
        dict(report_period="2099"),
        dict(symbol="NO.SUCH"),
    ):
        assert eligible(resources, dict(case, **changed)) == []
    assert eligible([dict(r, active=False) for r in resources], case) == []


def test_top_one_is_distinct_from_top_three_and_hidden_page_quote_does_not_count():
    gold = dict(status="supported", allowed_anchors=[dict(document_id="d", page=5, quote="123.45")])
    distractor = dict(document_id="d", page=5, text="提及营业收入，但无数值")
    correct = dict(document_id="d", page=5, text="营业收入 123.45")
    assert evidence_metrics(gold, [distractor, correct]) == {"at1": False, "at3": True}
    assert evidence_metrics(gold, [distractor]) == {"at1": False, "at3": False}
    assert evidence_metrics(dict(status="insufficient"), [correct]) == {"at1": None, "at3": None}


def test_model_sees_retrieved_fragment_only_but_quote_coordinates_use_original_page():
    corpus = load_expanded()
    case = corpus["cases"][0]
    doc = corpus["documents"][case["document_ids"][0]]
    gold = corpus["gold"][case["id"]]
    anchor = gold["allowed_anchors"][0]
    page = doc["text_pages"][anchor["page"] - 1]["text"]
    fragment = dict(document_id=doc["id"], page=anchor["page"], text=anchor["quote"])
    import json

    captured = []

    class Model:
        def chat(self, messages):
            captured.append(json.loads(messages[1]["content"]))
            return json.dumps(
                dict(
                    status="supported",
                    symbol=case["symbol"],
                    metric=case["metric"],
                    period=case["period"],
                    value=gold["value"],
                    unit=gold["unit"],
                    reason_code=None,
                    citations=[
                        dict(document_id=doc["id"], page=anchor["page"], quote=anchor["quote"])
                    ],
                )
            )

    answer = make_task(Model(), case, corpus, [fragment])()
    assert captured[0]["documents"][0]["pages"][0]["text"] == anchor["quote"]
    assert "gold" not in captured[0]
    citation = answer["citations"][0]
    assert page[citation["start"] : citation["end"]] == anchor["quote"]
    assert citation["start"] == anchor["start"]


def test_quote_from_unseen_part_of_retrieved_page_is_rejected():
    corpus = load_expanded()
    case = corpus["cases"][0]
    anchor = corpus["gold"][case["id"]]["allowed_anchors"][0]
    import json

    class Model:
        def chat(self, messages):
            return json.dumps(
                dict(
                    status="supported",
                    symbol=case["symbol"],
                    metric=case["metric"],
                    period=case["period"],
                    value="1",
                    unit="元",
                    reason_code=None,
                    citations=[
                        dict(
                            document_id=anchor["document_id"],
                            page=anchor["page"],
                            quote=anchor["quote"],
                        )
                    ],
                )
            )

    with pytest.raises(ValueError, match="unseen"):
        make_task(
            Model(),
            case,
            corpus,
            [
                dict(
                    document_id=anchor["document_id"],
                    page=anchor["page"],
                    text="仅标题，未提供金标数值",
                )
            ],
        )()


def test_empty_retrieval_never_calls_model_or_fabricates_a_supported_answer():
    corpus = load_expanded()
    case = corpus["cases"][0]

    class Model:
        def chat(self, messages):
            raise AssertionError("empty evidence must not call provider")

    answer = make_task(Model(), case, corpus, [])()
    assert answer["status"] == "insufficient"
    assert answer["value"] is None and not answer["citations"]


def test_summary_keeps_missing_and_failed_cases_in_the_denominator():
    rows = [dict(id="a", scores=dict(contract=True)), dict(id="b", task_error="TimeoutError")]
    summary = summarize(rows, ["a", "b", "c"])
    assert summary["requested"] == 3
    assert summary["passed"] == 1
    assert summary["scored"] == 1
    assert summary["missing"] == ["c"]
    assert summary["integrity_ok"] is False


def test_dataset_mutation_is_detected(tmp_path):
    corpus = load_expanded()
    manifest = deepcopy(corpus["manifest"])
    assert manifest["files"]["gold.json"]
    # The existing strict corpus loader validates every PDF, page and gold fingerprint.
    from app.report_evidence_eval import load_corpus

    (tmp_path / "manifest.json").write_text(__import__("json").dumps(manifest))
    with pytest.raises((FileNotFoundError, ValueError)):
        load_corpus(tmp_path)


def test_expanded_fixture_is_valid_under_the_original_strict_scorer():
    from app.report_evidence_eval import read_json, score_answer

    corpus = load_expanded()
    answers = read_json(EXPANDED / "fixture_answers.json")
    assert all(all(score_answer(answers[c["id"]], c, corpus).values()) for c in corpus["cases"])


def test_model_duplicate_json_keys_are_rejected():
    corpus = load_expanded()
    case = corpus["cases"][0]
    import json

    raw = json.loads((EXPANDED / "fixture_answers.json").read_text(encoding="utf-8"))[case["id"]]
    for citation in raw["citations"]:
        citation.pop("start")
        citation.pop("end")

    class Model:
        def chat(self, messages):
            return '{"value":"0",' + json.dumps(raw)[1:]

    fragment = dict(
        document_id=raw["citations"][0]["document_id"],
        page=raw["citations"][0]["page"],
        text=raw["citations"][0]["quote"],
    )
    with pytest.raises(ValueError, match="duplicate"):
        make_task(Model(), case, corpus, [fragment])()


def test_chroma_comparator_uses_existing_research_similarity_gate_and_common_scope():
    from app.openviking_benchmark import ChromaComparator

    corpus = load_expanded()
    case = corpus["cases"][0]
    resource = eligible(resources_for(corpus), case)[0]
    calls = []

    class RAG:
        def search(self, query, **kwargs):
            calls.append(kwargs)
            return dict(
                success=True,
                results=[
                    dict(text="相关片段", distance=0.2, metadata=dict(resource_id=resource["id"])),
                    dict(
                        text="低相关片段", distance=0.8, metadata=dict(resource_id=resource["id"])
                    ),
                ],
            )

    baseline = ChromaComparator(RAG(), [resource])
    found = baseline.find(case)
    assert [f["text"] for f in found] == ["相关片段"]
    assert calls[0]["filter_metadata"] == {"resource_id": {"$in": [resource["id"]]}}
    assert calls[0]["n_results"] == 3


def test_failed_model_response_still_attributes_its_usage_to_the_engine(monkeypatch):
    from scripts import run_openviking_benchmark as bench

    corpus = load_expanded()
    case = corpus["cases"][0]
    anchor = corpus["gold"][case["id"]]["anchor"]
    fragment = dict(document_id=anchor["document_id"], page=anchor["page"], text=anchor["quote"])
    monkeypatch.setattr(bench.runtime, "save", lambda report: None)

    class Gate:
        records = []

        def snapshot(self):
            return {"records": self.records.copy()}

    gate = Gate()

    class Model:
        def chat(self, messages):
            gate.records.append(dict(kind="chat", usage=dict(total_tokens=17)))
            raise RuntimeError("provider-details-not-for-report")

    report = {"engines": {"chroma_bge": []}}
    row = bench.record_case("chroma_bge", case, corpus, lambda: [fragment], Model(), report, gate)
    assert row["task_error"] == "RuntimeError"
    assert row["model_tokens"] == 17


def test_existing_complete_chroma_page_is_reused_but_partial_page_is_not_assumed_complete():
    from app.openviking_benchmark import index_chroma

    resource = resources_for(load_expanded())[0]

    class Collection:
        def get(self, **kwargs):
            return {
                "metadatas": [
                    dict(resource_id=resource["id"], chunk_index=0, total_chunks=2),
                    dict(resource_id=resource["id"], chunk_index=1, total_chunks=2),
                ]
            }

    class RAG:
        collection = Collection()

        def add_text(self, *args, **kwargs):
            raise AssertionError("complete page should be reused")

    assert index_chroma(RAG(), [resource]) == {"reused_pages": 1, "indexed_pages": 0}

    class PartialCollection:
        def get(self, **kwargs):
            return {"metadatas": [dict(resource_id=resource["id"], chunk_index=0, total_chunks=2)]}

    partial = RAG()
    partial.collection = PartialCollection()
    with pytest.raises(ValueError, match="partial"):
        index_chroma(partial, [resource])


def test_withdrawal_invalidates_both_catalogs_even_when_native_index_still_returns_old_hit():
    from app.openviking_benchmark import ChromaComparator, invalidate_resource

    corpus = load_expanded()
    case = corpus["cases"][0]
    original = resources_for(corpus)
    bound = deepcopy(original)
    target = eligible(original, case)[0]

    class RAG:
        def search(self, *args, **kwargs):
            return dict(
                success=True,
                results=[
                    dict(
                        text="stale financial evidence",
                        distance=0,
                        metadata=dict(resource_id=target["id"]),
                    )
                ],
            )

    comparator = ChromaComparator(RAG(), original)
    assert len(comparator.find(case)) == 1
    invalidate_resource(target["id"], bound, comparator.resources)
    assert comparator.find(case) == []
    assert all(r["id"] != target["id"] for r in eligible(bound, case))


def test_bulk_import_uses_completed_task_result_not_only_initial_response():
    from app.openviking_benchmark import completed_import

    initial = {"task_id": "job-1", "status": "accepted"}
    final = {
        "status": "completed",
        "result": {
            "status": "success",
            "root_uri": "viking://user/pilot-a/resources/test",
            "errors": [],
        },
    }
    assert completed_import(initial, final)["root_uri"].endswith("/test")
    with pytest.raises(ValueError):
        completed_import(initial, {"status": "running"})
    with pytest.raises(ValueError):
        completed_import(initial, {"status": "completed", "result": {"errors": ["failed page"]}})


def test_recursive_agent_listing_can_use_rel_path_without_name():
    from app.openviking_benchmark import physical_page

    assert (
        physical_page(
            {
                "uri": "viking://user/pilot-a/resources/report/p0005/p0005.md",
                "rel_path": "p0005/p0005.md",
                "isDir": False,
            }
        )
        == 5
    )
    assert (
        physical_page({"uri": "viking://user/pilot-a/resources/report/p0005", "isDir": True})
        is None
    )
    assert physical_page({"uri": "viking://user/pilot-a/resources/report/.overview.md"}) is None
