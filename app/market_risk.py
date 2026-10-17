"""Bounded public sector context and transparent, provisional market attention rules."""

import asyncio
import json
import re
from datetime import date, datetime, time
from decimal import Decimal

from app.market import SHANGHAI, normalize_symbol
from app.tools.market_data import DailyPricesArguments

RULE = "market_attention_v1"
NOTE = "市场风险参考等级，基于已观测量价；阈值待回测，不是公司安全认证或买卖指令。"


def num(value):
    try:
        v = Decimal(str(value))
        return v if v.is_finite() else None
    except Exception:
        return None


def rounded(v):
    return float(round(v, 4)) if v is not None else None


def select_boards(records, symbol):
    boards = {}
    for r in records[:100]:
        code = r.get("NEW_BOARD_CODE", "")
        if r.get("SECUCODE") != symbol or not re.fullmatch(r"BK\d{4}", code):
            continue
        industry = r.get("BOARD_TYPE") == "行业"
        reason = r.get("SELECTED_BOARD_REASON")
        if not industry and not reason:
            continue
        boards[code] = dict(
            code=code,
            name=str(r.get("BOARD_NAME", ""))[:80],
            kind="industry" if industry else "theme",
            membership_reason=str(reason or "")[:300],
        )
    industry = [r for r in boards.values() if r["kind"] == "industry"][:1]
    themes = [r for r in boards.values() if r["kind"] == "theme"][:2]
    return industry + themes


def clean_rows(rows, today, closed_today):
    valid = {}
    for row in rows:
        try:
            day = date.fromisoformat(row["trade_date"])
            close = num(row.get("close"))
            if close is None or close <= 0 or day > today or (day == today and not closed_today):
                continue
            valid[day.isoformat()] = {**row, "close": close}
        except (ValueError, KeyError, TypeError):
            continue
    return [valid[k] for k in sorted(valid)]


def assess_market(rows, peers, *, today=None, closed_today=True):
    today = today or datetime.now(SHANGHAI).date()
    rows = clean_rows(rows, today, closed_today)
    output = dict(
        rule_version=RULE,
        risk_level="unknown",
        basis=[],
        metrics={},
        comparisons=[],
        latest_trade_date=rows[-1]["trade_date"] if rows else None,
        record_count=len(rows),
        limitations=[NOTE],
        dimensions={},
    )
    if len(rows) < 26 or (today - date.fromisoformat(rows[-1]["trade_date"])).days > 7:
        output["basis"] = ["已收盘同口径样本不足26条，或最新交易日超过7自然日；暂不评级。"]
        return output
    closes = [r["close"] for r in rows]
    last = closes[-1]
    ma5, ma20 = sum(closes[-5:]) / 5, sum(closes[-20:]) / 20
    old_ma20 = sum(closes[-25:-5]) / 20
    change20 = (last / closes[-21] - 1) * 100
    change5 = (last / closes[-6] - 1) * 100
    daily = (last / closes[-2] - 1) * 100
    peak, drawdown = closes[-21], Decimal(0)
    for c in closes[-21:]:
        peak = max(peak, c)
        drawdown = max(drawdown, (1 - c / peak) * 100)
    volumes = [num(r.get("volume_lots")) for r in rows[-21:]]
    ratio = None
    if all(v is not None and v >= 0 for v in volumes):
        avg = sum(volumes[:-1]) / 20
        if avg > 0:
            ratio = volumes[-1] / avg
    downtrend = last < ma20 and ma5 < ma20 and ma20 < old_ma20
    output["metrics"] = dict(
        close=rounded(last),
        ma5=rounded(ma5),
        ma20=rounded(ma20),
        ma20_change=rounded(ma20 - old_ma20),
        change5_percent=rounded(change5),
        change20_percent=rounded(change20),
        daily_change_percent=rounded(daily),
        drawdown20_percent=rounded(drawdown),
        volume_ratio20=rounded(ratio),
    )
    level = "medium" if downtrend else "low"
    trend = (
        "下行"
        if downtrend
        else "上行"
        if last > ma20 and ma5 > ma20 and ma20 > old_ma20
        else "震荡"
    )
    output["dimensions"] = dict(
        trend=trend,
        volume="放量"
        if ratio and ratio >= 2
        else "缩量"
        if ratio is not None and ratio < Decimal(".7")
        else "平稳"
        if ratio is not None
        else "量能数据不足",
    )
    output["basis"].append(
        f"趋势{trend}：收盘{last}，MA5={ma5:.4f}，MA20={ma20:.4f}，"
        f"MA20较5个观测日前变化{ma20 - old_ma20:.4f}。"
    )
    output["basis"].append(
        f"20个观测日变化{change20:.2f}%，收盘回撤{drawdown:.2f}%；"
        + (f"最新量/前20日均量{ratio:.2f}倍。" if ratio is not None else "缺少同单位量能。")
    )
    if (downtrend and change20 <= -10 and drawdown >= 15) or (
        ratio is not None and daily <= -5 and ratio >= 2
    ):
        level = "high"
        output["basis"].append("触发显著下行回撤或放量下跌警示。")
    for peer in peers:
        p_rows = clean_rows(peer.get("rows", []), today, closed_today)
        stock_map = {r["trade_date"]: r["close"] for r in rows}
        peer_map = {r["trade_date"]: r["close"] for r in p_rows}
        dates = sorted(stock_map.keys() & peer_map.keys())[-21:]
        entry = {k: peer.get(k) for k in ("name", "code", "kind", "membership_reason", "error")}
        entry.update(common_dates=dates, change_percent=None, relative_change_points=None)
        if len(dates) >= 21 and dates[-1] == rows[-1]["trade_date"]:
            a, b = dates[0], dates[-1]
            pchange = (peer_map[b] / peer_map[a] - 1) * 100
            rel = (stock_map[b] / stock_map[a] - 1) * 100 - pchange
            entry.update(change_percent=rounded(pchange), relative_change_points=rounded(rel))
            output["basis"].append(
                f"{entry['name']}同期{pchange:.2f}%，个股相对变化{rel:.2f}个百分点。"
            )
            if entry.get("kind") == "industry" and (pchange <= -10 or rel <= -5) and level == "low":
                level = "medium"
                output["basis"].append("行业明显下行或个股明显弱于行业，提高至中等关注。")
        output["comparisons"].append(entry)
    if ratio is None:
        output["limitations"].append("量能缺失，评级仅反映趋势/回撤及已可比的板块。")
    output["limitations"].append(
        "不复权，除权除息可能影响趋势；缺失交易日未核验，观测日不保证完整交易日。"
    )
    output["risk_level"] = level
    return output


