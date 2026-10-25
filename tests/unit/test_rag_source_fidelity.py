"""Source preservation and metric semantics, without a model or database."""

import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from app.rag.chunker import TextChunker


@pytest.mark.parametrize("strategy", ["simple", "paragraph", "smart"])
def test_chunks_are_bounded_source_slices_with_complete_coverage(strategy):
    text = (
        "  财报\t摘要\r\n\r\n现金流 66,593,247,721.09 元；负增长 -12.34%。\n" * 8
        + "最后一句没有标点也必须保留"
    )
    chunker = TextChunker(chunk_size=85, overlap=17)
    rows = chunker.chunk_with_metadata(text, source="frozen", strategy=strategy)
    covered = set()
    for i, row in enumerate(rows):
        start, end = row["char_start"], row["char_end"]
        assert row["text"] == text[start:end]
        assert 0 < len(row["text"]) <= 85
        assert row["char_count"] == end - start
        assert row["chunk_index"] == i
        assert row["total_chunks"] == len(rows)
        assert row["chunker_version"] == "source-slices-v2"
        if i:
            assert rows[i - 1]["char_start"] < start <= rows[i - 1]["char_end"]
        covered.update(range(start, end))
    assert all(i in covered for i, c in enumerate(text) if not c.isspace())
    assert rows[-1]["text"].endswith("最后一句没有标点也必须保留")
    assert chunker.chunk(text, strategy) == [r["text"] for r in rows]


@pytest.mark.parametrize("strategy", ["simple", "paragraph", "smart"])
def test_numeric_tokens_are_not_cut_when_they_fit(strategy):
    token = "-66,593,247,721.09%"
    for prefix in range(1, 45):
        text = "甲" * prefix + token + "乙" * 120
        rows = TextChunker(45, 13).chunk_with_metadata(text, strategy=strategy)
        assert any(token in r["text"] for r in rows)
        for row in rows:
            for boundary in (row["char_start"], row["char_end"]):
                assert not prefix < boundary < prefix + len(token)


@pytest.mark.parametrize("token", ["−12.34%", "－12.34％", "＋12.34%", "-.75%", "−.75%"])
@pytest.mark.parametrize("strategy", ["simple", "paragraph", "smart"])
def test_unicode_signs_and_fraction_only_decimals_stay_attached(token, strategy):
    for overlap in (0, 5):
        for prefix in range(1, 21):
            text = "A" * prefix + token + "B" * 60
            rows = TextChunker(20, overlap).chunk_with_metadata(text, strategy=strategy)
            assert any(token in row["text"] for row in rows)
            for row in rows:
                for boundary in (row["char_start"], row["char_end"]):
                    assert not prefix < boundary < prefix + len(token)


def test_unpunctuated_long_text_and_repeated_text_have_real_offsets():
    text = "重复无标点" * 90
    rows = TextChunker(37, 36).chunk_with_metadata(text)
    assert rows[-1]["char_end"] == len(text)
    assert all(row["text"] == text[row["char_start"] : row["char_end"]] for row in rows)
    assert len(rows) <= len(text)
    assert TextChunker().chunk(" \n\t") == []


@pytest.mark.parametrize("size,overlap", [(0, 0), (-1, 0), (10, -1), (10, 10), (10, 11)])
def test_invalid_chunk_parameters_fail_early(size, overlap):
    with pytest.raises(ValueError):
        TextChunker(size, overlap)


def test_cosine_uses_actual_vectors_and_rejects_unknown_scores():
    from app.rag.scoring import cosine_similarity, relevant_results

    assert cosine_similarity([2, 0], [10, 0]) == pytest.approx(1)
    assert cosine_similarity([2, 0], [3, 4]) == pytest.approx(0.6)
    assert cosine_similarity([2, 0], [-10, 0]) == pytest.approx(-1)
    for vector in (None, [], [0, 0], [1], [float("nan"), 0], [float("inf"), 0]):
        assert cosine_similarity([2, 0], vector) is None
    rows = [
        dict(similarity=s, text="evidence", distance=0)
        for s in (None, float("nan"), float("inf"), True, "0.9", 1.1, -0.1, 0.49, 0.5, 0.8)
    ]
    assert [r["similarity"] for r in relevant_results(rows)] == [0.5, 0.8]


