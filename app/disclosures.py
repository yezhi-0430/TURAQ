"""Fixed-source, bounded public disclosure retrieval and page-addressable text cache."""

import asyncio
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

from app.document_parser import SAFE_ERRORS
from app.market import SHANGHAI, normalize_symbol

SOURCE = "巨潮资讯网公开披露"
CACHE = Path(__file__).resolve().parents[1] / ".local-backups" / "disclosures"
PATH_RE = re.compile(r"^finalpage/\d{4}-\d{2}-\d{2}/\d+\.pdf$", re.I)
ID_RE = re.compile(r"^[a-f0-9]{24}$")
# cninfo silently caps pageSize at 30 and then repeats the same page for every pageNum.
SOURCE_PAGE_SIZE = 30


class DisclosureUnavailable(ValueError):
    pass


def parser_error(output):
    """Map the child's whitelisted error to a user-facing reason without trusting raw output."""
    try:
        message = json.loads(output).get("error", "")
    except (ValueError, AttributeError):
        message = ""
    if message in SAFE_ERRORS:
        return message if "未生成文档事实" in message else message + "，未生成文档事实"
    return "PDF解析失败（文件损坏或格式不受支持），未生成文档事实"


def canonical(value):
    code = normalize_symbol(value)
    return code[2:] + "." + code[:2].upper()


