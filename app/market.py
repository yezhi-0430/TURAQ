"""Read-only public market snapshots. No synthetic data or model calls."""
import asyncio
import re
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from time import monotonic

import httpx

from app.market_history import ADJUSTMENTS, PERIODS, parse_klines, reconcile_latest_month

SHANGHAI = timezone(timedelta(hours=8))
INDICES = ('sh000001', 'sz399001', 'sz399006', 'sh000300')
SOURCE = '腾讯财经公开行情'


def is_index(code: str) -> bool:
    return code.startswith(('sh000', 'sh950', 'sz399', 'bj899'))


def normalize_symbol(value: str) -> str:
    value = value.strip().lower()
    if re.fullmatch(r'\d{6}\.(sh|sz|bj)', value):
        value = value[-2:] + value[:6]
    if re.fullmatch(r'\d{6}', value):
        if value[0] in '69':
            prefix = 'bj' if value.startswith('92') else 'sh'
        elif value[0] in '03':
            prefix = 'sz'
        elif value[0] in '48':
            prefix = 'bj'
        else:
            raise ValueError('无法识别代码，请使用 000001.SZ 等完整代码')
        value = prefix + value
    if not re.fullmatch(r'(sh|sz|bj)\d{6}', value):
        raise ValueError('请输入六位股票代码，或 000001.SZ / SH000001 格式')
    return value


def number(value: str, *, nonnegative: bool = False) -> Decimal:
    result = Decimal(value)
    if not result.is_finite() or (nonnegative and result < 0):
        raise ValueError('非法行情数字')
    return result


def optional_number(value: str):
    try:
        return str(number(value, nonnegative=True)) if value else None
    except (ValueError, InvalidOperation):
        return None


def parse_quotes(text: str, now: datetime) -> dict:
    records = {}
    for code, body in re.findall(r'v_((?:sh|sz|bj)\d{6})="([^"\r\n]*)"', text):
        f = body.split('~')
        try:
            if len(f) < 38 or f[2] != code[2:] or not f[1].strip():
                continue
            stamp = datetime.strptime(f[30], '%Y%m%d%H%M%S').replace(tzinfo=SHANGHAI)
            if stamp > now + timedelta(minutes=5) or stamp.year < 1990:
                continue
            price = number(f[3], nonnegative=True)
            previous = number(f[4], nonnegative=True)
            # Zero is the provider's no-trade/unavailable price, never a -100% move.
            change = price - previous if price > 0 and previous > 0 else None
            percent = change / previous * 100 if change is not None else None
            lots = number(f[36], nonnegative=True) if f[36] else None
            if lots is not None and lots != lots.to_integral_value():
                continue
            amount = optional_number(f[37])
            records[code] = {
                'code': code, 'symbol': code[2:] + '.' + code[:2].upper(),
                'name': f[1], 'kind': 'index' if is_index(code) else 'stock',
                'price': str(price) if price > 0 else None,
                'previous_close': str(previous) if previous > 0 else None,
                'change': str(change) if change is not None else None,
                'change_percent': str(percent.quantize(Decimal('0.01'))) if percent else (
                    '0.00' if percent is not None else None
                ),
                'open': optional_number(f[5]), 'high': optional_number(f[33]),
                'low': optional_number(f[34]),
                'volume_lots': int(lots) if lots is not None else None,
                'amount_yuan': str(Decimal(amount) * 10000) if amount is not None else None,
                'quote_time': stamp.isoformat(), 'fetched_at': now.isoformat(),
            }
        except (ValueError, InvalidOperation, IndexError):
            continue
    return records


