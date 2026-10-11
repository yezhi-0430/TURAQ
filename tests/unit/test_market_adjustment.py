import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.market import MarketService, parse_klines
from app.market_history import reconcile_latest_month

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone(timedelta(hours=8)))


def payload(period, adjustment, rows=None):
    key = ('' if adjustment == 'none' else adjustment) + period
    return {'code': 0, 'data': {'sh600519': {key: rows or [
        ['2026-09-30', '10', '11', '12', '9', '100'],
        ['2026-10-09', '11', '12', '13', '10', '200']]}}}


@pytest.mark.parametrize('period', ['day', 'week', 'month'])
@pytest.mark.parametrize('adjustment', ['none', 'qfq', 'hfq'])
def test_matching_adjustment_records(period, adjustment):
    result = parse_klines(payload(period, adjustment), 'sh600519', period, NOW,
                          adjustment=adjustment)
    assert result['adjustment'] == adjustment
    assert result['bars'][1]['close'] == '12'


def test_never_mislabel_unadjusted_as_adjusted():
    with pytest.raises(ValueError):
        parse_klines(payload('day', 'none'), 'sh600519', 'day', NOW, adjustment='qfq')


def test_provider_negative_forward_adjusted_prices_are_preserved():
    result = parse_klines(payload('month', 'qfq', [
        ['2001-08-31', '-314.300', '-313.856', '-313.719', '-314.595', '100'],
        ['2001-09-28', '-313', '-312', '-311', '-314', '200']]),
        'sh600519', 'month', NOW, adjustment='qfq')
    assert result['bars'][0]['close'] == '-313.856'
    assert result['bars'][1]['change_percent'] is None


def test_incomplete_current_month_is_rejected_even_with_older_daily_rows():
    monthly = parse_klines(payload('month', 'hfq'), 'sh600519', 'month', NOW, 'hfq')
    daily = parse_klines(payload('day', 'hfq', [
        ['2026-09-30', '10', '11', '12', '9', '100'],
        ['2026-10-09', '11', '12', '13', '10', '100']]),
        'sh600519', 'day', NOW, 'hfq')
    with pytest.raises(ValueError, match='完整月份'):
        reconcile_latest_month(monthly, daily)


def test_service_adjustment_cache_isolation_and_current_month_aggregation():
    async def run():
        calls = []
        elapsed, incomplete = 0, False
        async def handle(request):
            calls.append(request)
            _, period, _, _, _, adjust = request.url.params['param'].split(',')
            adjust = adjust or 'none'
            if period == 'month' and adjust == 'hfq':
                rows = [['2026-09-30', '8800', '8886.536', '9000', '8700', '100'],
                        ['2026-10-09', '8854.345', '8075.81', '9018.113', '8027.34', '60279']]
            elif period == 'day' and adjust == 'hfq':
                rows = [['2026-09-30', '8800', '8886.536', '9000', '8700', '100'],
                        ['2026-10-08', '8854.345', '8870.609', '8883.047', '8793.002', '25168'],
                        ['2026-10-09', '8868.527', '8911.185', '9018.113', '8868.527', '35111']]
                if incomplete:
                    rows.pop(1)
            else:
                rows = None
            return httpx.Response(200, json=payload(period, adjust, rows))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            service = MarketService(client=client, now=lambda: NOW, clock=lambda: elapsed)
            for adjust in ['none', 'qfq', 'hfq']:
                result = await service.klines('sh600519', 'day', adjust)
                assert result['adjustment'] == adjust
            assert len(calls) == 3
            await service.klines('sh600519', 'day', 'qfq')
            assert len(calls) == 3
            result = await service.klines('sh600519', 'month', 'hfq')
            last = result['bars'][-1]
            assert last['close'] == '8911.185'
            assert last['low'] == '8793.002'
            assert Decimal(last['volume_lots']) == 60279
            assert result['latest_bar_source'] == 'daily_aggregation'
            elapsed, incomplete = 31, True
            stale = await service.klines('sh600519', 'month', 'hfq')
            assert stale['stale'] is True
            assert stale['bars'][-1] == last, 'incomplete refresh retains verified monthly bar'
            with pytest.raises(ValueError):
                await service.klines('sh600519', 'day', 'invalid')
    asyncio.run(run())


@pytest.mark.parametrize('adjustment', ['qfq', 'hfq'])
def test_month_refreshes_recent_daily_cache_when_trading_volume_grows(adjustment):
    async def run():
        elapsed, calls = 0, []

        async def handle(request):
            period = request.url.params['param'].split(',')[1]
            calls.append(period)
            volume = '100' if elapsed == 0 else '200'
            rows = [['2026-09-30', '10', '11', '12', '9', '50'],
                    ['2026-10-09', '11', '12', '13', '10', volume]]
            return httpx.Response(200, json=payload(period, adjustment, rows))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            service = MarketService(client=client, now=lambda: NOW, clock=lambda: elapsed)
            await service.klines('sh600519', 'day', adjustment)
            elapsed = 10
            result = await service.klines('sh600519', 'month', adjustment)
            assert result['stale'] is False
            assert result['bars'][-1]['volume_lots'] == '200'
            assert (await service.klines('sh600519', 'day', adjustment))['bars'][-1][
                'volume_lots'] == '200'
            assert calls == ['day', 'month', 'day']
            assert ('sh600519', 'month', adjustment) not in service.kline_retry
    asyncio.run(run())


@pytest.mark.parametrize('failure', ['incomplete', 'offline'])
def test_month_retains_verified_data_when_daily_cache_retry_fails(failure):
    async def run():
        elapsed, growing, calls = 0, False, []

        async def handle(request):
            period = request.url.params['param'].split(',')[1]
            calls.append(period)
            if growing and period == 'day' and failure == 'offline':
                raise httpx.ConnectError('offline')
            volume = '200' if growing and period == 'month' else '100'
            rows = [['2026-09-30', '10', '11', '12', '9', '50'],
                    ['2026-10-09', '11', '12', '13', '10', volume]]
            return httpx.Response(200, json=payload(period, 'qfq', rows))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            service = MarketService(client=client, now=lambda: NOW, clock=lambda: elapsed)
            verified = await service.klines('sh600519', 'month', 'qfq')
            elapsed = 31
            await service.klines('sh600519', 'day', 'qfq')
            elapsed, growing = 35, True
            result = await service.klines('sh600519', 'month', 'qfq')
            assert result['stale'] is True
            assert result['bars'] == verified['bars']
            assert calls[-2:] == ['month', 'day'], 'retry daily once before retaining old month'
            await service.klines('sh600519', 'month', 'qfq')
            assert len(calls) == 5, 'failed recheck keeps the existing outage cooldown'
    asyncio.run(run())
