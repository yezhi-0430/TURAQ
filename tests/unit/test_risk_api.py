import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import Actor, require_actor
from app.llm_client import FakeModelClient
from app.model_limits import model_admission
from app.risk_api import get_model_client, router
from tests.unit.admission import offline_admission


def test_returns_502_for_invalid_model_reply() -> None:
    application = FastAPI()
    application.dependency_overrides[model_admission] = offline_admission
    application.dependency_overrides[require_actor] = lambda: Actor(1, "unit@example.com", True)
    application.include_router(router)
    application.dependency_overrides[get_model_client] = lambda: FakeModelClient(reply="不是JSON")

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/risk-summary",
            json={"input_text": "用户提供：今日收盘价9元"},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "模型输出格式无效"}


def test_returns_valid_risk_summary() -> None:
    expected = {
        "facts": ["今日收盘价9元"],
        "inferences": [],
        "unknowns": ["缺少成交量"],
        "risk_level": "unknown",
        "sources": ["用户提供的数据"],
    }

    application = FastAPI()
    application.dependency_overrides[model_admission] = offline_admission
    application.dependency_overrides[require_actor] = lambda: Actor(1, "unit@example.com", True)
    application.include_router(router)
    application.dependency_overrides[get_model_client] = lambda: FakeModelClient(
        reply=json.dumps(expected, ensure_ascii=False)
    )

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/risk-summary",
            json={"input_text": "用户提供：今日收盘价9元"},
        )

    assert response.status_code == 200
    assert response.json() == expected


def test_default_fake_provider_returns_valid_offline_summary(stock_session, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    application = FastAPI()
    application.dependency_overrides[model_admission] = offline_admission
    application.dependency_overrides[require_actor] = lambda: Actor(1, "unit@example.com", True)
    application.include_router(router)
    with TestClient(application) as client:
        response = client.post("/api/v1/risk-summary", json={"input_text": "昨日10元，今日9元"})
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] == "unknown"
    assert body["facts"] == []
    assert body["sources"] == []
    assert any("离线" in value for value in body["unknowns"])
