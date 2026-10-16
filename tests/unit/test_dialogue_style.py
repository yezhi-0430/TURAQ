"""The existing API keeps ordinary dialogue and follow-ups in the same model request."""

import pytest

from tests.unit.test_agent_safety import safety  # noqa: F401


@pytest.fixture(autouse=True)
def clean_test_database():
    yield


def test_ordinary_explanation_is_not_forced_into_market_queries(safety):  # noqa: F811
    answer = "RSI反映近期涨跌力量的相对变化，较高数值并不保证价格马上反转。"
    safety.model.replies = iter([{"content": answer}])
    response = safety.client.post(
        "/api/v1/agent/chat",
        json={
            "messages": [
                {"role": "user", "content": "RSI是怎么看的？"},
                {"role": "assistant", "content": "RSI用于观察近期涨跌力量。"},
                {"role": "user", "content": "所以它不能确定价格马上反转，对吗？"},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == answer and body["rounds"] == 1
    assert body["executions"] == []
    messages = safety.model.requests[0]["messages"]
    assert messages[-1]["content"].startswith("所以它")
    assert "不强制每次添加总结" in messages[0]["content"]
    assert "不机械套用固定报告模板" in messages[0]["content"]
    assert "1至3句" in messages[0]["content"]


def test_user_requested_brief_answer_and_summary_are_preserved(safety):  # noqa: F811
    answer = "已有资料支持进一步比较，完整财务与公告信息仍需补充。"
    safety.model.replies = iter([{"content": answer}])
    response = safety.client.post(
        "/api/v1/agent/chat",
        json={
            "messages": [{"role": "user", "content": "把刚才的要点用一句话总结，不要展开过程。"}]
        },
    )
    assert response.status_code == 200
    assert response.json()["answer"] == answer
    assert "用户指定格式或长度时优先遵循" in safety.model.requests[0]["messages"][0]["content"]
