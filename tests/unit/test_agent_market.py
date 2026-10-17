import json
from datetime import UTC, date

import httpx
import pytest

from tests.unit.test_agent_safety import safety  # noqa: F401


@pytest.fixture(autouse=True)
def clean_test_database():
    yield


def args(**extra):
    from app.tools.market_data import DailyPricesArguments

    return DailyPricesArguments.model_validate(
        dict(stock_code="600519.SH", start_date="2024-01-01", end_date="2024-05-31", **extra)
    )


def payload(rows):
    return {"code": 0, "data": {"sh600519": {"day": rows}}}


def reader(response, requests=None):
    from app.agent_market import MarketHistoryReader

    def handle(request):
        if requests is not None:
            requests.append(request)
        return response(request) if callable(response) else httpx.Response(200, json=response)

    return MarketHistoryReader(lambda: 30, transport=httpx.MockTransport(handle))


def test_requested_history_prices_units_and_source():
    calls = []
    result = reader(
        payload(
            [
                ["2023-12-29", "10", "10", "11", "9", "1"],
                ["2024-01-02", "10", "10", "11", "9", "123.5"],
                ["2024-05-31", "9", "9", "10", "8", "2"],
                ["2024-06-03", "8", "8", "9", "7", "1"],
            ]
        ),
        calls,
    )(args(), None)
    assert len(calls) == 1
    assert calls[0].url.params["param"] == "sh600519,day,2024-01-01,2024-05-31,320,"
    assert result["data_status"] == "available"
    assert [row["trade_date"] for row in result["rows"]] == ["2024-05-31", "2024-01-02"]
    assert result["rows"][1]["volume_shares"] == "12350.0"
    assert result["summary"]["change_percent"] == "-10.0000"
    assert result["source_kind"] == "online_market"
    assert result["fetched_at"]


def test_empty_valid_response_is_not_network_failure():
    result = reader(payload([]))(args(), None)
    assert result["data_status"] == "no_data"
    assert result["rows"] == []
    assert result["latest_trade_date"] is None


def test_network_failure_uses_local_rows_and_marks_unverified_upstream(stock_session):
    from app.tools.market_data import DailyPricesArguments
    from tests.unit.test_daily_prices_tool import add_price

    add_price(stock_session, "000001.SZ", date(2026, 9, 10))
    add_price(stock_session, "000001.SZ", date(2026, 9, 11))
    request = DailyPricesArguments(
        stock_code="000001.SZ", start_date=date(2026, 9, 10), end_date=date(2026, 9, 20)
    )

    def fail(req):
        raise httpx.ConnectError("private upstream detail")

    result = reader(fail)(request, stock_session)
    assert result["data_status"] == "local_fallback"
    assert result["source_kind"] == "local_database"
    assert result["source"] is None
    assert result["fetched_at"] is None
    assert len(result["rows"]) == 2
    assert result["adjustment"] is None
    assert result["summary"]["change_percent"] is None
    assert "未知" in result["summary"]["change_basis"]
    assert "复权" in "".join(result["warnings"])
    from datetime import datetime

    from app.tools.provenance import build_tool_source

    source = build_tool_source("get_daily_prices", result, datetime.now(UTC))
    assert source.price_adjustment is None


def test_network_failure_without_local_rows_is_error():
    from app.agent_market import MarketDataUnavailable

    with pytest.raises(MarketDataUnavailable, match="本地"):
        reader(lambda req: httpx.Response(503))(args(), None)


def test_request_cache_and_range_bound():
    from app.agent_market import MarketHistoryReader
    from app.tools.market_data import DailyPricesArguments

    calls = []
    r = reader(payload([]), calls)
    r(args(), None)
    r(args(), None)
    assert len(calls) == 1
    with pytest.raises(ValueError, match="366"):
        r(
            DailyPricesArguments(
                stock_code="600519.SH", start_date=date(2022, 1, 1), end_date=date(2024, 5, 31)
            ),
            None,
        )
    deadline = MarketHistoryReader(lambda: (_ for _ in ()).throw(TimeoutError("deadline")))
    with pytest.raises(TimeoutError):
        deadline(args(), None)


def test_executor_uses_request_reader_and_generates_online_provenance(stock_session):
    from app.tools.executor import execute_tool

    stock_session.info["daily_price_reader"] = reader(
        payload([["2024-01-02", "10", "10", "11", "9", "100"]])
    )
    result = execute_tool("get_daily_prices", args().model_dump_json(), stock_session)
    assert result.status == "success"
    assert result.source.kind == "online_market"
    assert result.source.record_count == 1
    assert result.source.upstream_source == "腾讯财经公开行情"
    assert result.source.latest_trade_date == date(2024, 1, 2)
    assert result.source.collected_at is not None