def parse_minutes(payload: dict, code: str, now: datetime) -> dict:
    if payload.get('code') != 0:
        raise ValueError('分时源返回错误')
    raw = payload['data'][code]['data']
    day = datetime.strptime(raw['date'], '%Y%m%d').date()
    if day > now.date() or day.year < 1990:
        raise ValueError('分时日期无效')
    points = {}
    for row in raw['data']:
        parts = row.split()
        if len(parts) < 2:
            raise ValueError('分时字段缺失')
        stamp = datetime.strptime(parts[0], '%H%M').time()
        price = number(parts[1], nonnegative=True)
        if price > 0:
            points[stamp.strftime('%H:%M')] = {
                'time': stamp.strftime('%H:%M'), 'price': str(price),
                'cumulative_volume': optional_number(parts[2]) if len(parts) > 2 else None,
                'cumulative_amount': optional_number(parts[3]) if len(parts) > 3 else None,
            }
    if not points:
        raise ValueError('暂无有效分时数据')
    previous_close = None
    fields = payload['data'][code].get('qt', {}).get(code, [])
    if len(fields) > 30 and fields[30][:8] == raw['date']:
        previous_close = optional_number(fields[4])
        if previous_close is not None and Decimal(previous_close) <= 0:
            previous_close = None
    previous_volume, previous_amount = Decimal(0), Decimal(0)
    result = []
    for _, point in sorted(points.items()):
        lots = point.pop('cumulative_volume')
        amount = point.pop('cumulative_amount')
        lots = Decimal(lots) if lots is not None else None
        amount = Decimal(amount) if amount is not None else None
        consistent = (lots is not None and previous_volume is not None
                      and lots >= previous_volume
                      and (amount is None or previous_amount is None or amount >= previous_amount))
        point['volume_lots'] = str(lots - previous_volume) if consistent else None
        # Stocks: one lot = 100 shares. Index average price is not a stock VWAP.
        point['average_price'] = str(amount / (lots * 100)) if (
            consistent and lots > 0 and amount is not None and amount > 0
            and not is_index(code)) else None
        point['change_percent'] = str(((Decimal(point['price']) / Decimal(previous_close) - 1)
                                      * 100).quantize(Decimal('0.01'))) if previous_close else None
        previous_volume, previous_amount = lots, amount
        result.append(point)
    return {'code': code, 'trade_date': day.isoformat(), 'source': SOURCE,
            'fetched_at': now.isoformat(),
            'previous_close': previous_close, 'points': result}


