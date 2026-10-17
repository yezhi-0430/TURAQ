"""Request-scoped bounded quote and K-line readers, sharing the daily reader's budget."""

import asyncio
from datetime import date, datetime, time, timedelta

import httpx

from app.agent_market import MarketDataUnavailable, MarketRangeError
from app.market import (
    INDICES,
    SHANGHAI,
    SOURCE,
    is_index,
    normalize_symbol,
    parse_minutes,
    parse_quotes,
)
from app.market_history import parse_klines, reconcile_latest_month
from app.tools.research import StockQuotesArguments


class ResearchMarketReader:
    def __init__(self, history_reader):
        self.history = history_reader
        self.cache = {}

    def quotes(self, arguments):
        codes = tuple(dict.fromkeys(normalize_symbol(c) for c in arguments.stock_codes))
        return self._read(("quotes", codes), lambda: self._quotes(codes))

    def overview(self):
        result = self.quotes(StockQuotesArguments(stock_codes=list(INDICES)))
        moves = [q["change_percent"] for q in result["quotes"] if q["change_percent"] is not None]
        from decimal import Decimal

        return {
            **result,
            "coverage": {
                "requested_indices": len(INDICES),
                "available_indices": len(result["quotes"]),
                "known_change_indices": len(moves),
            },
            "summary": {
                "rising_indices": sum(Decimal(v) > 0 for v in moves) if moves else None,
                "falling_indices": sum(Decimal(v) < 0 for v in moves) if moves else None,
                "flat_indices": sum(Decimal(v) == 0 for v in moves) if moves else None,
            },
            "data_status": "insufficient_data"
            if not moves
            else "partial"
            if len(moves) < len(INDICES)
            else "available",
            "warnings": result["warnings"]
            + ["只覆盖所列主要指数，不代表全市场涨跌家数、资金流向或情绪评分。"],
        }

    def intraday(self, arguments):
        code = normalize_symbol(arguments.stock_code)
        result = self._read(("intraday", code), lambda: self._intraday(code))
        return {**result, "points": result["points"][-arguments.limit :]}

    async def _intraday(self, code):
        raw = await self.history.fetch_bytes(
            "https://web.ifzq.gtimg.cn/appstock/app/minute/query", {"code": code}
        )
        payload = httpx.Response(200, content=raw).json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise ValueError("分时源响应无效")
        entry = payload["data"].get(code)
        data = entry.get("data") if isinstance(entry, dict) else None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("data"), list)
            or not all(isinstance(row, str) for row in data["data"])
        ):
            raise ValueError("分时资料缺失")
        if "qt" in entry and not isinstance(entry["qt"], dict):
            raise ValueError("分时关联报价格式无效")
        now = datetime.now(SHANGHAI)
        result = parse_minutes(payload, code, now)
        for point in result["points"]:
            stamp = datetime.combine(
                date.fromisoformat(result["trade_date"]),
                time.fromisoformat(point["time"]),
                SHANGHAI,
            )
            if stamp > now + timedelta(minutes=5):
                raise ValueError("分时观测时间无效")
        return {
            **result,
            "data_status": "available",
            "warnings": [
                "公开分时可能延迟，返回最近观测点；量为累计量差分，记录缺口与完整交易时段未核验。"
            ],
        }

    def klines(self, arguments):
        code = normalize_symbol(arguments.stock_code)
        if is_index(code) and arguments.adjustment != "none":
            raise MarketRangeError("指数无需复权，请使用none")
        key = ("klines", code, arguments.period, arguments.adjustment)
        data = self._read(key, lambda: self._klines(code, arguments))
        return {**data, "bars": data["bars"][-arguments.limit :]}

    def _read(self, key, coroutine):
        self.history.remaining()
        if key not in self.cache:
            try:
                self.cache[key] = asyncio.run(coroutine())
            except MarketRangeError:
                raise
            except (
                httpx.HTTPError,
                TimeoutError,
                ValueError,
                KeyError,
                TypeError,
                IndexError,
                UnicodeError,
            ) as exc:
                self.history.remaining()
                raise MarketDataUnavailable(
                    "在线行情获取失败，请稍后重试；失败不表示无交易或无风险。"
                ) from exc
        self.history.remaining()
        return self.cache[key]

    async def _quotes(self, codes):
        content = await self.history.fetch_bytes("https://qt.gtimg.cn/q=" + ",".join(codes))
        now = datetime.now(SHANGHAI)
        quotes = parse_quotes(content.decode("gb18030"), now)
        rows = [quotes[c] for c in codes if c in quotes]
        missing = [c for c in codes if c not in quotes]
        if not rows:
            raise MarketDataUnavailable("行情源未返回有效报价，不能视为零价格或无风险。")
        return dict(
            source=SOURCE,
            fetched_at=now.isoformat(),
            quotes=rows,
            unavailable=missing,
            data_status="partial" if missing else "available",
            warnings=["公开行情可能延迟；以quote_time为实际观测时间，不承诺实时。"]
            + (["部分证券未返回有效报价。"] if missing else []),
        )

    async def _history(self, code, period, adjustment):
        suffix = "" if adjustment == "none" else adjustment
        raw = await self.history.fetch_bytes(
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            {"param": f"{code},{period},,,320,{suffix}"},
        )
        payload = httpx.Response(200, content=raw).json()
        if (
            not isinstance(payload, dict)
            or payload.get("code") != 0
            or not isinstance(payload.get("data"), dict)
            or not isinstance(payload["data"].get(code), dict)
        ):
            raise ValueError("K线源响应格式无效")
        now = datetime.now(SHANGHAI)
        if payload["data"][code].get(suffix + period) == []:
            return dict(
                code=code,
                period=period,
                adjustment=adjustment,
                bars=[],
                source=SOURCE,
                fetched_at=now.isoformat(),
            )
        return parse_klines(payload, code, period, now, adjustment)

    async def _klines(self, code, arguments):
        data = await self._history(code, arguments.period, arguments.adjustment)
        if data["bars"] and arguments.period == "month" and arguments.adjustment != "none":
            daily = await self._history(code, "day", arguments.adjustment)
            data = reconcile_latest_month(data, daily)
        return {
            **data,
            "data_status": "available" if data["bars"] else "no_data",
            "warnings": ["仅返回源提供的最近记录，不证明交易日完整；最新K线可能尚未收盘。"],
        }
