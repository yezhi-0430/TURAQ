"""Isolated data for conversational research extensions; no paid model calls."""

import json
from datetime import date

import httpx
import pytest

from app.tools.executor import execute_tool
from tests.unit.test_research_tools import history_request, prices, wire


@pytest.fixture(autouse=True)
def clean_test_database():
    yield


@pytest.mark.parametrize(
    "name,args", [("get_market_overview", {}), ("get_intraday_prices", {"stock_code": "600519.SH"})]
)
def test_offline_new_online_capabilities_do_not_query_network(stock_session, name, args):
    record = execute_tool(name, json.dumps(args), stock_session)
    assert record.error.kind == "execution_error"
    assert "离线" in record.error.message


@pytest.mark.parametrize(
    "name,args",
    [
        ("get_market_overview", {"url": "https://evil"}),
        ("get_intraday_prices", {"stock_code": "600519.SH", "limit": 241}),
        (
            "compare_stocks",
            {
                "stock_codes": ["600519.SH", "600519"],
                "start_date": "2024-01-01",
                "end_date": "2024-05-31",
            },
        ),
        (
            "compare_stocks",
            {"stock_codes": ["600519.SH"], "start_date": "2024-01-01", "end_date": "2024-05-31"},
        ),
        ("calculate_price_statistics", history_request(atr_period=True)),
    ],
)
def test_new_arguments_are_strict(stock_session, name, args):
    record = execute_tool(name, json.dumps(args), stock_session)
    assert record.error.kind == "invalid_arguments"


def test_flat_bollinger_atr_and_return_variability(stock_session):
    wire(stock_session, {"code": 0, "data": {"sh600519": {"day": prices(35, constant=True)}}})
    record = execute_tool(
        "calculate_price_statistics", json.dumps(history_request()), stock_session
    )
    assert record.status == "success"
    assert record.result["statistics"]["bollinger"] == {
        "middle": "10.0000",
        "upper": "10.0000",
        "lower": "10.0000",
    }
    assert record.result["statistics"]["atr"] == "2.0000"
    assert record.result["statistics"]["return_std_percent"] == "0.0000"
    assert record.source.inputs_origin == "market_data"
    assert record.source.record_count == 35


def test_statistics_insufficient_is_not_zero(stock_session):
    wire(stock_session, {"code": 0, "data": {"sh600519": {"day": prices(1)}}})
    record = execute_tool(
        "calculate_price_statistics", json.dumps(history_request()), stock_session
    )
    assert record.result["data_status"] == "insufficient_data"
    assert all(v is None for v in record.result["statistics"].values())


def test_comparison_uses_common_observations_and_benchmark(stock_session):
    def response(req):
        code = req.url.params["param"].split(",")[0]
        rows = (
            prices(4)
            if code == "sh600519"
            else [
                ["2024-01-02", "10", "10", "11", "9", "1"],
                ["2024-01-04", "12", "12", "13", "11", "2"],
            ]
        )
        return httpx.Response(200, json={"code": 0, "data": {code: {"day": rows}}})

    calls = []
    wire(stock_session, response, calls)
    record = execute_tool(
        "compare_stocks",
        json.dumps(
            {
                "stock_codes": ["600519.SH", "000001.SZ"],
                "start_date": "2024-01-01",
                "end_date": "2024-05-31",
            }
        ),
        stock_session,
    )
    assert record.status == "success"
    assert record.result["common_dates"] == ["2024-01-02", "2024-01-04"]
    first, second = record.result["stocks"]
    assert first["change_percent"] == "100.0000"
    assert second["change_percent"] == "20.0000"
    assert second["relative_change_points"] == "-80.0000"
    assert record.source.record_count == 4
    assert record.source.latest_trade_date == date(2024, 1, 4)
    assert len(calls) == 2


def test_single_success_does_not_claim_cross_stock_comparison(stock_session):
    def response(req):
        code = req.url.params["param"].split(",")[0]
        return (
            httpx.Response(503)
            if code == "sz000001"
            else httpx.Response(200, json={"code": 0, "data": {code: {"day": prices(5)}}})
        )

    wire(stock_session, response)
    record = execute_tool(
        "compare_stocks",
        json.dumps(
            {
                "stock_codes": ["600519.SH", "000001.SZ"],
                "start_date": "2024-01-01",
                "end_date": "2024-05-31",
            }
        ),
        stock_session,
    )
    assert record.result["data_status"] == "insufficient_data"
    assert record.result["common_dates"] == []
    assert all(row["change_percent"] is None for row in record.result["stocks"])


