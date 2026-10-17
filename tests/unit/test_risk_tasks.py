from uuid import uuid4

import pytest

from tests.unit.test_risk_workbench import risk_env  # noqa: F401


@pytest.fixture(autouse=True)
def clean_test_database():
    yield


def task_payload(**kwargs):
    return dict(request_id=str(uuid4()), scope="group", group_id=1, days=90, mode="full", **kwargs)


def test_group_task_is_private_and_duplicate_scope_reuses_result(risk_env):  # noqa: F811
    c, actor, _, _ = risk_env
    payload = task_payload()
    response = c.post("/api/v1/risk/tasks", json=payload)
    assert response.status_code == 201
    task = response.json()
    assert task["total"] == 1 and task["items"][0]["symbol"] == "000001.SZ"
    duplicate = c.post("/api/v1/risk/tasks", json=task_payload()).json()
    assert duplicate["id"] == task["id"]
    actor[0] = 2
    assert c.get("/api/v1/risk/tasks/" + str(task["id"])).status_code == 404
    assert c.post("/api/v1/risk/tasks", json=task_payload()).status_code == 404
    assert c.post("/api/v1/risk/tasks/" + str(task["id"]) + "/cancel").status_code == 404


def test_full_reading_process_saves_each_phase_and_synthesizes_after_tail(risk_env, monkeypatch):  # noqa: F811
    import json

    from fastapi import Request

    from app.auth.dependencies import get_settings
    from app.risk_api import get_model_client
    from app.risk_tasks import collection_admission

    c, _, app, admission = risk_env
    app.dependency_overrides[get_settings] = lambda: admission.settings
    app.dependency_overrides[collection_admission] = lambda: admission
    from app.model_limits import model_admission

    def document_admission(request: Request):
        assert request.state.model_purpose == "risk_document"
        return admission

    app.dependency_overrides[model_admission] = document_admission
    monkeypatch.setattr(
        "app.risk_reading.collect_stock",
        lambda *a, **k: dict(
            facts=["真实形状行情夹具"],
            warnings=[],
            coverage={"market": "available"},
            trade_date="2026-10-13",
            input_text="行情夹具",
            evidence=[
                dict(
                    kind="market_observation",
                    title="隔离测试行情",
                    date="2026-10-13",
                    page=None,
                    url=None,
                    excerpt="夹具",
                    verification="observed",
                )
            ],
            context={
                "market_assessment": dict(
                    risk_level="medium", basis=["程序依据"], latest_trade_date="2026-10-13"
                )
            },
        ),
    )

    class Reader:
        def __init__(self, *a):
            pass

        def list(self, *a, **k):
            return dict(
                documents=[
                    dict(
                        document_id="a" * 24,
                        title="完整报告",
                        published_date="2026-10-01",
                        url="https://example.com/report",
                    )
                ],
                next_page=None,
            )

        def document(self, id):
            return dict(
                pages=[dict(page=1, text="首段"), dict(page=2, text="尾页诉讼风险")], warnings=[]
            )

    monkeypatch.setattr("app.risk_reading.DisclosureReader", Reader)
    tid = c.post("/api/v1/risk/tasks", json=task_payload()).json()["id"]
    while True:
        response = c.post(f"/api/v1/risk/tasks/{tid}/collect")
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        if item["progress"]["phase"] == "review":
            break

    class Model:
        calls = []

        def chat(self, messages):
            self.calls.append(messages[-1]["content"])
            assert "尾页诉讼风险" in self.calls[-1]
            return json.dumps(
                dict(
                    facts=[],
                    inferences=["尾页诉讼风险"],
                    unknowns=[],
                    risk_level="medium",
                    sources=[],
                )
            )

    model = Model()
    app.dependency_overrides[get_model_client] = lambda: model
    reviewed = c.post(f"/api/v1/risk/tasks/{tid}/process").json()["items"][0]
    assert reviewed["status"] == "pending" and reviewed["progress"]["phase"] == "ready"
    assert reviewed["event_id"] is None and reviewed["progress"]["batches"] == 1
    assert c.get(f"/api/v1/risk/tasks/{tid}").json()["items"][0]["progress"][
        "read_characters"
    ] == len("首段尾页诉讼风险")
    finished = c.post(f"/api/v1/risk/tasks/{tid}/process").json()["items"][0]
    assert finished["status"] == "completed" and finished["progress"]["phase"] == "done"
    detail = c.get(f"/api/v1/risk/events/{finished['event_id']}").json()
    assert any("尾页诉讼风险" in t for t in detail["result"]["inferences"])
    assert len(model.calls) == 2


