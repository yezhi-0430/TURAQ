"""Bounded read-only history for live research, using the dashboard's source and validator."""

import asyncio
from datetime import datetime
from decimal import Decimal

import httpx

from app.market import SHANGHAI, SOURCE, normalize_symbol
from app.market_history import parse_klines
from app.tools.calculations import CalculateChangeArguments, calculate_change
from app.tools.market_data import DailyPricesArguments, StockNotFoundError, get_daily_prices


class MarketDataUnavailable(Exception):
    pass


class MarketRangeError(ValueError):
    pass


class MarketHistoryReader:
    def __init__(self, remaining, *, transport=None):
        self.remaining = remaining
        self.transport = transport
        self.cache = {}
        self.attempts = 0
        self.network_attempts = 0

    async def fetch(self, code, arguments):
        content = await self.fetch_bytes(
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            {"param": f"{code},day,{arguments.start_date},{arguments.end_date},320,"},
        )
        return httpx.Response(200, content=content).json()

    async def fetch_bytes(self, url, params=None):
        budget = min(8, self.remaining())
        if budget <= 0:
            raise TimeoutError("行情查询超时")
        if self.network_attempts >= 8:
            raise MarketRangeError("每次研究最多8次行情请求，请缩小查询范围")
        self.network_attempts += 1
        async with (
            asyncio.timeout(budget),
            httpx.AsyncClient(
                timeout=budget, transport=self.transport, trust_env=False, follow_redirects=False
            ) as client,
        ):
            async with client.stream(
                "GET",
                url,
                params=params,
            ) as response:
                response.raise_for_status()
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 1048576:
                        raise ValueError("行情响应超出大小限制")
                    chunks.append(chunk)
                return b"".join(chunks)

    @staticmethod
    def result(arguments, rows, kind, source, fetched_at, status, warnings):
        dates = [row["trade_date"] for row in rows]
        ordered = sorted(rows, key=lambda row: row["trade_date"])
        change = None
        online = kind == "online_market"
        if online and len(ordered) >= 2:
            change = calculate_change(
                CalculateChangeArguments(
                    previous_close=Decimal(ordered[0]["close"]),
                    current_close=Decimal(ordered[-1]["close"]),
                )
            )["change_percent"]
        return dict(
            stock_code=arguments.stock_code,
            start_date=arguments.start_date.isoformat(),
            end_date=arguments.end_date.isoformat(),
            adjustment="none" if online else None,
            rows=sorted(rows, key=lambda row: row["trade_date"], reverse=True),
            source_kind=kind,
            source=source,
            fetched_at=fetched_at,
            data_status=status,
            latest_trade_date=max(dates, default=None),
            warnings=warnings,
            coverage="本次源返回的记录；未验证全部交易日是否齐全。",
            summary=dict(
                record_count=len(rows),
                first_trade_date=min(dates, default=None),
                last_trade_date=max(dates, default=None),
                change_percent=change,
                change_basis=(
                    "首末返回交易日收盘价，不复权；由程序计算"
                    if online
                    else "本地价格复权口径未知，暂不计算区间涨跌幅"
                ),
            ),
        )

    def __call__(self, arguments: DailyPricesArguments, session):
        self.remaining()
        now = datetime.now(SHANGHAI)
        if (arguments.end_date - arguments.start_date).days + 1 > 366:
            raise MarketRangeError("在线日线每次最多查询 366 天，请将更长区间拆分查询")
        if arguments.start_date.year < 1990 or arguments.end_date > now.date():
            raise MarketRangeError("查询日期须在 1990 年至今天之间")
        code = normalize_symbol(arguments.stock_code)
        arguments = arguments.model_copy(update={"stock_code": code[2:] + "." + code[:2].upper()})
        key = (code, arguments.start_date, arguments.end_date)
        if key in self.cache:
            return self.cache[key]
        if self.attempts >= 4:
            raise MarketRangeError("本次研究最多查询 4 个不同区间，请缩小范围")
        self.attempts += 1
        try:
            payload = asyncio.run(self.fetch(code, arguments))
            self.remaining()
            now = datetime.now(SHANGHAI)
            if not isinstance(payload, dict) or payload.get("code") != 0:
                raise ValueError("行情源响应格式无效")
            data = payload.get("data")
            if not isinstance(data, dict) or not isinstance(data.get(code), dict):
                raise ValueError("行情源缺少股票数据")
            if data[code].get("day") == []:
                result = self.result(
                    arguments,
                    [],
                    "online_market",
                    SOURCE,
                    now.isoformat(),
                    "no_data",
                    ["数据源未返回该区间记录，不能据此推定停牌或无风险。"],
                )
            else:
                history = parse_klines(payload, code, "day", now, "none")
                bars = [
                    bar
                    for bar in history["bars"]
                    if arguments.start_date.isoformat()
                    <= bar["date"]
                    <= arguments.end_date.isoformat()
                ]
                rows = [
                    dict(
                        trade_date=bar["date"],
                        open=bar["open"],
                        high=bar["high"],
                        low=bar["low"],
                        close=bar["close"],
                        volume_lots=bar["volume_lots"],
                        volume_shares=str(Decimal(bar["volume_lots"]) * 100),
                    )
                    for bar in bars
                ]
                result = self.result(
                    arguments,
                    rows,
                    "online_market",
                    SOURCE,
                    history["fetched_at"],
                    "available" if rows else "no_data",
                    [] if rows else ["源返回数据不覆盖请求区间。"],
                )
        except MarketRangeError:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            self.remaining()
            rows = []
            if session is not None:
                try:
                    rows = get_daily_prices(arguments, session)
                except StockNotFoundError:
                    pass
            if not rows:
                raise MarketDataUnavailable(
                    "在线日线获取失败，本地也没有该区间记录；请稍后重试，不表示市场无数据。"
                ) from exc
            result = self.result(
                arguments,
                rows,
                "local_database",
                None,
                None,
                "local_fallback",
                [
                    "在线源获取失败，使用本地已有记录；上游来源、采集时间、复权口径及成交量单位未知。"
                ],
            )
        self.cache[key] = result
        return result
