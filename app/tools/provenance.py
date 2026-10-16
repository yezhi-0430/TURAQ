"""Describe what a tool actually observed without inventing upstream facts."""

from datetime import date, datetime, time
from typing import Literal, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ToolSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "local_database", "python_calculation", "online_market", "cached_catalog", "public_document"
    ]
    executed_at: AwareDatetime
    latest_trade_date: date | None = None
    record_count: int = Field(ge=0)
    # These facts are not captured by the current stock/daily-price tables.
    upstream_source: str | None = None
    collected_at: AwareDatetime | None = None
    inputs_origin: Literal["tool_arguments", "market_data"] | None = None
    data_status: (
        Literal["available", "no_data", "local_fallback", "partial", "insufficient_data"] | None
    ) = None
    price_adjustment: Literal["none", "qfq", "hfq"] | None = None
    quote_time: AwareDatetime | None = None
    warnings: list[str] = Field(default_factory=list)
    document_titles: list[str] = Field(default_factory=list)
    published_dates: list[date] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list)


def build_tool_source(
    tool_name: str,
    result: dict[str, object] | list[dict[str, object]],
    executed_at: datetime,
) -> ToolSource:
    """Use returned rows, never the requested range or model-written source labels."""
    if tool_name in {
        "search_company_reports",
        "list_company_announcements",
        "read_disclosure_document",
        "search_disclosure_text",
        "extract_financial_sections",
        "compare_report_sections",
    }:
        reports = result.get("reports", [result])
        documents = result.get("documents", [r["document"] for r in reports if "document" in r])
        pages = [p["page"] for r in reports for p in r.get("excerpts", [])]
        return ToolSource(
            kind="public_document",
            executed_at=executed_at,
            record_count=len(pages) if pages else len(documents),
            upstream_source=result["source"],
            data_status=result["data_status"],
            warnings=result["warnings"],
            document_titles=[d["title"] for d in documents],
            published_dates=[d["published_date"] for d in documents],
            page_numbers=pages,
        )
    if tool_name == "search_stocks":
        return ToolSource(
            kind="cached_catalog",
            executed_at=executed_at,
            record_count=len(result["results"]),
            upstream_source="项目股票代码目录（缓存）",
            warnings=result["warnings"],
        )
    if tool_name in {"get_stock_quotes", "get_market_overview"}:
        rows = result["quotes"]
        timestamps = [datetime.fromisoformat(row["quote_time"]) for row in rows]
        return ToolSource(
            kind="online_market",
            executed_at=executed_at,
            record_count=len(rows),
            upstream_source=result["source"],
            collected_at=result["fetched_at"],
            latest_trade_date=max(t.date() for t in timestamps),
            quote_time=max(timestamps),
            data_status=result["data_status"],
            warnings=result["warnings"],
        )
    if tool_name == "get_kline_history":
        return ToolSource(
            kind="online_market",
            executed_at=executed_at,
            record_count=len(result["bars"]),
            latest_trade_date=max(
                (date.fromisoformat(r["date"]) for r in result["bars"]), default=None
            ),
            upstream_source=result["source"],
            collected_at=result["fetched_at"],
            price_adjustment=result["adjustment"],
            data_status=result["data_status"],
            warnings=result["warnings"],
        )
    if tool_name == "get_intraday_prices":
        from app.market import SHANGHAI

        day = date.fromisoformat(result["trade_date"])
        stamp = datetime.combine(day, time.fromisoformat(result["points"][-1]["time"]), SHANGHAI)
        return ToolSource(
            kind="online_market",
            executed_at=executed_at,
            latest_trade_date=day,
            record_count=len(result["points"]),
            upstream_source=result["source"],
            collected_at=result["fetched_at"],
            quote_time=stamp,
            data_status=result["data_status"],
            warnings=result["warnings"],
        )
    if tool_name in {
        "calculate_technical_indicators",
        "analyze_price_volume",
        "compare_stocks",
        "calculate_price_statistics",
        "analyze_market_context",
    }:
        data = result["input_data"]
        return ToolSource(
            kind="python_calculation",
            executed_at=executed_at,
            record_count=data["record_count"],
            latest_trade_date=data["latest_trade_date"],
            upstream_source=data["source"],
            collected_at=data["fetched_at"],
            inputs_origin="market_data",
            price_adjustment=data["adjustment"],
            data_status=result["data_status"],
            warnings=result["warnings"],
        )
    if tool_name == "get_daily_prices":
        if isinstance(result, dict):
            rows = cast(list[dict[str, object]], result["rows"])
            dates = [date.fromisoformat(cast(str, row["trade_date"])) for row in rows]
            return ToolSource(
                kind=result["source_kind"],
                executed_at=executed_at,
                latest_trade_date=max(dates, default=None),
                record_count=len(rows),
                upstream_source=result["source"],
                collected_at=result["fetched_at"],
                data_status=result["data_status"],
                price_adjustment=result["adjustment"],
                warnings=result["warnings"],
            )
        rows = cast(list[dict[str, object]], result)
        dates = [date.fromisoformat(cast(str, row["trade_date"])) for row in rows]
        return ToolSource(
            kind="local_database",
            executed_at=executed_at,
            latest_trade_date=max(dates, default=None),
            record_count=len(rows),
        )
    if tool_name == "get_stock_profile":
        return ToolSource(kind="local_database", executed_at=executed_at, record_count=1)
    if tool_name == "calculate_change":
        return ToolSource(
            kind="python_calculation",
            executed_at=executed_at,
            record_count=1,
            inputs_origin="tool_arguments",
        )
    raise ValueError("未注册工具没有可信来源")
