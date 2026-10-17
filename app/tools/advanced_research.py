"""Additional bounded read schemas and server-side comparative price statistics."""

from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.market import normalize_symbol
from app.tools.market_data import DailyPricesArguments, StockProfileArguments
from app.tools.research import ResearchRangeArguments, calculation_base, rounded, usable


class MarketOverviewArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntradayArguments(StockProfileArguments):
    limit: int = Field(default=120, strict=True, ge=1, le=240)


class CompareStocksArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stock_codes: list[str] = Field(min_length=2, max_length=4)
    start_date: date
    end_date: date

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def dates(cls, value):
        return DailyPricesArguments.parse_date(value)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        codes = []
        for value in self.stock_codes:
            code = normalize_symbol(StockProfileArguments(stock_code=value).stock_code)
            codes.append(code[2:] + "." + code[:2].upper())
        if len(set(codes)) != len(codes):
            raise ValueError("请提供2至4个不同的股票代码")
        ResearchRangeArguments(
            stock_code=codes[0], start_date=self.start_date, end_date=self.end_date
        )
        self.stock_codes = codes
        return self


class PriceStatisticsArguments(ResearchRangeArguments):
    bollinger_period: int = Field(default=20, strict=True, ge=2, le=120)
    atr_period: int = Field(default=14, strict=True, ge=2, le=60)


def calculate_price_statistics(history, arguments: PriceStatisticsArguments):
    rows, result = calculation_base(history)
    result["statistics"] = values = dict(bollinger=None, atr=None, return_std_percent=None)
    result["periods"] = dict(bollinger=arguments.bollinger_period, atr=arguments.atr_period)
    result["methods"] += (
        " 布林带为收盘均值±2倍总体标准差；ATR采用Wilder平滑真波幅，"
        "收益波动为相邻返回日收益百分比的样本标准差，不年化、不评级。"
    )
    if not usable(rows, result):
        return result
    closes = [Decimal(row["close"]) for row in rows]
    n = arguments.bollinger_period
    if len(rows) >= n:
        middle = sum(closes[-n:]) / n
        sigma = (sum((close - middle) ** 2 for close in closes[-n:]) / n).sqrt()
        values["bollinger"] = dict(
            middle=rounded(middle),
            upper=rounded(middle + 2 * sigma),
            lower=rounded(middle - 2 * sigma),
        )
    else:
        result["warnings"].append(f"布林带需要{n}条收盘记录。")
    n = arguments.atr_period
    if len(rows) >= n + 1:
        ranges = [
            max(
                Decimal(row["high"]) - Decimal(row["low"]),
                abs(Decimal(row["high"]) - previous),
                abs(Decimal(row["low"]) - previous),
            )
            for row, previous in zip(rows[1:], closes[:-1], strict=True)
        ]
        atr = sum(ranges[:n]) / n
        for item in ranges[n:]:
            atr = (atr * (n - 1) + item) / n
        values["atr"] = rounded(atr)
    else:
        result["warnings"].append(f"ATR{n}需要{n + 1}条记录。")
    if len(rows) >= 3:
        returns = [(b / a - 1) * 100 for a, b in zip(closes[:-1], closes[1:], strict=True)]
        mean = sum(returns) / len(returns)
        values["return_std_percent"] = rounded(
            (sum((v - mean) ** 2 for v in returns) / (len(returns) - 1)).sqrt()
        )
        result["warnings"].append(
            "交易日覆盖未核验，相邻返回日可能跨多个交易日；波动统计不是严格连续日或未来波动预测。"
        )
    else:
        result["warnings"].append("收益波动统计至少需要3条记录。")
    if any(v is None for v in values.values()):
        result["data_status"] = "insufficient_data"
    return result


def compare_histories(arguments: CompareStocksArguments, histories, errors):
    valid = {code: h for code, h in histories.items() if h["adjustment"] == "none" and h["rows"]}
    dates = (
        sorted(set.intersection(*[{r["trade_date"] for r in h["rows"]} for h in valid.values()]))
        if len(valid) >= 2
        else []
    )
    entries = []
    for code in arguments.stock_codes:
        history = histories.get(code)
        entries.append(
            dict(
                stock_code=code,
                change_percent=None,
                max_close_drawdown_percent=None,
                relative_change_points=None,
                input_data=calculation_base(history)[1]["input_data"] if history else None,
                error=errors.get(code),
                reason=(errors.get(code) or "")
                if history is None
                else "复权口径未知"
                if history["adjustment"] != "none"
                else "该区间未返回行情记录"
                if not history["rows"]
                else None,
                data_status="available" if code in valid else "insufficient_data",
            )
        )
    result = dict(
        benchmark_code=arguments.stock_codes[0],
        common_dates=dates,
        stocks=entries,
        data_status="partial" if len(valid) < len(arguments.stock_codes) else "available",
        warnings=["比较仅使用共同返回日期；交易日覆盖未核验，共同日收盘回撤不含盘中或未采样时段。"],
        input_data=dict(
            record_count=0,
            latest_trade_date=None,
            adjustment="none" if valid else None,
            source=next(iter(valid.values()))["source"] if valid else None,
            fetched_at=max(
                (h["fetched_at"] for h in valid.values() if h["fetched_at"]), default=None
            ),
        ),
    )
    if len(dates) < 2:
        result["data_status"] = "insufficient_data"
        result["warnings"].append("不足两只股票或不足两个共同观测日，不能形成同口径跨股票比较。")
        return result
    changes = {}
    for entry in entries:
        code = entry["stock_code"]
        if code not in valid:
            continue
        by_day = {row["trade_date"]: Decimal(row["close"]) for row in valid[code]["rows"]}
        closes = [by_day[day] for day in dates]
        changes[code] = (closes[-1] / closes[0] - 1) * 100
        entry["change_percent"] = rounded(changes[code])
        peak, drawdown = closes[0], Decimal(0)
        for close in closes:
            peak = max(peak, close)
            drawdown = max(drawdown, (1 - close / peak) * 100)
        entry["max_close_drawdown_percent"] = rounded(drawdown)
        result["warnings"].extend(valid[code]["warnings"])
    benchmark = changes.get(arguments.stock_codes[0])
    if benchmark is None:
        result["warnings"].append("首个指定股票的基准资料不足，相对基准变化未计算。")
    else:
        for entry in entries:
            if entry["stock_code"] in changes:
                entry["relative_change_points"] = rounded(changes[entry["stock_code"]] - benchmark)
    result["input_data"].update(record_count=len(dates) * len(valid), latest_trade_date=dates[-1])
    return result