def test_external_stock_task_does_not_add_watchlist_and_can_cancel(risk_env):  # noqa: F811
    c, _, _, _ = risk_env
    p = dict(request_id=str(uuid4()), scope="stock", symbol="600519.SH", days=90)
    response = c.post("/api/v1/risk/tasks", json=p)
    assert response.status_code == 201
    task = response.json()
    assert task["items"][0]["name"] == "贵州茅台"
    assert (
        c.post("/api/v1/risk/tasks/" + str(task["id"]) + "/cancel").json()["status"] == "cancelled"
    )
    from sqlalchemy import func, select

    from app.auth.dependencies import get_session_factory
    from app.database import WatchlistItem

    with c.app.dependency_overrides[get_session_factory]()() as db:
        assert db.scalar(select(func.count()).select_from(WatchlistItem)) == 2


@pytest.mark.parametrize("failure", ["deadline", "format"])
def test_document_failure_explains_reason_and_preserves_resume_position(
    risk_env, monkeypatch, failure  # noqa: F811
):
    from sqlalchemy import select

    from app.auth.dependencies import get_session_factory, get_settings
    from app.model_limits import ModelDeadlineExceeded
    from app.risk_reading import new_reading
    from app.risk_summary import RiskSummaryParseError
    from app.risk_task_records import RiskTaskItem

    c, _, app, admission = risk_env
    app.dependency_overrides[get_settings] = lambda: admission.settings
    task = c.post("/api/v1/risk/tasks", json=task_payload()).json()
    reading = new_reading()
    reading.update(stage="review", cursor=dict(document=0, page=1, offset=37), batches=1)
    with app.dependency_overrides[get_session_factory]()() as db:
        item = db.scalar(select(RiskTaskItem).where(RiskTaskItem.task_id == task["id"]))
        item.snapshot = dict(reading=reading, evidence=[], facts=[], coverage={})
        db.commit()

    def fail(*a, **k):
        if failure == "deadline":
            raise ModelDeadlineExceeded("模型请求超时")
        raise RiskSummaryParseError("模型输出格式无效")

    monkeypatch.setattr("app.risk_tasks.review_step", fail)
    result = c.post(f"/api/v1/risk/tasks/{task['id']}/process").json()["items"][0]
    assert result["status"] == "failed"
    assert ("超时" if failure == "deadline" else "格式无效") in result["error"]
    assert result["progress"]["batches"] == 1 and result["event_id"] is None
    resumed = c.post(f"/api/v1/risk/tasks/{task['id']}/resume").json()["items"][0]
    assert resumed["status"] == "pending" and resumed["progress"]["phase"] == "review"
    with app.dependency_overrides[get_session_factory]()() as db:
        item = db.scalar(select(RiskTaskItem).where(RiskTaskItem.task_id == task["id"]))
        assert item.snapshot["reading"]["cursor"] == dict(document=0, page=1, offset=37)


@pytest.mark.parametrize("market_level", ["unknown", "low", "medium", "high"])
def test_processing_saves_structured_result_and_real_coverage(risk_env, market_level):  # noqa: F811
    from app.risk_tasks import get_stock_analyzer

    c, _, _, _ = risk_env
    c.app.dependency_overrides[get_stock_analyzer] = lambda: (
        lambda symbol, days, admission, **kwargs: dict(
            evidence=[
                dict(
                    kind="market_observation",
                    verification="observed",
                    title="测试真实形状",
                    date="2026-10-09",
                    url=None,
                    page=None,
                    excerpt="观察事实",
                )
            ],
            coverage={"market": "available", "reports": "failed", "announcements": "no_data"},
            facts=["已观察价格"],
            warnings=["财报获取失败"],
            trade_date="2026-10-09",
            input_text="事实材料",
            context={
                "observations": [],
                "market_assessment": {
                    "risk_level": market_level,
                    "basis": ["程序依据"],
                    "rule_version": "market_attention_v1",
                },
            },
        )
    )
    task = c.post("/api/v1/risk/tasks", json=task_payload()).json()
    result = c.post("/api/v1/risk/tasks/" + str(task["id"]) + "/process").json()
    assert result["status"] == "completed"
    item = result["items"][0]
    assert item["event_id"] and item["coverage"]["reports"] == "failed"
    detail = c.get("/api/v1/risk/events/" + str(item["event_id"])).json()
    assert detail["symbol"] == "000001.SZ" and detail["trade_date"] == "2026-10-09"
    assert detail["risk_level"] == market_level
    assert detail["result"]["market_assessment"]["basis"] == ["程序依据"]
    assert c.get("/api/v1/risk/events").json()["overview"]["high"] == (
        1 if market_level == "high" else 0
    )
    assert "已观察价格" in detail["result"]["facts"]
    assert detail["evidence"][0]["verification"] == "observed"
    assert c.post("/api/v1/risk/tasks/" + str(task["id"]) + "/process").status_code == 409
    again = c.get("/api/v1/risk/tasks/" + str(task["id"])).json()
    assert again["items"][0]["event_id"] == item["event_id"]


