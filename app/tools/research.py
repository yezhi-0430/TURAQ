"""Read-only research schemas and calculations on server-observed price series."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.market import SHANGHAI
from app.stock_list import stock_list_service
from app.tools.market_data import DailyPricesArguments, StockProfileArguments


class SearchStocksArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=20)
    ]
    market: Literal["sh", "sz", "bj"] | None = None
    limit: int = Field(default=10, strict=True, ge=1, le=20)


class StockQuotesArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stock_codes: list[
        Annotated[
            str,
            StringConstraints(
                strict=True,
                strip_whitespace=True,
                pattern=r"^(?:[0-9]{6}(?:\.(?:SH|SZ|BJ))?|(?:sh|sz|bj)[0-9]{6})$",
            ),
        ]
    ] = Field(min_length=1, max_length=10)


class KlineHistoryArguments(StockProfileArguments):
    period: Literal["day", "week", "month"] = "day"
    adjustment: Literal["none", "qfq", "hfq"] = "none"
    limit: int = Field(default=60, strict=True, ge=1, le=120)


class ResearchRangeArguments(DailyPricesArguments):
    @model_validator(mode="after")
    def bounded_range(self) -> Self:
        if (self.end_date - self.start_date).days + 1 > 366:
            raise ValueError("计算范围最多366个自然日")
        return self


class TechnicalArguments(ResearchRangeArguments):
    ma_periods: list[Annotated[int, Field(strict=True, ge=2, le=250)]] = Field(
        default_factory=lambda: [5, 10, 20, 60], min_length=1, max_length=6
    )
    rsi_period: int = Field(default=14, strict=True, ge=2, le=50)


class PriceVolumeArguments(ResearchRangeArguments):
    volume_window: int = Field(default=20, strict=True, ge=2, le=60)


def search_stocks(arguments: SearchStocksArguments):
    if not stock_list_service.stocks:
        from app.agent_market import MarketDataUnavailable

        raise MarketDataUnavailable("股票代码目录暂不可用，不能将其视为无匹配股票")
    matches = stock_list_service.search(arguments.query, arguments.market, arguments.limit + 1)
    return dict(
        query=arguments.query,
        results=[
            {k: row.get(k) for k in ("symbol", "code", "name", "market")}
            for row in matches[: arguments.limit]
        ],
        truncated=len(matches) > arguments.limit,
        catalog_updated_at=stock_list_service.last_updated.isoformat()
        if stock_list_service.last_updated
        else None,
        warnings=["缓存股票代码目录只用于名称与代码匹配，不证明上市状态、行情或财报完整。"],
    )


def rounded(value):
    return (
        str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        if value is not None
        else None
    )


def calculation_base(history):
    rows = sorted(history["rows"], key=lambda row: row["trade_date"])
    return rows, dict(
        stock_code=history["stock_code"],
        data_status="available",
        warnings=list(history["warnings"]),
        input_data=dict(
            source_kind=history["source_kind"],
            source=history["source"],
            fetched_at=history["fetched_at"],
            adjustment=history["adjustment"],
            record_count=len(rows),
            first_trade_date=rows[0]["trade_date"] if rows else None,
            latest_trade_date=rows[-1]["trade_date"] if rows else None,
            coverage=history["coverage"],
        ),
        methods="基于实际返回的日线记录；缺失交易日未核验；价格统计使用同一不复权口径。",
    )


def usable(rows, result):
    if not rows or result["input_data"]["adjustment"] != "none":
        result["data_status"] = "insufficient_data"
        result["warnings"].append("缺少价格记录或复权口径未知，不能生成可核对的技术指标。")
        return False
    if rows[-1]["trade_date"] == datetime.now(SHANGHAI).date().isoformat():
        result["warnings"].append(
            "最新日线属于今天，可能尚未收盘；指标随盘中变化，累计量不能当作全天放量。"
        )
    return True


def calculate_technical(history, arguments: TechnicalArguments):
    rows, result = calculation_base(history)
    values = dict(ma={str(n): None for n in arguments.ma_periods}, rsi=None, macd=None)
    result["indicators"] = values
    result["methods"] += (
        " MA为收盘简单均值；RSI为Wilder平滑；MACD=EMA12-EMA26，DEA=EMA9，"
        "柱值=2*(DIF-DEA)，EMA从首日收盘初始化。"
    )
    if not usable(rows, result):
        return result
    closes = [Decimal(row["close"]) for row in rows]
    for period in arguments.ma_periods:
        if len(closes) >= period:
            values["ma"][str(period)] = rounded(sum(closes[-period:]) / period)
        else:
            result["warnings"].append(f"MA{period}需要{period}条收盘记录，当前仅{len(closes)}条。")
    n = arguments.rsi_period
    result["rsi_period"] = n
    if len(closes) >= n + 1:
        deltas = [b - a for a, b in zip(closes, closes[1:], strict=False)]
        gain = sum(max(d, Decimal(0)) for d in deltas[:n]) / n
        loss = sum(max(-d, Decimal(0)) for d in deltas[:n]) / n
        for delta in deltas[n:]:
            gain = (gain * (n - 1) + max(delta, Decimal(0))) / n
            loss = (loss * (n - 1) + max(-delta, Decimal(0))) / n
        values["rsi"] = rounded(Decimal(50) if gain + loss == 0 else gain / (gain + loss) * 100)
    else:
        result["warnings"].append(f"RSI{n}需要{n + 1}条记录。")
    if len(closes) >= 35:
        fast = slow = closes[0]
        dea = Decimal(0)
        for close in closes[1:]:
            fast += (close - fast) * Decimal(2) / 13
            slow += (close - slow) * Decimal(2) / 27
            dif = fast - slow
            dea += (dif - dea) * Decimal(2) / 10
        values["macd"] = dict(
            dif=rounded(dif), dea=rounded(dea), histogram=rounded(2 * (dif - dea))
        )
        result["warnings"].append(
            "MACD使用本次区间首日初始化，短区间存在热启动误差，不等同于更长历史的指标。"
        )
    else:
        result["warnings"].append("MACD至少需要35条记录。")
    if (
        any(v is None for v in values["ma"].values())
        or values["rsi"] is None
        or values["macd"] is None
    ):
        result["data_status"] = "insufficient_data"
    return result


def analyze_price_volume(history, arguments: PriceVolumeArguments):
    rows, result = calculation_base(history)
    metrics = dict(
        change_percent=None,
        high=None,
        low=None,
        max_close_drawdown_percent=None,
        latest_volume_lots=None,
        previous_average_volume_lots=None,
        volume_ratio=None,
    )
    result["metrics"] = metrics
    result["volume_window"] = arguments.volume_window
    result["methods"] += (
        " 回撤基于返回日收盘价；量比为最新累计成交量/此前N条日线均量，"
        "不是市场盘口量比，也不自动评级异常。"
    )
    if not usable(rows, result):
        return result
    closes = [Decimal(row["close"]) for row in rows]
    metrics.update(
        high=rounded(max(Decimal(r["high"]) for r in rows)),
        low=rounded(min(Decimal(r["low"]) for r in rows)),
        latest_volume_lots=rows[-1].get("volume_lots"),
    )
    if len(rows) >= 2:
        metrics["change_percent"] = rounded((closes[-1] / closes[0] - 1) * 100)
        peak = closes[0]
        drawdown = Decimal(0)
        for close in closes:
            peak = max(peak, close)
            drawdown = max(drawdown, (1 - close / peak) * 100)
        metrics["max_close_drawdown_percent"] = rounded(drawdown)
    else:
        result["warnings"].append("首末变化和收盘回撤至少需要2条记录。")
    n = arguments.volume_window
    if len(rows) >= n + 1 and all(r.get("volume_lots") is not None for r in rows[-n - 1 :]):
        average = sum(Decimal(r["volume_lots"]) for r in rows[-n - 1 : -1]) / n
        metrics["previous_average_volume_lots"] = rounded(average)
        if average > 0:
            metrics["volume_ratio"] = rounded(Decimal(rows[-1]["volume_lots"]) / average)
        else:
            result["warnings"].append("前期平均成交量为零，不能计算成交量比值。")
    else:
        result["warnings"].append(f"成交量比值需要{n + 1}条同单位记录。")
    if metrics["change_percent"] is None or metrics["volume_ratio"] is None:
        result["data_status"] = "insufficient_data"
    return result
