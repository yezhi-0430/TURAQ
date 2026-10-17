"""Research tools use isolated synthetic market responses, never paid models."""

import json
from datetime import date, timedelta

import httpx
import pytest

from app.tools.executor import execute_tool
from tests.unit.test_agent_safety import safety  # noqa: F401


@pytest.fixture(autouse=True)
def clean_test_database():
    yield


NEW_TOOLS = {
    "analyze_market_context",
    "search_stocks",
    "get_stock_quotes",
    "get_kline_history",
    "calculate_technical_indicators",
    "analyze_price_volume",
    "get_market_overview",
    "get_intraday_prices",
    "compare_stocks",
    "calculate_price_statistics",
    "search_company_reports",
    "list_company_announcements",
    "read_disclosure_document",
    "search_disclosure_text",
    "extract_financial_sections",
    "compare_report_sections",
}


def prices(n=45, constant=False):
    return [
        [
            str(date(2024, 1, 1) + timedelta(days=i)),
            str(10 if constant else i + 1),
            str(10 if constant else i + 1),
            str(11 if constant else i + 2),
            str(9 if constant else i + 0.5),
            str(i + 1),
        ]
        for i in range(n)
    ]


def history_request(**extra):
    return dict(stock_code="600519.SH", start_date="2024-01-01", end_date="2024-05-31", **extra)


def test_tools_extend_read_only_registry(stock_session):
    from app.tools.registry import tool_definitions

    tools = tool_definitions()
    assert {t["function"]["name"] for t in tools} == NEW_TOOLS | {
        "get_stock_profile",
        "get_daily_prices",
        "calculate_change",
    }
    assert all(t["function"]["parameters"]["additionalProperties"] is False for t in tools)


@pytest.mark.parametrize(
    "name,args",
    [
        ("get_stock_quotes", {"stock_codes": ["600519.SH"]}),
        ("get_kline_history", {"stock_code": "600519.SH"}),
    ],
)
def test_offline_online_tools_report_disabled(stock_session, name, args):
    result = execute_tool(name, json.dumps(args), stock_session)
    assert result.status == "error"
    assert result.error.kind == "execution_error"
    assert "离线" in result.error.message


@pytest.mark.parametrize(
    "name,args",
    [
        ("get_stock_quotes", {"stock_codes": ["http://evil"]}),
        ("get_stock_quotes", {"stock_codes": ["600519.SH"] * 11}),
        ("get_kline_history", {"stock_code": "600519.SH", "limit": True}),
        ("get_kline_history", {"stock_code": "600519.SH", "adjustment": "fake"}),
        ("search_stocks", {"query": "   "}),
        ("calculate_technical_indicators", history_request(ma_periods=[True])),
        ("analyze_price_volume", history_request(volume_window=0)),
    ],
)
def test_bad_arguments_rejected_before_reader(stock_session, name, args):
    result = execute_tool(name, json.dumps(args), stock_session)
    assert result.error.kind == "invalid_arguments"


def test_name_search_reuses_catalog_and_preserves_snapshot_limit(stock_session, monkeypatch):
    from app.stock_list import stock_list_service

    monkeypatch.setattr(
        stock_list_service,
        "stocks",
        [
            {"symbol": "600519.SH", "code": "sh600519", "market": "sh", "name": "贵州茅台"},
            {"symbol": "600001.SH", "code": "sh600001", "market": "sh", "name": "测试茅台"},
        ],
    )
    result = execute_tool("search_stocks", '{"query":"茅台","limit":1}', stock_session)
    assert result.status == "success"
    assert result.result["results"][0]["symbol"] == "600519.SH"
    assert result.result["truncated"] is True
    assert result.source.kind == "cached_catalog"
    assert result.source.record_count == 1
    assert result.source.latest_trade_date is None


def wire(stock_session, response, calls=None):
    from app.agent_market import MarketHistoryReader
    from app.agent_research import ResearchMarketReader

    def handle(req):
        if calls is not None:
            calls.append(req)
        return response(req) if callable(response) else httpx.Response(200, json=response)

    history = MarketHistoryReader(lambda: 30, transport=httpx.MockTransport(handle))
    stock_session.info["daily_price_reader"] = history
    stock_session.info["research_reader"] = ResearchMarketReader(history)


