"""Validate actual OHLC series without mixing adjustment bases."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

PERIODS = ('day', 'week', 'month')
ADJUSTMENTS = ('none', 'qfq', 'hfq')
MAX_BARS = 320
# The provider occasionally returns a row or two beyond the requested count
# (e.g. index series append the live session); keep the newest MAX_BARS.
MAX_SOURCE_ROWS = MAX_BARS + 10


def parse_klines(payload: dict, code: str, period: str, now: datetime,
                 adjustment: str = 'none') -> dict:
    if period not in PERIODS or adjustment not in ADJUSTMENTS or payload.get('code') != 0:
        raise ValueError('K线周期或源响应无效')
    key = ('' if adjustment == 'none' else adjustment) + period
    rows = payload['data'][code].get(key)
    if not isinstance(rows, list) or not rows or len(rows) > MAX_SOURCE_ROWS:
        raise ValueError('暂无有效的真实K线数据')
    records = {}
    for row in rows:
        try:
            day = datetime.strptime(row[0], '%Y-%m-%d').date()
            op, close, high, low, volume = (Decimal(str(v)) for v in row[1:6])
            if day > now.date() or day.year < 1990:
                raise ValueError('K线日期无效')
            if not all(v.is_finite() for v in (op, close, high, low, volume)):
                raise ValueError('K线数字无效')
            if not (low <= op <= high and low <= close <= high and volume >= 0):
                raise ValueError('K线价格或成交量无效')
            if adjustment != 'qfq' and low <= 0:
                raise ValueError('K线价格或成交量无效')
            records[day.isoformat()] = {
                'date': day.isoformat(), 'open': str(op), 'close': str(close),
                'high': str(high), 'low': str(low), 'volume_lots': str(volume),
            }
        except (InvalidOperation, IndexError, TypeError) as exc:
            raise ValueError('K线字段无效') from exc
    bars, previous = [], None
    for day in sorted(records):
        bar = records[day]
        close = Decimal(bar['close'])
        bar['change_percent'] = str(((close / previous - 1) * 100).quantize(
            Decimal('0.01'))) if previous is not None and previous > 0 and close > 0 else None
        bars.append(bar)
        previous = close
    bars = bars[-MAX_BARS:]
    return {'code': code, 'period': period, 'adjustment': adjustment,
            'trade_date': bars[-1]['date'], 'fetched_at': now.isoformat(),
            'source': '腾讯财经公开行情', 'bars': bars}


def reconcile_latest_month(history: dict, daily: dict) -> dict:
    """The provider's unfinished HFQ month can be wrong; aggregate real matching daily bars."""
    if (history['code'] != daily['code'] or history['adjustment'] != daily['adjustment']
            or history['trade_date'] != daily['trade_date']):
        raise ValueError('月线与同口径日线的日期不一致')
    month = history['trade_date'][:7]
    bars = [bar for bar in daily['bars'] if bar['date'].startswith(month)]
    volume = sum((Decimal(bar['volume_lots']) for bar in bars), Decimal(0))
    if not bars or volume != Decimal(history['bars'][-1]['volume_lots']):
        raise ValueError('缺少完整月份的真实日线，无法核验月K')
    last = {
        'date': bars[-1]['date'], 'open': bars[0]['open'], 'close': bars[-1]['close'],
        'high': str(max(Decimal(bar['high']) for bar in bars)),
        'low': str(min(Decimal(bar['low']) for bar in bars)), 'volume_lots': str(volume),
    }
    previous = Decimal(history['bars'][-2]['close']) if len(history['bars']) > 1 else None
    close = Decimal(last['close'])
    last['change_percent'] = str(((close / previous - 1) * 100).quantize(
        Decimal('0.01'))) if previous is not None and previous > 0 and close > 0 else None
    return {**history, 'bars': [*history['bars'][:-1], last],
            'latest_bar_source': 'daily_aggregation'}
