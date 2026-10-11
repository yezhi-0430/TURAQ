import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app import market

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone(timedelta(hours=8)))


def minute_payload(rows):
    fields = [''] * 38
    fields[4], fields[30] = '10', '20261009150000'
    return {'code': 0, 'data': {'sh600519': {
        'data': {'date': '20261009', 'data': rows}, 'qt': {'sh600519': fields}}}}


def test_minute_volume_average_and_previous_close():
    result = market.parse_minutes(minute_payload([
        '0931 12 15 17000', '0930 10 10 10000', '0931 12 15 17000',
        '0932 12 15 17000']), 'sh600519', NOW)
    assert result['previous_close'] == '10'
    assert [p['volume_lots'] for p in result['points']] == ['10', '5', '0']
    assert Decimal(result['points'][1]['average_price']) == Decimal('17000') / 1500
    assert result['points'][1]['change_percent'] == '20.00'


def test_missing_amount_and_volume_do_not_invent_average():
    result = market.parse_minutes(minute_payload(['0930 10', '0931 11']), 'sh600519', NOW)
    assert result['points'][0]['average_price'] is None
    assert result['points'][0]['volume_lots'] is None


def test_wrong_day_snapshot_does_not_supply_previous_close():
    payload = minute_payload(['0930 10 1 1000'])
    payload['data']['sh600519']['qt']['sh600519'][30] = '20261008150000'
    assert market.parse_minutes(payload, 'sh600519', NOW)['previous_close'] is None


def test_decreasing_cumulative_volume_is_unavailable_not_negative():
    result = market.parse_minutes(minute_payload(['0930 10 10 10000', '0931 10 5 5000']),
                                  'sh600519', NOW)
    assert result['points'][1]['volume_lots'] is None
    assert result['points'][1]['average_price'] is None


def test_other_index_never_uses_stock_vwap():
    payload = minute_payload(['0930 2798.85 188263 727315881.70'])
    payload['data']['sh000016'] = payload['data'].pop('sh600519')
    result = market.parse_minutes(payload, 'sh000016', NOW)
    assert result['points'][0]['average_price'] is None


def history_payload(period='day', rows=None):
    return {'code': 0, 'data': {'sh600519': {period: rows or [
        ['2026-10-08', '10', '11', '12', '9', '100.5'],
        ['2026-10-09', '11', '12', '13', '10', '200']]}}}


@pytest.mark.parametrize('period', ['day', 'week', 'month'])
def test_kline_source_ohlc_units_and_percent(period):
    result = market.parse_klines(history_payload(period), 'sh600519', period, NOW)
    assert result['adjustment'] == 'none'
    assert result['bars'][0]['change_percent'] is None
    bar = result['bars'][1]
    assert (bar['open'], bar['close'], bar['high'], bar['low']) == ('11', '12', '13', '10')
    assert Decimal(bar['volume_lots']) == 200
    assert bar['change_percent'] == '9.09'


@pytest.mark.parametrize('row', [
    ['2099-10-09', '10', '11', '12', '9', '100'],
    ['2026-10-09', '10', '11', '8', '9', '100'],
    ['2026-10-09', 'NaN', '11', '12', '9', '100'],
    ['2026-10-09', '10', '11', '12', '9', '-1'],
])
def test_kline_invalid_records_rejected(row):
    with pytest.raises(ValueError):
        market.parse_klines(history_payload(rows=[row]), 'sh600519', 'day', NOW)


def test_history_cache_period_isolation_and_stale_failure():
    async def run():
        tick = [0.0]
        calls = []
        async def handle(request):
            calls.append(request)
            period = request.url.params['param'].split(',')[1]
            if tick[0] > 30:
                raise httpx.ConnectError('offline')
            return httpx.Response(200, json=history_payload(period))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            service = market.MarketService(client=client, clock=lambda: tick[0], now=lambda: NOW)
            first = await service.klines('600519.SH', 'day')
            assert first['bars'] and not first['stale']
            await service.klines('600519.SH', 'day')
            assert len(calls) == 1
            assert (await service.klines('600519.SH', 'week'))['period'] == 'week'
            tick[0] = 31
            stale = await service.klines('600519.SH', 'day')
            assert stale['stale'] and stale['bars'] == first['bars'] and stale['error']
            await service.klines('600519.SH', 'day')
            assert len(calls) == 3
            with pytest.raises(ValueError):
                await service.klines('600519.SH', 'year')
    asyncio.run(run())
