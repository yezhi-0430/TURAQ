"""Twenty offline model-output cases exercised through the HTTP endpoint."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import Actor, require_actor
from app.llm_client import FakeModelClient
from app.risk_api import get_model_client, router

VALID_SUMMARY = {
    "facts": ["用户提供的今日收盘价为9元"],
    "inferences": [],
    "unknowns": ["缺少成交量和评级依据"],
    "risk_level": "unknown",
    "sources": ["用户提供的数据"],
}
VALID_REPLY = json.dumps(VALID_SUMMARY, ensure_ascii=False)

CASES = [
    pytest.param(VALID_REPLY, VALID_SUMMARY, id="valid-chinese"),
    pytest.param(json.dumps(VALID_SUMMARY), VALID_SUMMARY, id="valid-unicode-escapes"),
    pytest.param(
        "\n" + json.dumps(VALID_SUMMARY, indent=2, ensure_ascii=False) + "\n",
        VALID_SUMMARY,
        id="valid-multiline",
    ),
    pytest.param("", None, id="empty"),
    pytest.param(" \n\t", None, id="whitespace-only"),
    pytest.param("无法生成摘要", None, id="plain-text"),
    pytest.param('{"facts": [', None, id="truncated-json"),
    pytest.param("{'facts': []}", None, id="single-quotes"),
    pytest.param(VALID_REPLY[:-1] + ",}", None, id="trailing-comma"),
    pytest.param("```json\n" + VALID_REPLY + "\n```", None, id="markdown-fence"),
    pytest.param("以下是摘要：" + VALID_REPLY, None, id="explanation-prefix"),
    *[
        pytest.param(
            json.dumps({key: value for key, value in VALID_SUMMARY.items() if key != field}),
            None,
            id=f"missing-{field}",
        )
        for field in ("facts", "inferences", "unknowns", "risk_level", "sources")
    ],
    pytest.param(
        json.dumps({**VALID_SUMMARY, "facts": "今日收盘价9元"}),
        None,
        id="facts-string",
    ),
    pytest.param(
        json.dumps({**VALID_SUMMARY, "risk_level": "safe"}),
        None,
        id="invalid-risk-level",
    ),
    pytest.param(
        json.dumps({**VALID_SUMMARY, "sources": None}),
        None,
        id="null-sources",
    ),
    pytest.param(json.dumps([VALID_SUMMARY]), None, id="array-root"),
]


@pytest.mark.parametrize(("reply", "expected"), CASES)
def test_model_output_is_handled_and_next_request_succeeds(reply, expected) -> None:
    application = FastAPI()
    application.dependency_overrides[require_actor] = lambda: Actor(1, "unit@example.com", True)
    application.include_router(router)
    model = FakeModelClient(reply=reply)
    application.dependency_overrides[get_model_client] = lambda: model
    payload = {"input_text": "用户提供：今日收盘价9元，没有其他信息。"}

    # Default TestClient behavior raises unhandled server exceptions.
    with TestClient(application) as client:
        response = client.post("/api/v1/risk-summary", json=payload)

        if expected is None:
            assert response.status_code == 502
            assert response.json() == {"detail": "模型输出格式无效"}
        else:
            assert response.status_code == 200
            assert response.json() == expected

        # Reuse the same application after each sample, including all failures.
        model.reply = VALID_REPLY
        recovery = client.post("/api/v1/risk-summary", json=payload)
        assert recovery.status_code == 200
        assert recovery.json() == VALID_SUMMARY