def test_search_requests_vectors_and_returns_cosine_independent_of_l2():
    from app.rag.core import RAGSystem

    class Collection:
        def query(self, **kwargs):
            assert "embeddings" in kwargs["include"]
            assert kwargs["where"] == {"document_id": "allowed"}
            return dict(
                documents=[["a", "b"]],
                metadatas=[[{}, {}]],
                distances=[[64.0, 17.0]],
                embeddings=[np.array([[10.0, 0.0], [3.0, 4.0]])],
            )

    rag = RAGSystem.__new__(RAGSystem)
    rag.collection = Collection()
    rag.embedding_service = SimpleNamespace(embed_query=lambda _: [2.0, 0.0])
    result = rag.search("query", filter_metadata={"document_id": "allowed"})
    assert result["success"], result
    assert [r["similarity"] for r in result["results"]] == pytest.approx([1.0, 0.6])
    assert [r["distance"] for r in result["results"]] == [64.0, 17.0]


def test_both_context_consumers_use_provided_cosine(monkeypatch):
    from app.rag import api
    from app.rag.research_integration import RAGEnhancedResearch

    rows = [
        dict(text="correct", metadata={}, distance=20.0, similarity=0.8),
        dict(text="wrong", metadata={}, distance=0.0, similarity=0.2),
        dict(text="unknown", metadata={}, distance=0.0),
    ]
    fake = SimpleNamespace(search=lambda *args, **kwargs: dict(success=True, results=rows))
    wrapper = RAGEnhancedResearch.__new__(RAGEnhancedResearch)
    wrapper.rag, wrapper.enabled = fake, True
    assert [r["text"] for r in wrapper.search_knowledge("q")] == ["correct"]
    monkeypatch.setattr(api, "get_rag_system", lambda: fake)
    result = asyncio.run(api.enhance_query(api.QueryRequest(query="q")))
    assert [r["text"] for r in result["context"]] == ["correct"]


@pytest.mark.parametrize("method", ["add_text", "add_document"])
def test_import_records_non_overridable_source_offsets(method):
    from app.rag.core import RAGSystem

    text = "原文 1,234.56\n\n" * 12
    saved = {}
    rag = RAGSystem.__new__(RAGSystem)
    rag.chunker = TextChunker(65, 10)
    rag.parser = SimpleNamespace(
        parse=lambda _: text, get_file_info=lambda _: {"filename": "x.txt"}
    )
    rag.embedding_service = SimpleNamespace(
        embed_documents=lambda chunks: [[1.0, 0.0]] * len(chunks)
    )
    rag.collection = SimpleNamespace(add=lambda **kwargs: saved.update(kwargs))
    result = getattr(rag, method)(
        text if method == "add_text" else "x.txt",
        metadata={"char_start": -1, "chunker_version": "forged"},
    )
    assert result["success"], result
    for chunk, meta in zip(saved["documents"], saved["metadatas"], strict=True):
        assert meta["chunker_version"] == "source-slices-v2"
        assert chunk == text[meta["char_start"] : meta["char_end"]]


def test_repair_comparator_uses_scope_cosine_and_original_offsets():
    from app.openviking_benchmark import eligible, load_expanded, resources_for
    from scripts.run_rag_repair_eval import RepairedComparator

    corpus = load_expanded()
    resources = resources_for(corpus)
    case = corpus["cases"][0]
    source = eligible(resources, case)[0]
    row = dict(
        text=source["text"][:80],
        distance=999.0,
        similarity=0.8,
        metadata=dict(
            resource_id=source["id"], char_start=0, char_end=80, chunker_version="source-slices-v2"
        ),
    )
    calls = []

    def search(*args, **kwargs):
        calls.append(kwargs)
        return dict(success=True, results=[row])

    comparator = RepairedComparator(SimpleNamespace(search=search), resources)
    assert comparator.find(case)[0]["text"] == row["text"]
    assert set(calls[0]["filter_metadata"]["resource_id"]["$in"]) == {
        r["id"] for r in eligible(resources, case)
    }
    row["text"] += " forged"
    with pytest.raises(ValueError, match="source"):
        comparator.find(case)
    assert comparator.find(dict(case, owner="other-user")) == []
