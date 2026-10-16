import json

from app.risk_reading import final_material, next_batch


def test_malformed_document_reply_reports_format_error_without_exposing_model_text():
    import pytest

    from app.llm_client import FakeModelClient
    from app.risk_reading import document_summary
    from app.risk_summary import RiskSummaryParseError
    from tests.unit.admission import offline_admission

    with pytest.raises(RiskSummaryParseError, match="模型输出格式无效"):
        document_summary(FakeModelClient("invalid private output"), offline_admission(), "资料")


def test_batches_preserve_every_character_across_pages_and_documents():
    documents = [
        dict(
            document_id="a" * 24,
            title="A",
            published_date="2026-01-01",
            url="https://example.com/a",
            kinds=["reports"],
        ),
        dict(
            document_id="b" * 24,
            title="B",
            published_date="2026-01-02",
            url="https://example.com/b",
            kinds=["announcements"],
        ),
    ]
    pages = {
        "a" * 24: [dict(page=1, text="甲" * 123), dict(page=2, text="末页关键风险")],
        "b" * 24: [dict(page=1, text="乙" * 81)],
    }

    class Reader:
        def document(self, id):
            return dict(pages=pages[id])

    cursor = dict(document=0, page=0, offset=0)
    texts = []
    while cursor["document"] < len(documents):
        excerpts, cursor = next_batch(Reader(), documents, cursor, budget=50)
        texts.extend(e["excerpt"] for e in excerpts)
    assert "".join(texts) == "甲" * 123 + "末页关键风险" + "乙" * 81


def test_final_material_includes_reading_findings_not_only_market_indicators():
    snapshot = dict(
        facts=["报价事实"],
        warnings=[],
        coverage={},
        context={"market_assessment": {}},
        reading=dict(stage="ready", documents=[], findings=[dict(inferences=["尾页诉讼风险"])]),
    )
    text = final_material(snapshot)
    assert "尾页诉讼风险" in text and len(text) < 20000
    assert isinstance(json.loads(text), dict)


def test_collection_and_review_resume_all_pages_without_charging_collection_model(monkeypatch):
    from datetime import date

    from app.risk_reading import collect_step, review_step
    from tests.unit.admission import offline_admission

    admission = offline_admission()
    admission.settings.model_provider = "qwen"
    monkeypatch.setattr(
        "app.risk_reading.collect_stock",
        lambda *a, **k: dict(
            facts=["市场事实"],
            warnings=[],
            evidence=[],
            coverage={"market": "available"},
            context={"market_assessment": {}},
            trade_date="2026-10-13",
            input_text="市场材料",
        ),
    )

    class Reader:
        def list(self, *a, **k):
            page = k["page"]
            is_report = k["reports"]
            id = ("a" if is_report else "b") * 24
            if is_report and page == 2:
                id = "c" * 24
            return dict(
                documents=[
                    dict(
                        document_id=id,
                        title=id[0],
                        published_date="2026-10-01",
                        url="https://example.com/" + id,
                    )
                ],
                next_page=2 if is_report and page == 1 else None,
            )

        def document(self, id):
            return dict(
                pages=[dict(page=1, text=id[0] * 61000), dict(page=2, text="最后一页真实风险")],
                warnings=[],
            )

    reader = Reader()
    state = None
    for _ in range(10):
        state = collect_step(
            "600519.SH", 90, admission, end_date=date(2026, 10, 14), state=state, reader=reader
        )
        if state["reading"]["stage"] == "review":
            break
    assert len(state["reading"]["documents"]) == 3
    texts = []

    def summarize(model, admitted, material):
        values = json.loads(material)["excerpts"]
        texts.extend(v["excerpt"] for v in values)
        return dict(facts=[], inferences=["末页风险"], unknowns=[], risk_level="medium", sources=[])

    while state["reading"]["stage"] == "review":
        state = review_step(state, None, admission, reader=reader, summarizer=summarize)
    assert state["reading"]["stage"] == "ready"
    assert "".join(texts) == "".join(c * 61000 + "最后一页真实风险" for c in ["a", "c", "b"])
    assert (
        state["coverage"]["reports"] == "available"
        and state["coverage"]["announcements"] == "available"
    )
    assert state["reading"]["read_characters"] == sum(len(t) for t in texts)


def test_cross_model_mode_cannot_resume_real_reading_without_network():
    from datetime import date

    import pytest

    from app.disclosures import DisclosureUnavailable
    from app.risk_reading import collect_step, new_reading, review_step
    from tests.unit.admission import offline_admission

    a = offline_admission()

    class NoNetwork:
        def list(self, *a, **k):
            raise AssertionError("must reject mode before reader")

    state = dict(reading=new_reading(), coverage={})
    state["reading"]["model_mode"] = "qwen"
    with pytest.raises(DisclosureUnavailable, match="模型模式"):
        collect_step("600519.SH", 90, a, end_date=date.today(), state=state, reader=NoNetwork())
    state["reading"]["stage"] = "review"
    with pytest.raises(DisclosureUnavailable, match="模型模式"):
        review_step(state, None, a)


