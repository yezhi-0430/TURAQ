from datetime import datetime

import httpx
import pytest


@pytest.fixture(autouse=True)
def clean_test_database():
    yield


def test_document_capabilities_are_registered_read_only():
    from app.tools.registry import tool_definitions

    names = {t["function"]["name"] for t in tool_definitions()}
    assert {
        "search_company_reports",
        "list_company_announcements",
        "read_disclosure_document",
        "search_disclosure_text",
        "extract_financial_sections",
        "compare_report_sections",
    } <= names


def test_pdf_child_memory_is_bounded():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.document_parser import limit_process_memory; limit_process_memory(); "
            '\ntry: bytearray(1024*1024*1024)\nexcept MemoryError: print("bounded")',
        ],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0 and b"bounded" in result.stdout


def test_disclosure_listing_filters_symbol_and_rejects_unsafe_paths(tmp_path):
    from app.disclosures import DisclosureReader
    from app.market import SHANGHAI

    rows = [
        dict(
            secCode="600519",
            announcementId="123",
            announcementTitle="<em>2025</em>年年度报告",
            announcementTime=int(datetime(2026, 4, 1, tzinfo=SHANGHAI).timestamp() * 1000),
            adjunctUrl="finalpage/2026-04-01/123.PDF",
        ),
        dict(
            secCode="000001",
            announcementId="124",
            announcementTitle="别的公司",
            announcementTime=1,
            adjunctUrl="finalpage/2024-01-01/124.PDF",
        ),
        dict(
            secCode="600519",
            announcementId="125",
            announcementTitle="坏地址",
            announcementTime=1,
            adjunctUrl="https://evil/private.pdf",
        ),
    ]

    def handler(req):
        if req.url.path.endswith("szse_stock.json"):
            return httpx.Response(
                200, json={"stockList": [dict(code="600519", orgId="gssh0600519", zwjc="贵州茅台")]}
            )
        return httpx.Response(200, json={"announcements": rows, "hasMore": True})

    reader = DisclosureReader(
        lambda: 60, cache_dir=tmp_path, transport=httpx.MockTransport(handler)
    )
    result = reader.list("600519.SH", reports=True, limit=5)
    assert len(result["documents"]) == 1 and result["truncated"]
    assert result["documents"][0]["title"] == "2025年年度报告"
    assert result["documents"][0]["report_period"] == "2025年年度报告"
    assert result["documents"][0]["published_date"] == "2026-04-01"
    assert result["documents"][0]["url"].startswith("https://static.cninfo.com.cn/finalpage/")


def test_reader_requires_known_server_document_and_search_has_real_pages(tmp_path):
    from app.disclosures import DisclosureReader, DisclosureUnavailable

    reader = DisclosureReader(lambda: 60, cache_dir=tmp_path)
    with pytest.raises(DisclosureUnavailable):
        reader.read("../../secret", 1, 2)
    meta = dict(
        document_id="a" * 24,
        symbol="600519.SH",
        title="报告",
        url="https://static.cninfo.com.cn/finalpage/2024-01-01/123.PDF",
        published_date="2024-01-01",
        provider="巨潮资讯网",
        report_period="2023年年度报告",
    )
    reader._write(
        "a" * 24,
        {
            "metadata": meta,
            "pages": [
                {"page": 1, "text": "封面"},
                {"page": 2, "text": "营业收入 100 元\n风险说明"},
            ],
            "warnings": [],
        },
    )
    result = reader.search("a" * 24, "营业收入", 3)
    assert result["excerpts"][0]["page"] == 2
    assert "100 元" in result["excerpts"][0]["text"]
    assert reader.read("a" * 24, 2, 1)["excerpts"][0]["text"].startswith("营业收入")
    with pytest.raises(DisclosureUnavailable):
        reader.read("a" * 24, 3, 1)


