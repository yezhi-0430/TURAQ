import json
import logging
from contextlib import contextmanager

import pytest


def test_tool_definitions_describe_only_nineteen_read_tools(stock_session) -> None:
    from app.tools import registry

    definitions = registry.tool_definitions()

    assert {item["function"]["name"] for item in definitions} == {
        "analyze_market_context",
        "get_stock_profile",
        "get_daily_prices",
        "calculate_change",
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
    assert len(definitions) == 19
    for item in definitions:
        assert item["type"] == "function"
        assert item["function"]["description"]
        assert item["function"]["parameters"]["additionalProperties"] is False
    json.dumps(definitions)


def test_records_calculation_result_and_elapsed_time(stock_session, monkeypatch) -> None:
    from app.tools import executor

    ticks = iter([100.0, 100.125])
    monkeypatch.setattr(executor, "perf_counter", lambda: next(ticks))
    raw = '{"previous_close": 10, "current_close": 9}'

    record = executor.execute_tool("calculate_change", raw)

    assert record.tool_name == "calculate_change"
    assert record.arguments == raw
    assert record.status == "success"
    assert record.result == {"change_percent": "-10.0000"}
    assert record.error is None
    assert record.duration_ms == 125.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            '{"previous_close": 0.0001, "current_close": 12345678901234.5678}',
            "12345678901234567700.0000",
        ),
        (
            '{"previous_close": 0.0001, "current_close": 99999999999999.9999}',
            "99999999999999999800.0000",
        ),
    ],
)
def test_json_numeric_prices_keep_decimal_precision(stock_session, raw: str, expected: str) -> None:
    from app.tools import executor

    record = executor.execute_tool("calculate_change", raw)

    assert record.status == "success"
    assert record.result == {"change_percent": expected}
    assert record.arguments == raw


@pytest.mark.parametrize(
    "raw",
    [
        '{"previous_close": 10, "current_close": 9.0000000000000001}',
        '{"previous_close": 10.0000000000000001, "current_close": 9}',
        '{"previous_close": 10, "current_close": 9.0000000000000001e0}',
    ],
)
def test_overprecise_json_numbers_never_enter_calculation(stock_session, monkeypatch, raw: str):
    from app.tools import executor

    calls = []
    monkeypatch.setattr(executor, "calculate_change", lambda value: calls.append(value))

    record = executor.execute_tool("calculate_change", raw)

    assert calls == []
    assert record.status == "error"
    assert record.result is None
    assert record.error.kind == "invalid_arguments"
    assert record.arguments == raw


@pytest.mark.parametrize(
    "raw",
    [
        '{"previous_close": 0, "current_close": 9}',
        '{"previous_close": 10}',
        '{"previous_close": 10, "current_close": 9, "risk_level": "low"}',
        '{"previous_close":',
        "[]",
    ],
)
def test_bad_arguments_never_enter_calculation(stock_session, monkeypatch, raw: str) -> None:
    from app.tools import executor

    calls = []
    monkeypatch.setattr(executor, "calculate_change", lambda arguments: calls.append(arguments))

    record = executor.execute_tool("calculate_change", raw)

    assert calls == []
    assert record.status == "error"
    assert record.result is None
    assert record.error.kind == "invalid_arguments"
    assert "工具参数无效" in record.error.message
    assert record.arguments == raw
    assert record.duration_ms >= 0


def test_unknown_tool_never_opens_database(stock_session, monkeypatch) -> None:
    from app.tools import executor

    opened = []
    monkeypatch.setattr(executor, "SessionLocal", lambda: opened.append(True))

    record = executor.execute_tool("delete_stock", '{"stock_code": "000001.SZ"}')

    assert opened == []
    assert record.status == "error"
    assert record.error.kind == "unknown_tool"
    assert record.result is None


def test_reversed_dates_never_enter_query_or_open_session(stock_session, monkeypatch) -> None:
    from app.tools import executor

    calls = []
    monkeypatch.setattr(executor, "get_daily_prices", lambda *args: calls.append("query"))
    monkeypatch.setattr(executor, "SessionLocal", lambda: calls.append("session"))

    record = executor.execute_tool(
        "get_daily_prices",
        '{"stock_code": "000001.SZ", "start_date": "2026-09-26", "end_date": "2026-09-24"}',
    )

    assert calls == []
    assert record.error.kind == "invalid_arguments"
    assert "开始日期不能晚于结束日期" in record.error.message


def test_executes_profile_with_supplied_session(stock_session) -> None:
    from app.tools import executor

    record = executor.execute_tool(
        "get_stock_profile", '{"stock_code": "000001.SZ"}', session=stock_session
    )

    assert record.status == "success"
    assert record.result == {"stock_code": "000001.SZ", "name": "本地保存的名称甲"}


def test_opens_owned_session_only_for_valid_query(stock_session, monkeypatch) -> None:
    from app.tools import executor

    opened = []

    @contextmanager
    def open_session():
        opened.append(True)
        yield stock_session

    monkeypatch.setattr(executor, "SessionLocal", open_session)

    record = executor.execute_tool("get_stock_profile", '{"stock_code": "000001.SZ"}')

    assert opened == [True]
    assert record.status == "success"
    assert record.result["stock_code"] == "000001.SZ"


def test_empty_prices_are_successful_result(stock_session) -> None:
    from app.tools import executor

    record = executor.execute_tool(
        "get_daily_prices",
        '{"stock_code": "000001.SZ", "start_date": "2026-09-24", "end_date": "2026-09-25"}',
        session=stock_session,
    )

    assert record.status == "success"
    assert record.result == []
    assert record.error is None


def test_missing_stock_becomes_recorded_error(stock_session) -> None:
    from app.tools import executor

    record = executor.execute_tool(
        "get_stock_profile", '{"stock_code": "999999.SH"}', session=stock_session
    )

    assert record.status == "error"
    assert record.error.kind == "stock_not_found"
    assert record.error.message == "股票不存在"
    assert record.result is None


def test_unexpected_tool_failure_becomes_error_record(stock_session, monkeypatch) -> None:
    from app.tools import executor

    def fail(arguments):
        raise RuntimeError("模拟的工具内部失败")

    monkeypatch.setattr(executor, "calculate_change", fail)

    record = executor.execute_tool("calculate_change", '{"previous_close": 10, "current_close": 9}')

    assert record.status == "error"
    assert record.error.kind == "execution_error"
    assert record.error.message == "工具执行失败"


def test_logs_success_and_rejected_attempt_as_json(stock_session, caplog) -> None:
    from app.tools import executor

    with caplog.at_level(logging.INFO, logger="app.tools.executor"):
        success = executor.execute_tool(
            "calculate_change", '{"previous_close": 10, "current_close": 9}'
        )
        rejected = executor.execute_tool(
            "calculate_change", '{"previous_close": 0, "current_close": 9}'
        )

    records = [json.loads(item.message) for item in caplog.records]
    assert records == [success.model_dump(mode="json"), rejected.model_dump(mode="json")]
    assert records[0]["result"] == {"change_percent": "-10.0000"}
    assert records[1]["error"]["kind"] == "invalid_arguments"
