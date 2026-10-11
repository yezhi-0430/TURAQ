"""Describe what a tool actually observed without inventing upstream facts."""

from datetime import date, datetime
from typing import Literal, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ToolSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["local_database", "python_calculation"]
    executed_at: AwareDatetime
    latest_trade_date: date | None = None
    record_count: int = Field(ge=0)
    # These facts are not captured by the current stock/daily-price tables.
    upstream_source: None = None
    collected_at: None = None
    inputs_origin: Literal["tool_arguments"] | None = None


def build_tool_source(
    tool_name: str,
    result: dict[str, object] | list[dict[str, object]],
    executed_at: datetime,
) -> ToolSource:
    """Use returned rows, never the requested range or model-written source labels."""
    if tool_name == "get_daily_prices":
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