def test_technical_ma_rsi_and_cached_price_volume(stock_session):
    calls = []
    wire(stock_session, {"code": 0, "data": {"sh600519": {"day": prices()}}}, calls)
    result = execute_tool(
        "calculate_technical_indicators", json.dumps(history_request()), stock_session
    )
    assert result.status == "success"
    assert result.result["indicators"]["ma"]["5"] == "43.0000"
    assert result.result["indicators"]["ma"]["60"] is None
    assert result.result["indicators"]["rsi"] == "100.0000"
    assert result.source.kind == "python_calculation"
    assert result.source.inputs_origin == "market_data"
    assert result.source.record_count == 45
    assert result.source.latest_trade_date == date(2024, 2, 14)
    volume = execute_tool(
        "analyze_price_volume", json.dumps(history_request(volume_window=5)), stock_session
    )
    assert volume.result["metrics"]["change_percent"] == "4400.0000"
    assert volume.result["metrics"]["volume_ratio"] == "1.0714"
    assert volume.result["metrics"]["max_close_drawdown_percent"] == "0.0000"
    assert len(calls) == 1


def test_flat_prices_rsi_neutral_and_macd_zero(stock_session):
    wire(stock_session, {"code": 0, "data": {"sh600519": {"day": prices(constant=True)}}})
    result = execute_tool(
        "calculate_technical_indicators", json.dumps(history_request()), stock_session
    )
    assert result.result["indicators"]["rsi"] == "50.0000"
    assert result.result["indicators"]["macd"] == {
        "dif": "0.0000",
        "dea": "0.0000",
        "histogram": "0.0000",
    }


def test_short_or_unknown_basis_data_cannot_invent_indicators(stock_session):
    wire(stock_session, {"code": 0, "data": {"sh600519": {"day": prices(1)}}})
    result = execute_tool(
        "calculate_technical_indicators", json.dumps(history_request()), stock_session
    )
    assert result.result["data_status"] == "insufficient_data"
    assert result.result["indicators"]["rsi"] is None
    assert result.result["indicators"]["macd"] is None
    stock_session.info.clear()
    result = execute_tool(
        "calculate_technical_indicators",
        json.dumps({**history_request(), "stock_code": "000001.SZ"}),
        stock_session,
    )
    assert result.status == "success"
    assert result.result["data_status"] == "insufficient_data"
    assert result.source.kind == "python_calculation"


def test_quotes_partial_failure_and_observation_time(stock_session):
    from tests.unit.test_market_quotes import quote

    wire(stock_session, lambda req: httpx.Response(200, content=quote().encode("gb18030")))
    result = execute_tool(
        "get_stock_quotes", '{"stock_codes":["000001.SZ","600519.SH"]}', stock_session
    )
    assert result.status == "success"
    assert result.result["data_status"] == "partial"
    assert result.result["unavailable"] == ["sh600519"]
    assert result.source.kind == "online_market"
    assert result.source.quote_time
    assert result.source.latest_trade_date == date(2026, 10, 9)
    assert result.source.record_count == 1


def test_klines_preserve_basis_limit_and_actual_period(stock_session):
    wire(stock_session, {"code": 0, "data": {"sh600519": {"qfqweek": prices(4)}}})
    result = execute_tool(
        "get_kline_history",
        '{"stock_code":"600519.SH","period":"week","adjustment":"qfq","limit":2}',
        stock_session,
    )
    assert result.status == "success"
    assert len(result.result["bars"]) == 2
    assert result.source.price_adjustment == "qfq"
    assert result.result["period"] == "week"
    assert result.source.latest_trade_date == date(2024, 1, 4)


def test_positive_macd_matches_closed_form_reference(stock_session):
    wire(stock_session, {"code": 0, "data": {"sh600519": {"day": prices()}}})
    result = execute_tool(
        "calculate_technical_indicators", json.dumps(history_request()), stock_session
    )
    # Independent EMA closed forms for the series 1..45, not a production loop copy.
    assert result.result["indicators"]["macd"] == {
        "dif": "6.5806",
        "dea": "6.3905",
        "histogram": "0.3802",
    }


