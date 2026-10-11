import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Literal, cast

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.tools.calculations import CalculateChangeArguments, calculate_change
from app.tools.market_data import (
    DailyPricesArguments,
    StockNotFoundError,
    StockProfileArguments,
    get_daily_prices,
    get_stock_profile,
)
from app.tools.provenance import ToolSource, build_tool_source
from app.tools.registry import TOOL_ARGUMENT_MODELS

logger = logging.getLogger(__name__)

ToolResult = dict[str, object] | list[dict[str, object]]


class ToolExecutionError(BaseModel):
    kind: Literal["unknown_tool", "invalid_arguments", "stock_not_found", "execution_error"]
    message: str
    details: str | None = None


class ToolExecutionRecord(BaseModel):
    tool_call_id: str | None = None
    tool_name: str
    arguments: str
    status: Literal["success", "error"]
    result: ToolResult | None
    error: ToolExecutionError | None
    duration_ms: float = Field(ge=0)
    source: ToolSource | None = None


def _run_query(tool_name: str, arguments: BaseModel, session: Session) -> ToolResult:
    if tool_name == "get_stock_profile":
        return get_stock_profile(cast(StockProfileArguments, arguments), session)
    return get_daily_prices(cast(DailyPricesArguments, arguments), session)


def execute_tool(
    tool_name: str,
    arguments: str,
    session: Session | None = None,
    *,
    tool_call_id: str | None = None,
) -> ToolExecutionRecord:
    started = perf_counter()
    result = None
    error = None
    model = TOOL_ARGUMENT_MODELS.get(tool_name)

    if model is None:
        error = ToolExecutionError(kind="unknown_tool", message="工具未注册")
    else:
        try:
            decoded = json.loads(arguments, parse_float=Decimal)
            validated = model.model_validate(decoded)
            if tool_name == "calculate_change":
                result = calculate_change(cast(CalculateChangeArguments, validated))
            elif session is not None:
                result = _run_query(tool_name, validated, session)
            else:
                with SessionLocal() as owned_session:
                    result = _run_query(tool_name, validated, owned_session)
        except json.JSONDecodeError as exc:
            error = ToolExecutionError(
                kind="invalid_arguments", message=f"工具参数无效：arguments: {exc.msg}"
            )
        except ValidationError as exc:
            messages = [
                f"{'.'.join(str(part) for part in item['loc']) or 'arguments'}: {item['msg']}"
                for item in exc.errors(
                    include_input=False, include_context=False, include_url=False
                )
            ]
            error = ToolExecutionError(
                kind="invalid_arguments", message="工具参数无效：" + "; ".join(messages)
            )
        except StockNotFoundError as exc:
            error = ToolExecutionError(kind="stock_not_found", message=str(exc))
        except Exception as exc:
            error = ToolExecutionError(
                kind="execution_error",
                message="工具执行失败",
                details=f"{type(exc).__name__}: {exc}",
            )

    record = ToolExecutionRecord(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments=arguments,
        status="error" if error else "success",
        result=result,
        error=error,
        duration_ms=round((perf_counter() - started) * 1000, 3),
        source=build_tool_source(tool_name, result, datetime.now(UTC))
        if error is None and result is not None
        else None,
    )
    logger.info(record.model_dump_json())
    return record
