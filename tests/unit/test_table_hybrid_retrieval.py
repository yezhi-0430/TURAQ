"""Synthetic source/ranking regressions; no database, model runtime, or gold."""

from types import SimpleNamespace

import pytest

TABLE = (
    "示例股份 2024年年度报告\n主要会计数据\n单位：元 币种：人民币\n"
    "项目 2024年 2023年\n调整后 调整前\n"
    "营业收入 1,234.56 1,000.00\n"
    "归属于上市公\n司股东的净利 200.00 180.00\n润\n"
    "经营活动产生\n的现金流量净 345.67 123.45\n额\n"
    "分季度数据\n单位：元\n第一季度 第二季度 第三季度 第四季度\n"
    "营业收入 12.00 23.00 34.00 45.00\n尾句没有标点"
)


def test_table_units_keep_wrapped_labels_headers_and_original_coordinates():
    from app.rag.table_chunks import table_units

    units = table_units(TABLE)
    rows = [unit for unit in units if unit["kind"] == "table_row"]
    profit = next(unit for unit in rows if "200.00" in unit["body"]["text"])
    assert "归属于上市公\n司股东的净利" in profit["body"]["text"]
    assert profit["body"]["text"].rstrip().endswith("润")
    header = "".join(p["text"] for p in profit["headers"])
    assert "单位：元" in header and "2024年 2023年" in header and "调整后" in header
    quarter = next(unit for unit in rows if "34.00" in unit["body"]["text"])
    assert "第三季度" in "".join(p["text"] for p in quarter["headers"])
    covered = set()
    for unit in units:
        assert len(unit["body"]["text"]) <= 500
        assert sum(len(part["text"]) for part in unit["headers"]) <= 800
        for part in [unit["body"], *unit["headers"]]:
            assert part["text"] == TABLE[part["char_start"] : part["char_end"]]
        covered.update(range(unit["body"]["char_start"], unit["body"]["char_end"]))
    assert all(i in covered for i, c in enumerate(TABLE) if not c.isspace())


def test_two_tables_do_not_attach_the_first_table_period_to_the_second():
    from app.rag.table_chunks import table_units

    text = (
        "单位：元\n项目 2024年 2023年\n营业收入 100.00 80.00\n"
        "单位：百万元\n项目 2022年 2021年\n营业收入 20.00 10.00\n"
    )
    unit = next(
        u for u in table_units(text) if u["kind"] == "table_row" and "20.00" in u["body"]["text"]
    )
    header = "".join(h["text"] for h in unit["headers"])
    assert "百万元" in header and "2022年" in header
    assert "2024年" not in header


@pytest.mark.parametrize("text", ["", " \n\t", "无标点尾句" * 100, "指标 " + "1" * 1200])
def test_empty_and_unstructured_text_is_bounded_and_preserved(text):
    from app.rag.table_chunks import table_units

    units = table_units(text)
    covered = set()
    for unit in units:
        p = unit["body"]
        assert p["text"] == text[p["char_start"] : p["char_end"]]
        assert len(p["text"]) <= 500
        covered.update(range(p["char_start"], p["char_end"]))
    assert all(i in covered for i, c in enumerate(text) if not c.isspace())


def embedding_service():
    return SimpleNamespace(
        embed_documents=lambda texts: [[1.0, 0.1] for _ in texts],
        embed_query=lambda text: [1.0, 0.1],
    )


def resources():
    return [
        dict(id="allowed", document_id="doc-a", page=5, text=TABLE),
        dict(
            id="other",
            document_id="doc-b",
            page=1,
            text="单位：元\n项目 2024年 2023年\n归属于上市公司股东的净利润 999.00 888.00\n",
        ),
    ]


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_scoped_ranker_prefers_wrapped_metric_row_and_exposes_separate_parts(mode):
    from app.rag.hybrid import HybridRetriever

    retriever = HybridRetriever(resources(), embedding_service())
    result = retriever.find("请提取2023年调整后的归母净利润", {"allowed"}, mode=mode)
    assert result and "200.00" in result[0]["body"]["text"]
    assert all(unit["resource_id"] == "allowed" for unit in result)
    assert result[0]["parts"][0]["text"] != result[0]["search_text"]
    for unit in result:
        assert len(unit["parts"]) >= 1
        assert all(p["text"] == TABLE[p["char_start"] : p["char_end"]] for p in unit["parts"])
    assert sum(len(p["text"]) for u in result for p in u["parts"]) <= 4800
    assert len(result) <= 3


def test_scope_gates_run_before_either_query_ranker():
    from app.rag.hybrid import HybridRetriever

    service = embedding_service()
    service.embed_query = lambda _: pytest.fail("query must not run for an empty scope")
    retriever = HybridRetriever(resources(), service)
    assert retriever.find("净利润", set()) == []
    with pytest.raises(ValueError, match="scope"):
        retriever.find("净利润", {"nonexistent"})
    with pytest.raises(ValueError, match="duplicate"):
        HybridRetriever(resources() * 2, service)


def test_ranking_is_stable_and_limits_are_enforced():
    from app.rag.hybrid import HybridRetriever

    retriever = HybridRetriever(resources(), embedding_service())
    first = retriever.find("营业收入", {"allowed"})
    assert first == retriever.find("营业收入", {"allowed"})
    assert len(retriever.find("营业收入", {"allowed"}, limit=1)) <= 1
    for limit in (0, -1, 4, True):
        with pytest.raises(ValueError):
            retriever.find("营业收入", {"allowed"}, limit=limit)
    with pytest.raises(ValueError):
        retriever.find("营业收入", {"allowed"}, mode="unknown")


@pytest.mark.parametrize("vector", [[0.0, 0.0], [float("nan"), 0.0], [float("inf"), 0.0]])
def test_invalid_dense_vectors_fail_closed(vector):
    from app.rag.hybrid import HybridRetriever

    service = embedding_service()
    service.embed_documents = lambda texts: [vector for _ in texts]
    with pytest.raises(ValueError, match="vector"):
        HybridRetriever(resources(), service)


def test_query_vector_cannot_fabricate_a_semantic_score():
    from app.rag.hybrid import HybridRetriever

    service = embedding_service()
    service.embed_query = lambda _: [0.0, 0.0]
    retriever = HybridRetriever(resources(), service)
    assert retriever.find("营业收入", {"allowed"}) == []
    assert retriever.find("营业收入", {"allowed"}, mode="lexical")


def test_unit_metrics_count_ranked_units_without_stitching_quotes():
    from scripts.run_table_hybrid_eval import fragments_for, unit_evidence

    gold = dict(
        status="supported", allowed_anchors=[dict(document_id="d", page=2, quote="收入 123")]
    )
    first = dict(
        document_id="d",
        page=2,
        resource_id="r",
        parts=[
            dict(text="收入 ", char_start=0, char_end=3),
            dict(text="123", char_start=9, char_end=12),
        ],
    )
    correct = dict(
        document_id="d",
        page=2,
        resource_id="r",
        parts=[dict(text="收入 123", char_start=20, char_end=26)],
    )
    assert unit_evidence(gold, [first]) == dict(at1=False, at3=False)
    assert unit_evidence(gold, [first, correct]) == dict(at1=False, at3=True)
    fragments = fragments_for([first, correct, correct])
    assert len(fragments) == 3
    assert [f["text"] for f in fragments] == ["收入 ", "123", "收入 123"]
