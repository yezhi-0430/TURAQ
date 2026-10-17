import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.market import MarketService, normalize_symbol, parse_minutes, parse_quotes

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone(timedelta(hours=8)))


def quote(symbol='sz000001', price='11.59'):
    fields = [''] * 38
    for i, value in {1:'平安银行', 2:symbol[2:], 3:price, 4:'11.78', 5:'11.78',
                     6:'1078106', 30:'20261009161500', 31:'-0.19', 32:'-1.61',
                     33:'11.89', 34:'11.58', 36:'1078106', 37:'125972'}.items():
        fields[i] = value
    return 'v_' + symbol + '="' + '~'.join(fields) + '";'


@pytest.mark.parametrize(('value', 'expected'), [
    ('000001', 'sz000001'), ('000001.SH', 'sh000001'),
    ('600519.sh', 'sh600519'), (' SZ000001 ', 'sz000001'), ('920001', 'bj920001'),
])
def test_symbol(value, expected):
    assert normalize_symbol(value) == expected


@pytest.mark.parametrize('value', ['foo', 'sh000001,sz000001', '../secret', '123', '123456'])
def test_bad_symbol(value):
    with pytest.raises(ValueError):
        normalize_symbol(value)


def test_quote_precision_units_and_time():
    q = parse_quotes(quote(), NOW)['sz000001']
    assert q['price'] == '11.59'
    assert q['amount_yuan'] == str(Decimal('125972') * 10000)
    assert q['volume_lots'] == 1078106
    assert q['quote_time'] == '2026-10-09T16:15:00+08:00'
    assert q['symbol'] == '000001.SZ'


@pytest.mark.parametrize('price', ['NaN', 'Infinity', '-1', ''])
def test_invalid_quote_rejected(price):
    assert parse_quotes(quote(price=price), NOW) == {}


def test_zero_price_is_unavailable_not_a_crash():
    assert parse_quotes(quote(price='0'), NOW)['sz000001']['price'] is None


def test_future_timestamp_rejected():
    assert parse_quotes(quote().replace('20261009161500', '20991009161500'), NOW) == {}


def test_minute_series_keeps_actual_times():
    payload = {'code':0, 'data':{'sz000001':{'data':{'date':'20261009',
        'data':['0930 11.78 7508', '0931 11.83 62344', '1530 11.59 1078143']}}}}
    result = parse_minutes(payload, 'sz000001', NOW)
    assert result['trade_date'] == '2026-10-09'
    assert result['points'][2]['time'] == '15:30'
    assert result['points'][2]['price'] == '11.59'
    assert result['points'][2]['volume_lots'] == '1015799'


def test_cache_coalescing_and_stale_outage():
    async def run():
        clock = [0.0]
        calls = []
        async def handle(request):
            calls.append(request)
            await asyncio.sleep(0)
            if len(calls) > 1:
                raise httpx.ConnectError('offline')
            return httpx.Response(200, content=quote().encode('gb18030'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            service = MarketService(client=client, clock=lambda:clock[0], now=lambda:NOW)
            a,b = await asyncio.gather(service.quotes(['sz000001']), service.quotes(['sz000001']))
            assert len(calls) == 1
            assert not a['stale'] and not b['stale']
            clock[0] = 11
            failed = await service.quotes(['sz000001'])
            assert failed['stale'] and failed['quotes'][0]['price'] == '11.59'
            n = len(calls)
            await service.quotes(['sz000001'])
            assert len(calls) == n  # outage cooldown, no request hammering
    asyncio.run(run())

def test_partial_response_preserves_last_real_quote():
    async def run():
        tick = [0.0]
        calls = [0]
        async def handle(request):
            calls[0] += 1
            text = quote() + quote('sh600519') if calls[0] == 1 else quote('sh600519')
            return httpx.Response(200, content=text.encode('gb18030'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            service = MarketService(client=client, clock=lambda:tick[0], now=lambda:NOW)
            await service.quotes(['sz000001','sh600519'])
            tick[0] = 11
            result = await service.quotes(['sz000001','sh600519'])
            saved = {q['code']:q for q in result['quotes']}
            assert saved['sz000001']['price'] == '11.59'
            assert saved['sz000001']['stale']
            assert result['stale'] and result['error']
    asyncio.run(run())

def test_unknown_symbol_does_not_block_other_quotes():
    async def run():
        async def handle(request):
            text = '' if 'sz999999' in str(request.url) else quote()
            return httpx.Response(200, content=text.encode('gb18030'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            service = MarketService(client=client, now=lambda:NOW)
            unknown = await service.quotes(['sz999999'])
            assert unknown['unavailable'] == ['sz999999']
            result = await service.quotes(['sz000001'])
            assert result['quotes'][0]['price'] == '11.59'
    asyncio.run(run())


def test_invalid_minute_price_returns_error_payload():
    async def run():
        payload = {'code':0, 'data':{'sz000001':{'data':{'date':'20261009',
            'data':['0930 bad 7508']}}}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request:httpx.Response(200,json=payload))) as client:
            result = await MarketService(client=client, now=lambda:NOW).minutes('sz000001')
            assert result['stale'] and result['points'] == []
    asyncio.run(run())
