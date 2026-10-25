import json
from copy import deepcopy

from app.risk_reading import new_reading, review_step
from tests.unit.admission import offline_admission


def test_reduce_preserves_original_findings_and_lineage():
    admission = offline_admission()
    admission.settings.model_provider = "qwen"
    original = [{"facts": ["甲" * 5000]}, {"facts": ["末页诉讼" * 1500]}]
    state = dict(reading=new_reading(), evidence=[dict(review_batch=1)], coverage={})
    state["reading"].update(stage="reduce", findings=deepcopy(original), batches=2)
    result = review_step(state, None, admission, summarizer=lambda *a: {"facts": ["合并"]})
    work = result["reading"]
    assert work["batch_findings"] == []  # legacy snapshots cannot invent lost batch mapping
    assert work["reduction_history"][0]["inputs"] == original
    assert work["reduction_history"][0]["output"] == {"facts": ["合并"]}
    assert work["legacy_findings_unavailable"] is True
    assert work["findings"] == [{"facts": ["合并"]}]


def test_each_batch_records_summary_with_exact_evidence_and_cursor():
    admission = offline_admission()
    admission.settings.model_provider = "qwen"
    state = dict(reading=new_reading(), evidence=[], coverage={})
    state["reading"].update(
        stage="review",
        documents=[
            dict(
                document_id="a" * 24,
                title="合成报告",
                published_date="2026-01-01",
                url="https://example.invalid/a",
                kinds=["reports"],
                status="extracted",
                content_hash="frozen",
            )
        ],
    )

    class Reader:
        def document(self, key):
            return dict(content_hash="frozen", pages=[dict(page=1, text="尾页风险")])

    summary = {"facts": ["尾页风险"], "sources": ["合成报告第1页"]}
    review_step(state, None, admission, reader=Reader(), summarizer=lambda *a: summary)
    record = state["reading"]["batch_findings"][0]
    assert record["summary"] == summary
    assert record["evidence_indices"] == [0]
    assert record["cursor_before"] == dict(document=0, page=0, offset=0)
    summary["facts"].clear()
    assert record["summary"]["facts"] == ["尾页风险"]
    assert json.loads(json.dumps(state))["reading"]["batch_findings"] == [record]


def test_production_report_period_survives_batch_evidence():
    from app.risk_reading import next_batch

    doc = dict(
        document_id="a" * 24,
        title="真实字段形状",
        published_date="2026-01-01",
        url="https://example.invalid/a",
        report_period="2025年度",
        symbol="000001.SZ",
    )

    class Reader:
        def document(self, key):
            return {"pages": [{"page": 1, "text": "原文"}]}

    slices, _ = next_batch(Reader(), [doc], dict(document=0, page=0, offset=0))
    assert slices[0]["report_period"] == "2025年度"