class DisclosureReader:
    def __init__(self, remaining, *, cache_dir=CACHE, transport=None):
        self.remaining, self.cache_dir, self.transport = remaining, Path(cache_dir), transport
        self.requests = 0
        self.catalog = None
        self.listings = {}

    async def _fetch(self, url, *, form=None, size=2 * 1024 * 1024):
        # Large report PDFs routinely take 8-15 s from static.cninfo; listings stay short.
        budget = min(60 if size > 2 * 1024 * 1024 else 12, self.remaining())
        if self.requests >= 8:
            raise DisclosureUnavailable("每次分析最多8次文档请求，请缩小资料范围")
        self.requests += 1
        async with (
            asyncio.timeout(budget),
            httpx.AsyncClient(
                timeout=budget, trust_env=False, follow_redirects=False, transport=self.transport
            ) as client,
        ):
            async with client.stream(
                "POST" if form else "GET",
                url,
                data=form,
                headers={"Referer": "https://www.cninfo.com.cn/", "User-Agent": "Mozilla/5.0"},
            ) as response:
                response.raise_for_status()
                chunks, count = [], 0
                async for chunk in response.aiter_bytes():
                    count += len(chunk)
                    if count > size:
                        raise DisclosureUnavailable("披露资料超过下载大小上限")
                    chunks.append(chunk)
                return b"".join(chunks)

    def fetch(self, url, **kwargs):
        self.remaining()
        try:
            result = asyncio.run(self._fetch(url, **kwargs))
            self.remaining()
            return result
        except (httpx.HTTPError, TimeoutError) as exc:
            self.remaining()
            raise DisclosureUnavailable("公开披露源请求失败，请稍后重试；失败不代表无风险") from exc

    def _write(self, document_id, value):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp = self.cache_dir / (document_id + "." + uuid4().hex + ".tmp")
        try:
            temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, self.cache_dir / (document_id + ".json"))
        finally:
            temp.unlink(missing_ok=True)

    def _load(self, document_id):
        if not ID_RE.fullmatch(document_id):
            raise DisclosureUnavailable("文档编号无效，请先查询已披露资料")
        try:
            path = self.cache_dir / (document_id + ".json")
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("cache size")
            value = json.loads(path.read_text(encoding="utf-8"))
            if value["metadata"]["document_id"] != document_id:
                raise ValueError("cache identity")
            return value
        except (OSError, ValueError, KeyError) as exc:
            raise DisclosureUnavailable("未找到文档，请先按股票查询资料") from exc

    def list(self, symbol, *, reports=False, limit=5, date_from=None, date_to=None, page=1):
        symbol = canonical(symbol)
        now = datetime.now(SHANGHAI)
        date_to = date_to or now.date()
        date_from = date_from or (now.date() - timedelta(days=730 if reports else 90))
        if date_from > date_to or date_to > now.date() or (date_to - date_from).days > 1096:
            raise DisclosureUnavailable("披露查询范围须为今天以前且不超过三年")
        if not 1 <= page <= 10000 or not 1 <= limit <= 100:
            raise DisclosureUnavailable("披露分页参数无效")
        key = (symbol, reports, limit, date_from, date_to, page)
        if key in self.listings:
            return self.listings[key]
        try:
            if self.catalog is None:
                self.catalog = json.loads(
                    self.fetch("https://www.cninfo.com.cn/new/data/szse_stock.json")
                )["stockList"]
            stock = next((s for s in self.catalog if s.get("code") == symbol[:6]), None)
            if not stock or not re.fullmatch(r"[a-zA-Z0-9]+", stock.get("orgId", "")):
                raise DisclosureUnavailable("披露源证券目录未找到该股票，不能推定没有公告")
            form = dict(
                pageNum=str(page),
                pageSize=str(min(limit, SOURCE_PAGE_SIZE)),
                column={"SH": "sse", "SZ": "szse", "BJ": "bse"}[symbol[-2:]],
                tabName="fulltext",
                stock=f"{symbol[:6]},{stock['orgId']}",
                searchkey="",
                secid="",
                category="category_ndbg_szsh;category_bndbg_szsh;category_sjdbg_szsh;category_yjdbg_szsh"
                if reports
                else "",
                trade="",
                seDate=f"{date_from}~{date_to}",
                sortName="time",
                sortType="desc",
                isHLtitle="true",
            )
            raw = json.loads(
                self.fetch("https://www.cninfo.com.cn/new/hisAnnouncement/query", form=form)
            )
            rows = raw.get("announcements")
            if rows is None and raw.get("totalAnnouncement") == 0:
                rows = []
            if not isinstance(rows, list):
                raise ValueError("announcement shape")
            documents = []
            rejected = 0
            for row in rows:
                path = row.get("adjunctUrl", "")
                if row.get("secCode") != symbol[:6] or not PATH_RE.fullmatch(path):
                    rejected += 1
                    continue
                title = html.unescape(
                    re.sub(r"<[^>]*>", "", str(row.get("announcementTitle", "")))
                )[:200]
                period = re.search(
                    r"20\d{2}年(?:年度|半年度|第一季度|第三季度|一季度|三季度)报告", title
                )
                if reports and (not period or "摘要" in title or "英文" in title):
                    continue
                stamp = datetime.fromtimestamp(int(row["announcementTime"]) / 1000, SHANGHAI)
                if not date_from <= stamp.date() <= date_to:
                    continue
                document_id = hashlib.sha256((symbol + path).encode()).hexdigest()[:24]
                meta = dict(
                    document_id=document_id,
                    symbol=symbol,
                    title=title,
                    provider=SOURCE,
                    report_period=period.group() if period else None,
                    published_date=stamp.date().isoformat(),
                    url="https://static.cninfo.com.cn/" + path,
                    fetched_at=now.isoformat(),
                )
                if not (self.cache_dir / (document_id + ".json")).exists():
                    self._write(document_id, dict(metadata=meta, pages=None, warnings=[]))
                documents.append(meta)
            result = dict(
                documents=documents[:limit],
                truncated=bool(raw.get("hasMore")) or len(documents) > limit,
                data_status="available" if documents else "no_data",
                source=SOURCE,
                fetched_at=now.isoformat(),
                page=page,
                next_page=page + 1 if raw.get("hasMore") else None,
                returned_count=len(rows),
                total_count=raw.get("totalAnnouncement"),
                page_signature=hashlib.sha256(
                    json.dumps(
                        [
                            (r.get("secCode"), r.get("adjunctUrl"), r.get("announcementTime"))
                            for r in rows
                        ],
                        sort_keys=True,
                    ).encode()
                ).hexdigest(),
                rejected_count=rejected,
                warnings=["分页披露清单；仅最后一页不能证明此前页面均已读取。"]
                + (["部分来源记录格式不符，已排除。"] if rejected else []),
            )
            self.listings[key] = result
            return result
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            if isinstance(exc, DisclosureUnavailable):
                raise
            raise DisclosureUnavailable("披露源格式无效，未将其当作无资料") from exc

    def document(self, document_id):
        self.remaining()
        value = self._load(document_id)
        if value.get("pages") is not None and not any(
            "仅保留节选" in w for w in value.get("warnings", [])
        ):
            return value
        meta = value["metadata"]
        prefix = "https://static.cninfo.com.cn/"
        if not meta["url"].startswith(prefix) or not PATH_RE.fullmatch(meta["url"][len(prefix) :]):
            raise DisclosureUnavailable("文档来源地址不在允许范围")
        data = self.fetch(meta["url"], size=20 * 1024 * 1024)
        # A 600+ page annual report needs ~35 s of layout extraction.
        parse_budget = min(150, self.remaining())
        child = subprocess.Popen(
            [sys.executable, "-m", "app.document_parser"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(__file__).resolve().parents[1],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            output, _ = child.communicate(data, timeout=parse_budget)
        except (subprocess.TimeoutExpired, TimeoutError):
            child.kill()
            child.communicate()
            raise DisclosureUnavailable("PDF解析超时，未生成文档事实") from None
        if len(output) > 8 * 1024 * 1024:
            raise DisclosureUnavailable("PDF文字超过8MB解析输出上限，未生成文档事实")
        if child.returncode:
            raise DisclosureUnavailable(parser_error(output))
        parsed = json.loads(output)
        self.remaining()
        value.update(
            pages=parsed["pages"],
            warnings=parsed["warnings"],
            content_hash=hashlib.sha256(data).hexdigest(),
            parser_version=2,
        )
        self._write(document_id, value)
        return value

    def result(self, value, excerpts):
        return dict(
            document=value["metadata"],
            excerpts=excerpts,
            page_count=len(value["pages"]),
            data_status="available" if excerpts else "no_data",
            source=SOURCE,
            warnings=value["warnings"]
            + ["PDF页码为文件页序；文字与表格可能存在解析差异，原PDF为核对依据。"],
        )

    def read(self, document_id, start_page=1, page_count=2):
        value = self.document(document_id)
        if start_page > len(value["pages"]):
            raise DisclosureUnavailable("页码超出文档实际范围")
        return self.result(value, value["pages"][start_page - 1 : start_page - 1 + page_count])

    def search(self, document_id, query, limit=3):
        value = self.document(document_id)
        matches = []
        for page in value["pages"]:
            text = page["text"]
            hit = text.find(query)
            if hit >= 0:
                matches.append(dict(page=page["page"], text=text[max(0, hit - 180) : hit + 2200]))
                if len(matches) >= limit:
                    break
        return self.result(value, matches)
