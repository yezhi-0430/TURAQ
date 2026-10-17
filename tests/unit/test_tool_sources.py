"""Use real local rows; a source tag must not invent market provenance."""

import json
from datetime import UTC, date, datetime

import pytest

from app.database import DailyPrice, Stock
from app.tools.executor import execute_tool


def source_of(record):
    source = record.model_dump(mode="json").get("source")
    assert source is not None, "成功工具必须提供后端生成的来源"
    assert source["upstream_source"] is None
    assert source["collected_at"] is None
    timestamp = datetime.fromisoformat(source["executed_at"])
    assert timestamp.utcoffset().total_seconds() == 0
    return source


def seed_prices(session):
    stock = session.query(Stock).filter_by(symbol="000001.SZ").one()
    for day, close in [(9, "9"), (7, "10"), (8, "9.5")]:
        session.add(
            DailyPrice(
                stock_id=stock.id,
                trade_date=date(2026, 10, day),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=100,
            )
        )
    session.commit()


def test_profile_source_does_not_invent_trade_date_or_provider(stock_session):
    before = datetime.now(UTC)
    record = execute_tool("get_stock_profile", '{"stock_code":"000001.SZ"}', session=stock_session)
    after = datetime.now(UTC)
    source = source_of(record)
    assert source["kind"] == "local_database"
    assert source["latest_trade_date"] is None
    assert source["record_count"] == 1
    assert source["inputs_origin"] is None
    assert before <= datetime.fromisoformat(source["executed_at"]) <= after
    assert record.result == {"stock_code": "000001.SZ", "name": "本地保存的名称甲"}


@pytest.mark.parametrize(
    ("start", "end", "count", "latest"),
    [
        ("2026-10-01", "2026-10-11", 3, "2026-10-09"),
        ("2026-10-07", "2026-10-08", 2, "2026-10-08"),
        ("2026-10-10", "2026-10-11", 0, None),
    ],
)
def test_daily_source_uses_only_returned_rows(stock_session, start, end, count, latest):
    seed_prices(stock_session)
    record = execute_tool(
        "get_daily_prices",
        json.dumps({"stock_code": "000001.SZ", "start_date": start, "end_date": end}),
        session=stock_session,
    )
    source = source_of(record)
    assert record.status == "success"
    assert isinstance(record.result, list)
    assert len(record.result) == count
    assert source["kind"] == "local_database"
    assert source["latest_trade_date"] == latest
    assert source["record_count"] == count
    assert source["inputs_origin"] is None
    if count:
        assert source["latest_trade_date"] == record.result[0]["trade_date"]
        assert all(isinstance(row["close"], str) for row in record.result)
    else:
        assert record.result == []


def test_calculation_marks_arguments_without_claiming_real_quotes(stock_session):
    record = execute_tool("calculate_change", '{"previous_close":10,"current_close":9}')
    source = source_of(record)
    assert source["kind"] == "python_calculation"
    assert source["inputs_origin"] == "tool_arguments"
    assert source["latest_trade_date"] is None
    assert source["record_count"] == 1
    assert record.result == {"change_percent": "-10.0000"}


@pytest.mark.parametrize(
    ("name", "raw", "kind"),
    [
        ("delete_watchlist", "{}", "unknown_tool"),
        ("get_stock_profile", "{broken", "invalid_arguments"),
        ("get_stock_profile", '{"stock_code":"999999.SH"}', "stock_not_found"),
        (
            "get_stock_profile",
            '{"stock_code":"000001.SZ","source":"腾讯实时"}',
            "invalid_arguments",
        ),
    ],
)
def test_rejected_queries_do_not_claim_source(stock_session, name, raw, kind):
    record = execute_tool(name, raw, session=stock_session)
    assert "source" in record.model_dump()
    assert record.status == "error"
    assert record.error.kind == kind
    assert record.source is None


def test_execution_failure_has_no_success_source(stock_session, monkeypatch):
    from app.tools import executor

    def fail(*args):
        raise RuntimeError("private database failure")

    monkeypatch.setattr(executor, "get_stock_profile", fail)
    record = execute_tool("get_stock_profile", '{"stock_code":"000001.SZ"}', session=stock_session)
    assert "source" in record.model_dump()
    assert record.error.kind == "execution_error"
    assert record.source is None


def test_server_policy_explains_source_dates_and_unverified_inputs(stock_session):
    from app.agent_policy import AGENT_SYSTEM_PROMPT

    for word in ("交易日期", "执行时间", "空列表", "计算输入"):
        assert word in AGENT_SYSTEM_PROMPT
