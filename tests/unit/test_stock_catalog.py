import asyncio
import io
import json
import zipfile

import httpx
import pytest


@pytest.fixture(autouse=True)
def clean_test_database():
    yield


def szse_xlsx(rows):
    """Build a minimal xlsx shaped like the SZSE export (inline strings + shared strings)."""
    shared = ["A股简称"]
    cells = []
    for index, row in enumerate([["板块", "A股代码", "A股简称"], *rows], start=1):
        parts = []
        for value in row:
            if value == "A股简称":
                parts.append('<c t="s"><v>0</v></c>')
            else:
                parts.append(f'<c t="inlineStr"><is><t>{value}</t></is></c>')
        cells.append(f'<row r="{index}">{"".join(parts)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr(
            "xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in shared)
            + "</sst>",
        )
        book.writestr(
            "xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{''.join(cells)}"
            "</sheetData></worksheet>",
        )
    return buffer.getvalue()


def exchanges(*, sse_main=2, szse_rows=None, bse_total=None, fail=None):
    szse_rows = szse_rows or [["主板", "000002", "万  科Ａ"], ["创业板", "300001", "特锐德"]]
    bse = [dict(xxzqdm=f"92000{i}", xxzqjc=f"北{i}") for i in range(3)]

    def handler(request):
        host = request.url.host
        if fail == host:
            return httpx.Response(503)
        if host == "query.sse.com.cn":
            kind = request.url.params["STOCK_TYPE"]
            rows = (
                [dict(A_STOCK_CODE=f"60000{i}", SEC_NAME_CN=f"沪{i}") for i in range(sse_main)]
                if kind == "1"
                else [dict(A_STOCK_CODE="688001", SEC_NAME_CN="华兴源创")]
            )
            return httpx.Response(200, json=dict(result=rows, pageHelp=dict(total=len(rows))))
        if host == "www.szse.cn":
            return httpx.Response(200, content=szse_xlsx(szse_rows))
        if host == "www.bse.cn":
            page = int(dict(x.split("=") for x in request.content.decode().split("&"))["page"])
            body = dict(
                content=bse[page * 2 : page * 2 + 2],
                totalPages=2,
                totalElements=bse_total or len(bse),
            )
            return httpx.Response(200, text="null(" + json.dumps([body]) + ")")
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def service(tmp_path, stocks=()):
    from app.stock_list import StockListService

    s = StockListService.__new__(StockListService)
    s.stocks, s.symbol_map, s.code_map, s.last_updated = list(stocks), {}, {}, None
    s._lock = asyncio.Lock()
    target = tmp_path / "stocks_base.json"
    original = s._save_to_file
    s._save_to_file = lambda: original(str(target))
    return s, target


def test_refresh_merges_all_three_exchanges_and_normalizes_names(tmp_path):
    s, target = service(tmp_path)
    updated, detail = asyncio.run(s.update_from_api(transport=exchanges()))
    assert updated, detail
    symbols = [x["symbol"] for x in s.stocks]
    assert symbols == [
        "000002.SZ", "300001.SZ", "600000.SH", "600001.SH", "688001.SH",
        "920000.BJ", "920001.BJ", "920002.BJ",
    ]
    assert s.get_by_symbol("000002.SZ")["name"] == "万科A"
    assert [x["symbol"] for x in s.search("万科a")] == ["000002.SZ"]
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["total"] == 8 and "北交所" in saved["source"]


def test_one_failed_exchange_keeps_existing_catalog(tmp_path):
    old = [dict(symbol="600519.SH", code="sh600519", name="贵州茅台", market="sh")]
    s, target = service(tmp_path, old)
    updated, detail = asyncio.run(s.update_from_api(transport=exchanges(fail="www.bse.cn")))
    assert not updated and "保留现有目录" in detail
    assert s.stocks == old and not target.exists()


def test_truncated_listing_is_rejected_instead_of_overwriting(tmp_path):
    """The old fallback once returned 200 of ~5000 stocks and would have replaced the file."""
    old = [
        dict(symbol=f"60{i:04d}.SH", code=f"sh60{i:04d}", name=f"沪{i}", market="sh")
        for i in range(100)
    ] + [
        dict(symbol="000002.SZ", code="sz000002", name="万科A", market="sz"),
        dict(symbol="920000.BJ", code="bj920000", name="北0", market="bj"),
    ]
    s, target = service(tmp_path, old)
    updated, detail = asyncio.run(s.update_from_api(transport=exchanges(sse_main=2)))
    assert not updated and "sh市场新名单仅3只（原100只）" in detail
    assert len(s.stocks) == 102 and not target.exists()


def test_incomplete_pagination_is_rejected(tmp_path):
    s, _ = service(tmp_path)
    updated, detail = asyncio.run(s.update_from_api(transport=exchanges(bse_total=50)))
    assert not updated and "ValueError" in detail


def test_scheduled_job_counts_rejection_as_failure(monkeypatch):
    from app import tasks

    async def rejected():
        return False, "sh市场新名单仅3只"

    monkeypatch.setattr(tasks.stock_list_service, "update_from_api", rejected)
    monkeypatch.setattr(tasks, "_consecutive_failures", 0)
    asyncio.run(tasks.update_stock_list())
    assert tasks._consecutive_failures == 1

    async def accepted():
        return True, "4955 -> 4955"

    monkeypatch.setattr(tasks.stock_list_service, "update_from_api", accepted)
    asyncio.run(tasks.update_stock_list())
    # An unchanged count is a successful refresh, not a failure.
    assert tasks._consecutive_failures == 0