class MarketContextReader:
    def __init__(self, history):
        self.history = history
        self.cache = {}

    async def _sectors(self, symbol, start, end):
        raw = await self.history.fetch_bytes(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            dict(
                reportName="RPT_F10_CORETHEME_BOARDTYPE",
                columns="ALL",
                filter=f'(SECUCODE="{symbol}")',
                pageSize=100,
                pageNumber=1,
            ),
        )
        body = json.loads(raw)
        result = body.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ValueError("未返回所属板块资料")
        boards = select_boards(result["data"], symbol)
        for board in boards:
            try:
                raw = await self.history.fetch_bytes(
                    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
                    dict(
                        secid="90." + board["code"],
                        klt=101,
                        fqt=0,
                        beg=start.strftime("%Y%m%d"),
                        end=end.strftime("%Y%m%d"),
                        lmt=320,
                        fields1="f1,f2,f3,f4,f5,f6",
                        fields2="f51,f52,f53,f54,f55,f56",
                    ),
                )
                data = json.loads(raw).get("data")
                if not isinstance(data, dict) or data.get("code") != board["code"]:
                    raise ValueError("板块身份不匹配")
                records = data.get("klines")
                if not isinstance(records, list) or len(records) > 320:
                    raise ValueError("板块日线无效")
                rows = []
                for r in records:
                    cells = r.split(",")
                    day = date.fromisoformat(cells[0])
                    if start <= day <= end:
                        rows.append(dict(trade_date=cells[0], close=cells[2], volume_lots=cells[5]))
                board["rows"] = rows
            except Exception as exc:
                # Optional peers must not discard already acquired stock/other-board records.
                board.update(rows=[], error="板块读取失败：" + type(exc).__name__)
        return boards

    def analyze(self, arguments, session):
        key = (arguments.stock_code, arguments.start_date, arguments.end_date)
        self.history.remaining()
        if key in self.cache:
            return self.cache[key]
        args = DailyPricesArguments(
            stock_code=arguments.stock_code,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
        )
        stock = self.history(args, session)
        peers, warnings = [], list(stock["warnings"])
        try:
            normalized = normalize_symbol(arguments.stock_code)
            symbol = normalized[2:] + "." + normalized[:2].upper()
            peers = asyncio.run(self._sectors(symbol, args.start_date, args.end_date))
        except Exception as exc:
            warnings.append("板块资料未取得：" + type(exc).__name__ + "；不猜行业、题材或强弱。")
        try:
            base = self.history(
                DailyPricesArguments(
                    stock_code="000300.SH", start_date=args.start_date, end_date=args.end_date
                ),
                session,
            )
            peers.append(
                dict(
                    name="沪深300",
                    code="000300.SH",
                    kind="benchmark",
                    rows=base["rows"] if base["adjustment"] == "none" else [],
                )
            )
        except Exception:
            warnings.append("大盘对照缺失。")
        now = datetime.now(SHANGHAI)
        assessment = assess_market(
            stock["rows"] if stock["adjustment"] == "none" else [],
            peers,
            today=now.date(),
            closed_today=now.time() >= time(15, 10),
        )
        warnings.extend(assessment["limitations"])
        has_sector = any(
            p.get("kind") != "benchmark" and p.get("relative_change_points") is not None
            for p in assessment["comparisons"]
        )
        from app.tools.research import calculation_base

        _, metadata = calculation_base(stock)
        used_rows = clean_rows(
            stock["rows"] if stock["adjustment"] == "none" else [],
            now.date(),
            now.time() >= time(15, 10),
        )
        metadata["input_data"].update(
            record_count=assessment["record_count"],
            latest_trade_date=assessment["latest_trade_date"],
            first_trade_date=used_rows[0]["trade_date"] if used_rows else None,
        )
        if any(p.get("kind") != "benchmark" for p in peers):
            metadata["input_data"]["source"] = (
                str(metadata["input_data"]["source"]) + "；东方财富公开板块资料与板块日线"
            )
        output = dict(
            stock_code=arguments.stock_code,
            assessment=assessment,
            data_status="insufficient_data"
            if assessment["risk_level"] == "unknown"
            else "available"
            if has_sector
            else "partial",
            input_data=metadata["input_data"],
            warnings=warnings,
            sector_source="东方财富公开板块资料与板块日线",
            sector_observed_at=now.isoformat(),
            sector_coverage="available" if has_sector else "partial",
            methods=NOTE,
        )
        self.cache[key] = output
        return output