def test_listing_supports_continuation_without_losing_later_documents(tmp_path):
    from urllib.parse import parse_qs

    from app.disclosures import DisclosureReader
    from app.market import SHANGHAI

    pages = []

    def handler(req):
        if req.url.path.endswith("szse_stock.json"):
            return httpx.Response(
                200, json={"stockList": [dict(code="600519", orgId="gssh0600519")]}
            )
        page = int(parse_qs(req.content.decode())["pageNum"][0])
        pages.append(page)
        return httpx.Response(
            200,
            json={
                "hasMore": page == 1,
                "totalAnnouncement": 2,
                "announcements": [
                    dict(
                        secCode="600519",
                        announcementTitle="公告" + str(page),
                        announcementTime=int(
                            datetime(2026, 10, 1, tzinfo=SHANGHAI).timestamp() * 1000
                        ),
                        adjunctUrl=f"finalpage/2026-10-01/{page}.pdf",
                    )
                ],
            },
        )

    r = DisclosureReader(lambda: 60, cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    a = r.list("600519.SH", limit=30, page=1)
    b = r.list("600519.SH", limit=30, page=2)
    assert pages == [1, 2] and a["next_page"] == 2 and b["next_page"] is None
    assert a["documents"][0]["document_id"] != b["documents"][0]["document_id"]


def test_small_page_size_can_enumerate_every_source_record(tmp_path):
    from urllib.parse import parse_qs

    from app.disclosures import DisclosureReader
    from app.market import SHANGHAI

    rows = [
        dict(
            secCode="600519", announcementTitle=f"公告{i}",
            announcementTime=int(datetime(2026, 10, 1, tzinfo=SHANGHAI).timestamp() * 1000),
            adjunctUrl=f"finalpage/2026-10-01/{i}.pdf",
        ) for i in range(5)
    ]

    def handler(req):
        if req.url.path.endswith("szse_stock.json"):
            return httpx.Response(200, json={"stockList": [dict(code="600519", orgId="valid")]})
        form = parse_qs(req.content.decode())
        page, size = int(form["pageNum"][0]), int(form["pageSize"][0])
        return httpx.Response(200, json={
            "announcements": rows[(page-1)*size:page*size], "hasMore": page*size < len(rows),
        })

    reader = DisclosureReader(
        lambda: 60, cache_dir=tmp_path, transport=httpx.MockTransport(handler)
    )
    titles, page = [], 1
    while page:
        result = reader.list("600519.SH", limit=1, page=page)
        titles += [d["title"] for d in result["documents"]]
        page = result["next_page"]
    assert titles == [f"公告{i}" for i in range(5)]


def test_listing_never_requests_more_than_source_page_size(tmp_path):
    """cninfo caps pageSize at 30 and repeats page 1 forever when asked for more."""
    from urllib.parse import parse_qs

    from app.disclosures import SOURCE_PAGE_SIZE, DisclosureReader

    sizes = []

    def handler(req):
        if req.url.path.endswith("szse_stock.json"):
            return httpx.Response(200, json={"stockList": [dict(code="600519", orgId="valid")]})
        sizes.append(int(parse_qs(req.content.decode())["pageSize"][0]))
        return httpx.Response(200, json={"announcements": [], "hasMore": False})

    reader = DisclosureReader(
        lambda: 60, cache_dir=tmp_path, transport=httpx.MockTransport(handler)
    )
    reader.list("600519.SH", limit=100)
    assert sizes == [SOURCE_PAGE_SIZE]


def test_parser_reports_specific_reason_instead_of_generic_ocr_message(tmp_path):
    import io
    import subprocess
    import sys

    from pypdf import PdfWriter

    from app.disclosures import parser_error
    from app.document_parser import compact

    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    blank = io.BytesIO()
    writer.write(blank)
    child = subprocess.run(
        [sys.executable, "-m", "app.document_parser"],
        input=blank.getvalue(),
        capture_output=True,
        timeout=30,
    )
    assert child.returncode == 1
    assert parser_error(child.stdout) == "未提取到文字，可能为扫描件；OCR尚未接通，未生成文档事实"
    # Unknown or hostile child output never reaches the user verbatim.
    assert "secret" not in parser_error(b'{"error":"secret path"}')
    assert "解析失败" in parser_error(b"not json")
    assert compact("营业收入        100   \n利润") == "营业收入  100\n利润"


def test_document_download_gets_longer_budget_than_listing(tmp_path, monkeypatch):
    from app.disclosures import DisclosureReader

    budgets = []

    def handler(req):
        return httpx.Response(200, content=b"x")

    reader = DisclosureReader(
        lambda: 170, cache_dir=tmp_path, transport=httpx.MockTransport(handler)
    )
    original = httpx.AsyncClient.__init__

    def spy(self, *a, **k):
        budgets.append(k["timeout"])
        original(self, *a, **k)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy)
    reader.fetch("https://static.cninfo.com.cn/a.pdf", size=20 * 1024 * 1024)
    reader.fetch("https://www.cninfo.com.cn/list")
    assert budgets == [60, 12]