class MarketService:
    """Batch snapshots with 10s cache, bounded storage and global outage cooldown."""

    def __init__(self, client=None, clock=monotonic, now=None):
        self.client = client
        self.clock = clock
        self.now = now or (lambda: datetime.now(SHANGHAI))
        self.cache = OrderedDict()
        self.quote_attempts = OrderedDict()
        self.minute_cache = OrderedDict()
        self.kline_cache = OrderedDict()
        self.kline_retry = OrderedDict()
        self.kline_lock = asyncio.Lock()
        self.lock = asyncio.Lock()
        self.minute_lock = asyncio.Lock()
        self.retry_after = 0.0
        self.minute_retry_after = 0.0

    async def _get(self, url, params=None):
        if self.client is not None:
            return await self.client.get(url, params=params, timeout=8)
        async with httpx.AsyncClient(timeout=8) as client:
            return await client.get(url, params=params)

    @staticmethod
    def _store(cache, key, value):
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > 256:
            cache.popitem(last=False)

    async def quotes(self, codes: list[str]) -> dict:
        codes = list(dict.fromkeys(normalize_symbol(c) for c in codes))
        if not 1 <= len(codes) <= 40:
            raise ValueError('每次查询 1 至 40 个代码')
        async with self.lock:
            tick = self.clock()
            missing = [c for c in codes if (c not in self.cache or tick-self.cache[c][0] >= 10)
                       and tick-self.quote_attempts.get(c, float('-inf')) >= 10]
            error = None
            if missing:
                if tick < self.retry_after:
                    error = '行情源暂不可用，稍后自动重试'
                else:
                    try:
                        response = await self._get('https://qt.gtimg.cn/q=' + ','.join(missing))
                        response.raise_for_status()
                        fetched = parse_quotes(response.content.decode('gb18030'), self.now())
                        for code in missing:
                            self._store(self.quote_attempts, code, self.clock())
                            if fetched.get(code):
                                self._store(self.cache, code, (self.clock(), fetched[code]))
                        if any(c not in fetched for c in missing):
                            error = '部分证券未返回有效行情，已有数据保留并标记过期'
                    except (httpx.HTTPError, ValueError, UnicodeError):
                        self.retry_after = self.clock() + 15
                        error = '行情源连接失败，已保留上次数据'
            quotes, unavailable = [], []
            for code in codes:
                entry = self.cache.get(code)
                if entry and entry[1]:
                    quotes.append({**entry[1], 'stale': self.clock()-entry[0] >= 10})
                else:
                    unavailable.append(code)
            return {'source': SOURCE, 'quotes': quotes, 'unavailable': unavailable,
                    'stale': bool(error or unavailable) or any(q['stale'] for q in quotes),
                    'error': error, 'checked_at': self.now().isoformat(),
                    'refresh_seconds': 10}

    async def minutes(self, code: str) -> dict:
        code = normalize_symbol(code)
        async with self.minute_lock:
            entry = self.minute_cache.get(code)
            if entry and self.clock()-entry[0] < 30:
                return {**entry[1], 'stale': False}
            if self.clock() < self.minute_retry_after:
                return {**entry[1], 'stale': True,
                        'error': '分时源暂不可用，保留旧数据'} if entry else {
                    'code': code, 'points': [], 'stale': True, 'error': '分时源暂不可用'}
            try:
                response = await self._get(
                    'https://web.ifzq.gtimg.cn/appstock/app/minute/query', {'code': code})
                response.raise_for_status()
                result = parse_minutes(response.json(), code, self.now())
                self._store(self.minute_cache, code, (self.clock(), result))
                return {**result, 'stale': False}
            except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, InvalidOperation):
                self.minute_retry_after = self.clock() + 15
                return {**entry[1], 'stale': True,
                        'error': '分时更新失败，保留旧数据'} if entry else {
                    'code': code, 'points': [], 'stale': True, 'error': '暂无可用的真实分时数据'}

    async def klines(self, code: str, period: str = 'day', adjustment: str = 'none') -> dict:
        code = normalize_symbol(code)
        if period not in PERIODS:
            raise ValueError('K线周期仅支持 day / week / month')
        if adjustment not in ADJUSTMENTS:
            raise ValueError('复权仅支持 none / qfq / hfq')
        if is_index(code) and adjustment != 'none':
            raise ValueError('指数无需股票复权，请使用不复权')
        key = (code, period, adjustment)
        suffix = '' if adjustment == 'none' else adjustment
        async with self.kline_lock:
            entry = self.kline_cache.get(key)
            if entry and self.clock() - entry[0] < 30:
                return {**entry[1], 'stale': False, 'refresh_seconds': 30}
            error = 'K线源暂不可用，保留已有数据'
            if self.clock() >= self.kline_retry.get(key, 0):
                try:
                    response = await self._get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
                                               {'param': f'{code},{period},,,320,{suffix}'})
                    response.raise_for_status()
                    data = parse_klines(response.json(), code, period, self.now(), adjustment)
                    if period == 'month' and adjustment != 'none':
                        daily_key = (code, 'day', adjustment)
                        daily_entry = self.kline_cache.get(daily_key)
                        daily = None
                        if daily_entry and self.clock() - daily_entry[0] < 30:
                            daily = daily_entry[1]
                            try:
                                data = reconcile_latest_month(data, daily)
                            except ValueError:
                                # A new month snapshot may have outgrown the cached daily volume.
                                daily = None
                        if daily is None:
                            response = await self._get(
                                'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
                                {'param': f'{code},day,,,320,{suffix}'})
                            response.raise_for_status()
                            daily = parse_klines(response.json(), code, 'day',
                                                 self.now(), adjustment)
                            self._store(self.kline_cache, daily_key, (self.clock(), daily))
                            data = reconcile_latest_month(data, daily)
                    self._store(self.kline_cache, key, (self.clock(), data))
                    return {**data, 'stale': False, 'refresh_seconds': 30}
                except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
                    self._store(self.kline_retry, key, self.clock() + 15)
                    error = '真实K线获取失败，已有数据标记为旧数据'
            return {**entry[1], 'stale': True, 'error': error} if entry else {
                'code': code, 'period': period, 'adjustment': adjustment,
                'bars': [], 'stale': True, 'error': error}
