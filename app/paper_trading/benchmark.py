"""Compare account equity with the real CSI 300 daily closes on the same dates."""

from bisect import bisect_right
from datetime import date
from decimal import Decimal

from app.market_api import service

BENCHMARK = ("sh000300", "沪深300")


def align(account_start: date, initial_capital: Decimal, points: list[tuple[date, Decimal]],
          bars: list[dict]) -> dict:
    """Base both series at the last index close on or before the account start date."""
    closes = sorted((date.fromisoformat(b["date"]), Decimal(b["close"])) for b in bars)
    days = [d for d, _ in closes]
    base_at = bisect_right(days, account_start) - 1
    if base_at < 0:
        return {"available": False, "reason": "沪深300 K线未覆盖账户创建日期", "series": []}
    base_day, base_close = closes[base_at]
    series = []
    for day, assets in points:
        at = bisect_right(days, day) - 1
        if at < base_at:
            continue
        index_day, close = closes[at]
        series.append({
            "date": day.isoformat(),
            "total_assets": assets,
            "account_return": (assets / initial_capital - 1).quantize(Decimal("0.000001")),
            "benchmark_close": close,
            "benchmark_date": index_day.isoformat(),
            "benchmark_return": (close / base_close - 1).quantize(Decimal("0.000001")),
        })
    last = series[-1] if series else None
    return {
        "available": bool(series),
        "reason": None if series else "暂无已记录的账户日终快照",
        "symbol": "000300.SH",
        "name": BENCHMARK[1],
        "base_date": base_day.isoformat(),
        "base_close": base_close,
        "series": series,
        "excess_return": last["account_return"] - last["benchmark_return"] if last else None,
    }


async def compare(account_start: date, initial_capital: Decimal,
                  points: list[tuple[date, Decimal]]) -> dict:
    data = await service.klines(BENCHMARK[0], "day", "none")
    if not data.get("bars"):
        return {"available": False, "reason": data.get("error") or "沪深300 K线暂不可用",
                "series": []}
    result = align(account_start, initial_capital, points, data["bars"])
    result["stale"] = bool(data.get("stale"))
    result["source"] = data.get("source", "腾讯财经公开行情")
    return result
