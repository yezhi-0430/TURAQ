import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from time import perf_counter
from typing import Literal, cast

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.agent_market import MarketDataUnavailable, MarketHistoryReader, MarketRangeError
from app.database import SessionLocal
from app.disclosures import DisclosureUnavailable
from app.tools.advanced_research import calculate_price_statistics, compare_histories
from app.tools.calculations import CalculateChangeArguments, calculate_change
from app.tools.documents import run_document_tool
from app.tools.market_data import (
    DailyPricesArguments,
    StockNotFoundError,
    StockProfileArguments,
    get_daily_prices,
    get_stock_profile,
)
from app.tools.provenance import ToolSource, build_tool_source
from app.tools.registry import TOOL_ARGUMENT_MODELS
from app.tools.research import analyze_price_volume, calculate_technical, search_stocks

logger = logging.getLogger(__name__)

ToolResult = dict[str, object] | list[dict[str, object]]


class ToolResultSerializer:
    """统一的工具结果序列化器，处理 datetime、Decimal 等特殊类型"""

    @staticmethod
    def serialize(obj: object) -> object:
        """将不可JSON序列化的对象转换为标准类型"""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, dict):
            return {k: ToolResultSerializer.serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ToolResultSerializer.serialize(item) for item in obj]
        if isinstance(obj, set):
            return [ToolResultSerializer.serialize(item) for item in obj]
        # 对于其他类型直接返回，Pydantic 会自动处理
        return obj


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

    @model_validator(mode="after")
    def serialize_result(self) -> "ToolExecutionRecord":
        """确保所有结果都能被 Pydantic 和 JSON 序列化"""
        if self.result is not None:
            self.result = ToolResultSerializer.serialize(self.result)
        return self


def _run_query(tool_name: str, arguments: BaseModel, session: Session) -> ToolResult:
    if tool_name == "analyze_market_context":
        history = session.info.get("daily_price_reader")
        if history is None:
            raise MarketDataUnavailable("综合市场分析在离线测试模式下未启用")
        from app.market_risk import MarketContextReader

        reader = session.info.setdefault("market_context_reader", MarketContextReader(history))
        return reader.analyze(arguments, session)
    if tool_name in {
        "search_company_reports",
        "list_company_announcements",
        "read_disclosure_document",
        "search_disclosure_text",
        "extract_financial_sections",
        "compare_report_sections",
    }:
        return run_document_tool(tool_name, arguments, session.info.get("disclosure_reader"))
    if tool_name == "get_stock_profile":
        return get_stock_profile(cast(StockProfileArguments, arguments), session)
    if tool_name == "search_stocks":
        return search_stocks(arguments)
    if tool_name in {
        "get_stock_quotes",
        "get_kline_history",
        "get_market_overview",
        "get_intraday_prices",
    }:
        reader = session.info.get("research_reader")
        if reader is None:
            raise MarketDataUnavailable("在线行情工具在离线测试模式下未启用")
        if tool_name == "get_market_overview":
            return reader.overview()
        if tool_name == "get_intraday_prices":
            return reader.intraday(arguments)
        return (
            reader.quotes(arguments)
            if tool_name == "get_stock_quotes"
            else reader.klines(arguments)
        )
    if tool_name == "compare_stocks":
        histories, errors = {}, {}
        for code in arguments.stock_codes:
            scope = DailyPricesArguments(
                stock_code=code, start_date=arguments.start_date, end_date=arguments.end_date
            )
            try:
                raw = _run_query("get_daily_prices", scope, session)
                histories[code] = (
                    raw
                    if isinstance(raw, dict)
                    else MarketHistoryReader.result(
                        scope,
                        raw,
                        "local_database",
                        None,
                        None,
                        "available" if raw else "no_data",
                        ["本地复权口径未知，不能比较价格变化。"],
                    )
                )
            except (MarketDataUnavailable, StockNotFoundError) as exc:
                errors[code] = str(exc)
        return compare_histories(arguments, histories, errors)
    if reader := session.info.get("daily_price_reader"):
        history = reader(cast(DailyPricesArguments, arguments), session)
    else:
        rows = get_daily_prices(cast(DailyPricesArguments, arguments), session)
        if tool_name == "get_daily_prices":
            return rows
        history = MarketHistoryReader.result(
            arguments,
            rows,
            "local_database",
            None,
            None,
            "available" if rows else "no_data",
            ["本地价格复权口径与成交量单位未知。"],
        )
    if tool_name == "get_daily_prices":
        return history
    if tool_name == "calculate_technical_indicators":
        return calculate_technical(history, arguments)
    if tool_name == "analyze_price_volume":
        return analyze_price_volume(history, arguments)
    if tool_name == "calculate_price_statistics":
        return calculate_price_statistics(history, arguments)
    raise ValueError("没有对应只读工具实现")


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
        except MarketRangeError as exc:
            error = ToolExecutionError(kind="invalid_arguments", message=str(exc))
        except (MarketDataUnavailable, DisclosureUnavailable) as exc:
            error = ToolExecutionError(kind="execution_error", message=str(exc))
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