def test_request_budget_is_bounded():
    from app.tools.market_data import DailyPricesArguments

    calls = []
    r = reader(payload([]), calls)
    for day in range(1, 5):
        r(
            DailyPricesArguments(
                stock_code="600519.SH", start_date=date(2024, 1, day), end_date=date(2024, 5, 31)
            ),
            None,
        )
    with pytest.raises(ValueError, match="4"):
        r(
            DailyPricesArguments(
                stock_code="600519.SH", start_date=date(2024, 1, 5), end_date=date(2024, 5, 31)
            ),
            None,
        )
    assert len(calls) == 4


def test_chat_live_mode_gets_online_history_through_existing_tool(safety, monkeypatch):  # noqa: F811
    from app import agent_api
    from app.model_limits import model_admission
    from tests.unit.admission import offline_admission

    admission = offline_admission()
    admission.settings.model_provider = "qwen"
    safety.client.app.dependency_overrides[model_admission] = lambda: admission
    monkeypatch.setattr(
        agent_api,
        "MarketHistoryReader",
        lambda remaining: reader(payload([["2024-01-02", "10", "10", "11", "9", "100"]])),
    )
    safety.model.replies = iter(
        [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "history",
                        "type": "function",
                        "function": {
                            "name": "get_daily_prices",
                            "arguments": args().model_dump_json(),
                        },
                    }
                ],
            },
            {"content": "**已查询在线日线**"},
        ]
    )
    response = safety.client.post(
        "/api/v1/agent/chat",
        json={"messages": [{"role": "user", "content": "查询贵州茅台2024年1月至5月日线"}]},
    )
    assert response.status_code == 200, response.text
    source = response.json()["executions"][0]["source"]
    assert source["kind"] == "online_market"
    assert source["record_count"] == 1
    assert source["collected_at"]
    tool = json.loads(safety.model.requests[-1]["messages"][-1]["content"])
    assert tool["result"]["rows"][0]["close"] == "10"
    assert tool["source"]["kind"] == "online_market"


@pytest.mark.parametrize(
    "bad", [None, [], {"code": 0, "data": None}, {"code": 0, "data": {"sh600519": None}}]
)
def test_malformed_provider_response_is_availability_error(bad):
    from app.agent_market import MarketDataUnavailable

    with pytest.raises(MarketDataUnavailable):
        reader(bad)(args(), None)


def test_slow_market_stream_is_cancelled_and_closed():
    import asyncio

    from app.agent_market import MarketDataUnavailable, MarketHistoryReader

    closed = []

    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"{"
            await asyncio.sleep(0.1)
            yield b"}"

        async def aclose(self):
            closed.append(True)

    async def handle(request):
        return httpx.Response(200, stream=Slow())

    r = MarketHistoryReader(lambda: 0.02, transport=httpx.MockTransport(handle))
    with pytest.raises(MarketDataUnavailable):
        r(args(), None)
    assert closed == [True]


@pytest.mark.parametrize("timeout_kind", ["deadline", "http"])
def test_model_timeout_preserves_audited_online_results(safety, monkeypatch, timeout_kind):  # noqa: F811
    from app import agent_api
    from app.llm_client import ModelTimeoutError
    from app.model_limits import ModelDeadlineExceeded, model_admission
    from tests.unit.admission import offline_admission

    admission = offline_admission()
    admission.settings.model_provider = "qwen"
    safety.client.app.dependency_overrides[model_admission] = lambda: admission
    monkeypatch.setattr(
        agent_api,
        "MarketHistoryReader",
        lambda remaining: reader(payload([["2024-01-02", "10", "10", "11", "9", "100"]])),
    )
    safety.model.replies = iter(
        [
            {
                "tool_calls": [
                    {
                        "id": "history",
                        "type": "function",
                        "function": {
                            "name": "get_daily_prices",
                            "arguments": args().model_dump_json(),
                        },
                    }
                ]
            }
        ]
    )
    original = safety.model.chat_with_tools

    def replies(messages, tools):
        if len(safety.model.requests):
            error = ModelDeadlineExceeded if timeout_kind == "deadline" else ModelTimeoutError
            raise error("模型请求超时")
        return original(messages, tools)

    monkeypatch.setattr(safety.model, "chat_with_tools", replies)
    response = safety.client.post(
        "/api/v1/agent/chat",
        json={"messages": [{"role": "user", "content": "查询600519.SH在2024年1月至5月日线"}]},
    )
    assert response.status_code == 504
    body = response.json()
    assert "模型" in body["detail"]
    partial = body["partial"]
    assert partial["status"] == "incomplete"
    assert partial["model_mode"] == "qwen"
    assert partial["run_id"]
    assert len(partial["executions"]) == 1
    execution = partial["executions"][0]
    assert execution["source"]["record_count"] == 1
    assert execution["source"]["kind"] == "online_market"
    assert json.loads(execution["result"])["rows"][0]["close"] == "10"
    assert not partial.get("answer")