def test_item_lease_follows_configured_deadline(risk_env):  # noqa: F811
    import time
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.auth.dependencies import get_session_factory
    from app.auth.service import aware
    from app.risk_task_records import RiskTaskItem
    from app.risk_tasks import get_stock_analyzer

    c, _, application, admission = risk_env
    admission.deadline = time.monotonic() + 120
    remaining = []

    def collect(symbol, days, admitted, **kwargs):
        with application.dependency_overrides[get_session_factory]()() as db:
            item = db.scalar(select(RiskTaskItem).where(RiskTaskItem.status == "running"))
            remaining.append((aware(item.lease_expires_at) - datetime.now(UTC)).total_seconds())
        return dict(
            evidence=[],
            coverage={"market": "failed", "reports": "failed", "announcements": "failed"},
            facts=[],
            warnings=[],
            trade_date=None,
            input_text="没有资料",
            context={},
        )

    application.dependency_overrides[get_stock_analyzer] = lambda: collect
    task = c.post("/api/v1/risk/tasks", json=task_payload()).json()
    result = c.post("/api/v1/risk/tasks/" + str(task["id"]) + "/process").json()
    assert remaining and remaining[0] > 115
    assert result["items"][0]["status"] == "failed" and result["items"][0]["event_id"] is None


def test_market_partial_failure_cannot_be_overwritten_by_later_success(monkeypatch):
    from datetime import date
    from types import SimpleNamespace

    from app.disclosures import DisclosureUnavailable
    from app.risk_task_analysis import collect_stock
    from tests.unit.admission import offline_admission

    admission = offline_admission()
    admission.settings.model_provider = "qwen"

    def execute(name, args, session):
        if name == "calculate_technical_indicators":
            return SimpleNamespace(status="error", error=SimpleNamespace(message="指标失败"))
        source = SimpleNamespace(
            latest_trade_date=date(2026, 10, 9), record_count=30, model_dump=lambda **k: {}
        )
        data = (
            {
                "data_status": "available",
                "quotes": [{"price": "10", "quote_time": "2026-10-09T15:00:00+08:00"}],
            }
            if name == "get_stock_quotes"
            else {"data_status": "available", "metrics": {}}
        )
        if name == "analyze_market_context":
            data.update(
                assessment=dict(risk_level="unknown", basis=[]),
                sector_coverage="partial",
                warnings=[],
            )
        return SimpleNamespace(status="success", result=data, source=source)

    def unavailable(*args, **kwargs):
        raise DisclosureUnavailable("来源失败")

    monkeypatch.setattr("app.risk_task_analysis.execute_tool", execute)
    monkeypatch.setattr("app.risk_task_analysis.DisclosureReader.list", unavailable)
    result = collect_stock("600519.SH", 90, admission, end_date=date(2026, 10, 9))
    assert result["coverage"]["market"] == "partial"


def test_reanalysis_versions_do_not_duplicate_events_or_reset_review(risk_env):  # noqa: F811
    from app.risk_tasks import get_stock_analyzer

    c, actor, application, admission = risk_env
    application.dependency_overrides[get_stock_analyzer] = lambda: (
        lambda *a, **k: dict(
            evidence=[
                dict(
                    kind="market_observation",
                    verification="observed",
                    title="观察",
                    date="2026-10-09",
                    url=None,
                    page=None,
                    excerpt="观察",
                )
            ],
            coverage={"market": "available", "reports": "partial", "announcements": "no_data"},
            facts=["已观察事实"],
            warnings=["覆盖不足"],
            trade_date="2026-10-09",
            input_text="实际材料",
            context={},
        )
    )
    first = c.post("/api/v1/risk/tasks", json=task_payload()).json()
    eid = c.post(f"/api/v1/risk/tasks/{first['id']}/process").json()["items"][0]["event_id"]
    original = c.get(f"/api/v1/risk/events/{eid}").json()
    old_aid = original["analysis_id"]
    c.patch(f"/api/v1/risk/events/{eid}", json={"status": "following"})
    second = c.post("/api/v1/risk/tasks", json=task_payload(force=True)).json()
    next_eid = c.post(f"/api/v1/risk/tasks/{second['id']}/process").json()["items"][0]["event_id"]
    assert next_eid == eid
    current = c.get(f"/api/v1/risk/events/{eid}").json()
    assert current["status"] == "following" and current["version"] == 2
    assert c.get("/api/v1/risk/events").json()["total"] == 1
    previous = c.get(f"/api/v1/risk/analyses/{old_aid}")
    assert previous.status_code == 200 and previous.json()["version"] == 1
    assert previous.json()["analysis_id"] == old_aid
    assert c.get(f"/api/v1/risk/tasks/{first['id']}").json()["items"][0]["analysis_id"] == old_aid
    admission.settings.model_provider = "fake"
    third = c.post("/api/v1/risk/tasks", json=task_payload(force=True)).json()
    fake_eid = c.post(f"/api/v1/risk/tasks/{third['id']}/process").json()["items"][0]["event_id"]
    assert fake_eid != eid
    assert c.get(f"/api/v1/risk/events/{eid}").json()["model_mode"] == "qwen"
    actor[0] = 2
    assert c.get(f"/api/v1/risk/analyses/{old_aid}").status_code == 404