def test_final_synthesis_rechecks_market_age():
    from datetime import date, timedelta

    state = dict(
        facts=[],
        context={
            "market_assessment": dict(
                risk_level="low",
                basis=["历史趋势"],
                latest_trade_date=str(date.today() - timedelta(days=10)),
            )
        },
        coverage={},
        reading=dict(stage="ready", documents=[], findings=[]),
    )
    result = json.loads(final_material(state))["market_assessment"]
    assert result["risk_level"] == "unknown" and result["historical_risk_level"] == "low"


def test_lost_cache_returns_to_extraction_and_changed_hash_restarts_reading():
    from datetime import date

    from app.disclosures import DisclosureUnavailable
    from app.risk_reading import collect_step, new_reading, review_step
    from tests.unit.admission import offline_admission

    a = offline_admission()
    a.settings.model_provider = "qwen"
    doc = dict(
        document_id="a" * 24,
        title="报告",
        published_date="2026-10-01",
        url="https://example.com/a",
        kinds=["reports"],
        status="extracted",
        content_hash="old",
        characters=30,
        page_count=1,
    )
    state = dict(
        reading=new_reading(),
        coverage={},
        evidence=[dict(kind="public_document", excerpt="旧版本")],
    )
    work = state["reading"]
    work.update(
        stage="review",
        model_mode="qwen",
        documents=[doc],
        cursor=dict(document=0, page=0, offset=10),
        findings=[dict(inferences=["旧版本结论"])],
    )

    class Lost:
        def document(self, id):
            raise DisclosureUnavailable("cache missing")

    state = review_step(state, None, a, reader=Lost())
    assert state["reading"]["stage"] == "extract" and doc["status"] == "pending"

    class Recovered:
        def document(self, id):
            return dict(pages=[dict(page=1, text="新全文")], warnings=[], content_hash="new")

    state = collect_step("600519.SH", 90, a, end_date=date.today(), state=state, reader=Recovered())
    assert state["reading"]["cursor"] == dict(document=0, page=0, offset=0)
    assert state["reading"]["findings"] == [] and state["evidence"] == []


def test_errors_are_deduplicated_and_deepen_retries_failed_documents_and_listings():
    from app.risk_reading import add_error, new_reading, retry_failed

    work = new_reading()
    work["listing_done"] = ["reports"]
    work["documents"] = [
        dict(document_id="a" * 24, title="甲", kinds=["reports"], status="extracted"),
        dict(document_id="b" * 24, title="乙", kinds=["reports"], status="failed", error="超时"),
        dict(document_id="c" * 24, title="丙", kinds=["reports"], status="extracted"),
    ]
    work["cursor"] = dict(document=3, page=0, offset=0)
    work["listed_pages"]["announcements"] = 1
    for _ in range(3):
        add_error(work, kind="announcements", message="披露源重复返回同一页，后续清单未完成")
    add_error(work, kind="reports", document_id="b" * 24, message="超时")
    assert len(work["errors"]) == 2

    stage, cleared = retry_failed(work)
    assert stage == "listing" and work["kind"] == "announcements" and work["page"] == 2
    assert work["errors"] == [] and "超时" in cleared
    # Failed file is requeued after the already-read files, and the cursor still covers it.
    assert [d["title"] for d in work["documents"]] == ["甲", "丙", "乙"]
    assert work["documents"][2]["status"] == "pending" and "error" not in work["documents"][2]
    assert work["cursor"]["document"] == 2


def test_legacy_oversized_listing_restarts_from_first_page():
    from app.risk_reading import new_reading, retry_failed

    work = new_reading()
    work.pop("page_size")
    work["listing_done"] = ["reports"]
    work["listed_pages"]["announcements"] = 4
    work["page_signatures"] = {"announcements": "same"}
    work["errors"] = [dict(kind="announcements", message="披露源重复返回同一页，后续清单未完成")]
    stage, _ = retry_failed(work)
    assert stage == "listing" and work["page"] == 1
    assert "announcements" not in work["page_signatures"]


def test_listing_failure_moves_on_and_collection_uses_source_page_size(monkeypatch):
    from datetime import date

    from app.disclosures import SOURCE_PAGE_SIZE, DisclosureUnavailable
    from app.risk_reading import collect_step, new_reading
    from tests.unit.admission import offline_admission

    admission = offline_admission()
    admission.settings.model_provider = "qwen"
    limits = []

    class Reader:
        def list(self, *a, **k):
            limits.append(k["limit"])
            raise DisclosureUnavailable("公开披露源请求失败")

    state = dict(coverage={}, warnings=[], evidence=[], reading=new_reading())
    for _ in range(2):
        state = collect_step(
            "600519.SH", 90, admission, end_date=date(2026, 10, 14), state=state, reader=Reader()
        )
    assert limits == [SOURCE_PAGE_SIZE] * 2
    assert state["reading"]["stage"] == "extract"
    assert [e["kind"] for e in state["reading"]["errors"]] == ["reports", "announcements"]