def test_drawdown_and_zero_reference_volume_are_distinct(stock_session):
    rows = prices(4)
    for row, value in zip(rows, [10, 12, 6, 9], strict=True):
        row[1:6] = [str(value), str(value), str(value + 1), str(value - 1), "0"]
    wire(stock_session, {"code": 0, "data": {"sh600519": {"day": rows}}})
    result = execute_tool(
        "analyze_price_volume", json.dumps(history_request(volume_window=2)), stock_session
    )
    assert result.result["metrics"]["max_close_drawdown_percent"] == "50.0000"
    assert result.result["metrics"]["change_percent"] == "-10.0000"
    assert result.result["metrics"]["volume_ratio"] is None
    assert result.result["data_status"] == "insufficient_data"
    assert any("零" in w for w in result.result["warnings"])


def test_all_market_tools_share_network_budget_and_quote_cache(stock_session):
    from tests.unit.test_market_quotes import quote

    calls = []

    def response(req):
        if req.url.host == "qt.gtimg.cn":
            return httpx.Response(200, content=quote(symbol="sh600519").encode("gb18030"))
        return httpx.Response(200, json={"code": 0, "data": {"sh600519": {"day": []}}})

    wire(stock_session, response, calls)
    for i in range(1, 8):
        arguments = json.dumps({"stock_codes": ["600519.SH", f"00000{i}.SZ"]})
        assert execute_tool("get_stock_quotes", arguments, stock_session).status == "success"
        assert execute_tool("get_stock_quotes", arguments, stock_session).status == "success"
    assert (
        execute_tool("get_daily_prices", json.dumps(history_request()), stock_session).status
        == "success"
    )
    exceeded = execute_tool("get_stock_quotes", '{"stock_codes":["600519.SH"]}', stock_session)
    assert exceeded.error.kind == "invalid_arguments"
    assert len(calls) == 8


def test_month_adjustment_is_reconciled_against_matching_daily(stock_session):
    calls = []

    def response(req):
        param = req.url.params["param"]
        rows = prices(2) if ",day," in param else [["2024-01-02", "1", "1", "100", ".5", "3"]]
        key = "hfqday" if ",day," in param else "hfqmonth"
        return httpx.Response(200, json={"code": 0, "data": {"sh600519": {key: rows}}})

    wire(stock_session, response, calls)
    result = execute_tool(
        "get_kline_history",
        '{"stock_code":"600519.SH","period":"month","adjustment":"hfq"}',
        stock_session,
    )
    assert result.status == "success"
    assert result.result["bars"][-1]["high"] == "3"
    assert result.source.price_adjustment == "hfq"
    assert len(calls) == 2


def test_live_api_exposes_and_audits_new_tools(safety, monkeypatch):  # noqa: F811
    from app import agent_api
    from app.agent_market import MarketHistoryReader
    from app.model_limits import model_admission
    from tests.unit.admission import offline_admission
    from tests.unit.test_market_quotes import quote

    admission = offline_admission()
    admission.settings.model_provider = "qwen"
    safety.client.app.dependency_overrides[model_admission] = lambda: admission
    monkeypatch.setattr(
        agent_api,
        "MarketHistoryReader",
        lambda remaining: MarketHistoryReader(
            remaining,
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, content=quote().encode("gb18030"))
            ),
        ),
    )
    safety.model.replies = iter(
        [
            {
                "tool_calls": [
                    {
                        "id": "catalog",
                        "type": "function",
                        "function": {"name": "search_stocks", "arguments": '{"query":"茅台"}'},
                    },
                    {
                        "id": "quote",
                        "type": "function",
                        "function": {
                            "name": "get_stock_quotes",
                            "arguments": '{"stock_codes":["000001.SZ"]}',
                        },
                    },
                ]
            },
            {"content": "隔离模型：已读取目录和行情。"},
        ]
    )
    response = safety.client.post(
        "/api/v1/agent/chat", json={"messages": [{"role": "user", "content": "查询股票与报价"}]}
    )
    assert response.status_code == 200
    executions = response.json()["executions"]
    assert len(executions) == 2
    assert executions[0]["source"]["kind"] == "cached_catalog"
    assert executions[1]["source"]["kind"] == "online_market"
    assert executions[1]["source"]["quote_time"]
    assert len(safety.model.requests[0]["tools"]) == 19
