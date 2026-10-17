"""First answers must not wait for whole-document review; deep reading is resumable."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.dependencies import get_session_factory, get_settings
from app.risk_reading import new_reading
from app.risk_task_records import RiskTaskItem
from app.risk_tasks import collection_admission
from tests.unit.test_risk_workbench import risk_env  # noqa: F401


@pytest.fixture(autouse=True)
def clean_test_database():
    yield


def market():
    return dict(
        facts=["价格低于MA20"],
        warnings=[],
        evidence=[
            dict(
                kind="market_observation",
                verification="observed",
                title="测试行情",
                date="2026-10-14",
                excerpt="真实形状夹具",
            )
        ],
        coverage=dict(market="available", reports="not_connected", announcements="not_connected"),
        context={"market_assessment": dict(risk_level="medium", basis=["趋势偏弱"])},
        trade_date="2026-10-14",
        input_text="行情",
    )


def setup(environment, monkeypatch):
    c, _, app, a = environment
    app.dependency_overrides[get_settings] = lambda: a.settings
    app.dependency_overrides[collection_admission] = lambda: a
    monkeypatch.setattr("app.risk_reading.collect_stock", lambda *a, **k: market())
    return c, app


def create(c):
    return c.post(
        "/api/v1/risk/tasks",
        json=dict(
            request_id=str(uuid4()),
            scope="group",
            group_id=1,
            days=90,
        ),
    ).json()


def test_default_first_answer_finishes_after_market_and_one_model_call(risk_env, monkeypatch):  # noqa: F811
    c, app = setup(risk_env, monkeypatch)
    task = create(c)
    root = f"/api/v1/risk/tasks/{task['id']}"
    prepared = c.post(root + "/collect").json()["items"][0]
    assert prepared["progress"]["phase"] == "overview"
    result = c.post(root + "/process")
    assert result.status_code == 200, result.text
    item = result.json()["items"][0]
    assert item["status"] == "completed" and item["event_id"]
    assert item["progress"]["phase"] == "paused"
    assert item["answer"]["inferences"]
    assert item["coverage"]["reports"] != "available"
    detail = c.get(f"/api/v1/risk/events/{item['event_id']}").json()
    assert detail["result"]["analysis_scope"] == "preliminary"
    deeper = c.post(root + f"/items/{item['id']}/deepen")
    assert deeper.status_code == 200
    assert deeper.json()["items"][0]["progress"]["phase"] == "listing"
    with app.dependency_overrides[get_session_factory]()() as db:
        saved = db.get(RiskTaskItem, item["id"])
        snapshot = deepcopy(saved.snapshot)
        snapshot["reading"]["stage"] = "ready"
        saved.snapshot = snapshot
        db.commit()
    full = c.post(root + "/process").json()["items"][0]
    assert full["event_id"] == item["event_id"]
    assert full["answer"]["analysis_scope"] == "full"
    old = c.get(f"/api/v1/risk/analyses/{item['analysis_id']}")
    assert old.status_code == 200
    assert old.json()["historical"] and old.json()["result"]["analysis_scope"] == "preliminary"
    old_history = next(
        h for h in c.get("/api/v1/risk/analyses").json()["items"] if h["id"] == item["analysis_id"]
    )
    assert old_history["event_id"] == item["event_id"]


def test_existing_batches_can_summarize_then_continue_without_losing_position(
    risk_env, monkeypatch  # noqa: F811
):  # noqa: F811
    c, app = setup(risk_env, monkeypatch)
    task = create(c)
    root = f"/api/v1/risk/tasks/{task['id']}"
    reading = new_reading()
    reading.update(
        stage="review",
        batches=8,
        read_characters=960000,
        cursor=dict(document=22, page=3, offset=100),
        findings=[dict(facts=["已读取的债务原文"], inferences=["经营现金流需关注"])],
    )
    with app.dependency_overrides[get_session_factory]()() as db:
        item = db.scalar(select(RiskTaskItem).where(RiskTaskItem.task_id == task["id"]))
        iid = item.id
        item.snapshot = market() | dict(reading=deepcopy(reading))
        item.status = "cancelled"
        db.commit()
    assert c.post(root + f"/items/{iid}/overview").status_code == 200
    result = c.post(root + "/process").json()["items"][0]
    assert result["progress"]["batches"] == 8 and result["progress"]["phase"] == "paused"
    assert c.post(root + f"/items/{iid}/deepen").status_code == 200
    with app.dependency_overrides[get_session_factory]()() as db:
        saved = db.get(RiskTaskItem, iid).snapshot["reading"]
        assert saved["stage"] == "review" and saved["cursor"] == reading["cursor"]
        assert saved["findings"] == reading["findings"]
    risk_env[1][0] = 2
    assert c.post(root + f"/items/{iid}/overview").status_code == 404


def test_new_first_answer_reuses_own_same_date_reading_only(risk_env, monkeypatch):  # noqa: F811
    c, app = setup(risk_env, monkeypatch)
    task = create(c)
    with app.dependency_overrides[get_session_factory]()() as db:
        item = db.scalar(select(RiskTaskItem).where(RiskTaskItem.task_id == task["id"]))
        work = new_reading()
        work.update(
            stage="review",
            batches=2,
            read_characters=240000,
            findings=[dict(facts=["已有原文发现"], inferences=[])],
        )
        item.snapshot = market() | dict(reading=work)
        item.status = "cancelled"
        db.commit()
    other = c.post(
        "/api/v1/risk/tasks",
        json=dict(
            request_id=str(uuid4()),
            scope="group",
            group_id=1,
            days=90,
            force=True,
        ),
    ).json()
    result = c.post(f"/api/v1/risk/tasks/{other['id']}/collect").json()["items"][0]
    assert result["progress"]["batches"] == 2
    assert result["recent_findings"]["facts"] == ["已有原文发现"]


def test_first_answer_uses_bounded_key_findings_without_deleting_full_reading():
    from app.risk_reading import final_material

    snapshot = market()
    work = new_reading()
    work.update(
        stage="overview",
        batches=100,
        findings=[
            dict(
                risk_level="high",
                facts=[f"{i}原文" + "事实" * 100] * 12,
                inferences=[f"{i}推断" + "压力" * 100] * 12,
            )
            for i in range(100)
        ],
    )
    snapshot["reading"] = work
    before = deepcopy(work["findings"])
    material = final_material(snapshot)
    assert len(material) < 24000
    selected = json.loads(material)["finding_selection"]
    assert selected["total_batches"] == 100 and selected["omitted_entries"] > 0
    assert work["findings"] == before