def test_intraday_has_actual_observation_time_and_limit(stock_session):
    wire(
        stock_session,
        {
            "code": 0,
            "data": {
                "sh600519": {
                    "data": {
                        "date": "20240104",
                        "data": ["0930 10 1 1000", "0931 11 2 2100", "0932 12 3 3300"],
                    }
                }
            },
        },
    )
    record = execute_tool(
        "get_intraday_prices", '{"stock_code":"600519.SH","limit":2}', stock_session
    )
    assert record.status == "success"
    assert [p["time"] for p in record.result["points"]] == ["09:31", "09:32"]
    assert record.source.latest_trade_date == date(2024, 1, 4)
    assert record.source.quote_time.isoformat() == "2024-01-04T09:32:00+08:00"
    assert record.source.record_count == 2


def test_overview_covers_only_requested_indices(stock_session):
    from tests.unit.test_market_quotes import quote

    wire(
        stock_session,
        lambda req: httpx.Response(
            200, content=(quote("sh000001") + quote("sz399001")).encode("gb18030")
        ),
    )
    record = execute_tool("get_market_overview", "{}", stock_session)
    assert record.status == "success"
    assert record.result["data_status"] == "partial"
    assert record.result["coverage"]["requested_indices"] == 4
    assert record.result["coverage"]["available_indices"] == 2
    assert record.source.record_count == 2


def test_overview_missing_price_changes_are_unknown_not_zero_statistics(stock_session):
    from tests.unit.test_market_quotes import quote

    content = "".join(
        quote(code, price="0") for code in ["sh000001", "sz399001", "sz399006", "sh000300"]
    )
    wire(stock_session, lambda req: httpx.Response(200, content=content.encode("gb18030")))
    record = execute_tool("get_market_overview", "{}", stock_session)
    assert record.result["data_status"] == "insufficient_data"
    assert record.result["summary"]["rising_indices"] is None
    assert record.result["summary"]["falling_indices"] is None


def test_price_statistics_match_independent_variance_reference(stock_session):
    wire(stock_session, {"code": 0, "data": {"sh600519": {"day": prices(35)}}})
    record = execute_tool(
        "calculate_price_statistics", json.dumps(history_request()), stock_session
    )
    assert record.result["statistics"]["bollinger"] == {
        "middle": "25.5000",
        "upper": "37.0326",
        "lower": "13.9674",
    }
    assert record.result["statistics"]["atr"] == "2.0000"
    # Closed-form sample variance for returns 100/k, k=1..34.
    assert record.result["statistics"]["return_std_percent"] == "18.3991"


def test_comparison_missing_benchmark_does_not_choose_another(stock_session):
    def response(req):
        code = req.url.params["param"].split(",")[0]
        return (
            httpx.Response(503)
            if code == "sh600519"
            else httpx.Response(200, json={"code": 0, "data": {code: {"day": prices(4)}}})
        )

    wire(stock_session, response)
    record = execute_tool(
        "compare_stocks",
        json.dumps(
            {
                "stock_codes": ["600519.SH", "000001.SZ", "600000.SH"],
                "start_date": "2024-01-01",
                "end_date": "2024-05-31",
            }
        ),
        stock_session,
    )
    assert record.result["data_status"] == "partial"
    assert record.result["benchmark_code"] == "600519.SH"
    assert all(row["relative_change_points"] is None for row in record.result["stocks"])
    assert any("基准" in warning for warning in record.result["warnings"])


@pytest.mark.parametrize(
    "bad",
    [[], None, {"code": 0, "data": {"sh600519": {"data": {"date": "20240104", "data": [1]}}}}],
)
def test_malformed_intraday_is_request_failure(stock_session, bad):
    wire(stock_session, bad)
    record = execute_tool("get_intraday_prices", '{"stock_code":"600519.SH"}', stock_session)
    assert record.status == "error"
    assert record.error.kind == "execution_error"
    assert record.source is None
