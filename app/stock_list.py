"""
全量A股列表服务 - 内存存储方案
"""
import asyncio
import io
import json
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

import httpx

from app.market import SHANGHAI

logger = logging.getLogger(__name__)

# 新目录任一市场少于原有数量的这个比例，视为源异常（截断/限流），拒绝替换。
MIN_KEEP_RATIO = 0.9
_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_SOURCE_ERRORS = (
    httpx.HTTPError, ValueError, KeyError, IndexError, TypeError,
    zipfile.BadZipFile, ET.ParseError,
)


def _record(code, name, market: str) -> dict | None:
    code = str(code).strip()
    # NFKC 把"万  科Ａ"这类全角/补空格简称规整为"万科A"，按名称搜索才能命中。
    name = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(name)))
    if not re.fullmatch(r"\d{6}", code) or not name:
        return None
    return {
        "symbol": f"{code}.{market.upper()}", "code": market + code, "name": name,
        "market": market,
    }


async def _fetch_sse(client: httpx.AsyncClient) -> list[dict]:
    """上交所主板(1)与科创板(8)上市A股。"""
    stocks = []
    for stock_type in ("1", "8"):
        response = await client.get(
            "https://query.sse.com.cn/sseQuery/commonQuery.do",
            params={
                "STOCK_TYPE": stock_type, "REG_PROVINCE": "", "CSRC_CODE": "", "STOCK_CODE": "",
                "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L", "COMPANY_STATUS": "2,4,5,7,8",
                "type": "inParams", "isPagination": "true", "pageHelp.cacheSize": "1",
                "pageHelp.beginPage": "1", "pageHelp.pageSize": "5000", "pageHelp.pageNo": "1",
            },
            headers={"Referer": "https://www.sse.com.cn/"},
        )
        response.raise_for_status()
        data = response.json()
        rows = data["result"]
        if len(rows) != int(data["pageHelp"]["total"]):
            raise ValueError("上交所名单分页不完整")
        stocks += [
            r for row in rows if (r := _record(row["A_STOCK_CODE"], row["SEC_NAME_CN"], "sh"))
        ]
    return stocks


def _xlsx_rows(content: bytes) -> list[list[str]]:
    """只读取首个工作表的文本，不引入 openpyxl。"""
    with zipfile.ZipFile(io.BytesIO(content)) as book:
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            shared = [
                "".join(t.text or "" for t in item.iter(_XLSX_NS + "t"))
                for item in ET.fromstring(book.read("xl/sharedStrings.xml"))
            ]
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.iter(_XLSX_NS + "row"):
        values = []
        for cell in row.findall(_XLSX_NS + "c"):
            value = cell.find(_XLSX_NS + "v")
            if cell.get("t") == "s":
                text = shared[int(value.text)]
            elif value is not None:
                text = value.text or ""
            else:
                text = "".join(t.text or "" for t in cell.iter(_XLSX_NS + "t"))
            values.append(text)
        rows.append(values)
    return rows


async def _fetch_szse(client: httpx.AsyncClient) -> list[dict]:
    """深交所A股列表官方导出（主板+创业板）。"""
    response = await client.get(
        "https://www.szse.cn/api/report/ShowReport",
        params={"SHOWTYPE": "xlsx", "CATALOGID": "1110", "TABKEY": "tab1"},
        headers={"Referer": "https://www.szse.cn/"},
    )
    response.raise_for_status()
    if len(response.content) > 20 * 1024 * 1024:
        raise ValueError("深交所名单超过大小上限")
    rows = _xlsx_rows(response.content)
    code_at, name_at = rows[0].index("A股代码"), rows[0].index("A股简称")
    return [
        r for row in rows[1:]
        if len(row) > max(code_at, name_at) and (r := _record(row[code_at], row[name_at], "sz"))
    ]


async def _fetch_bse(client: httpx.AsyncClient) -> list[dict]:
    """北交所上市股票（JSONP 分页，每页固定 20 条）。"""
    stocks, page, total_pages, total = [], 0, 1, None
    while page < total_pages:
        response = await client.post(
            "https://www.bse.cn/nqxxController/nqxxCnzq.do",
            data={
                "page": str(page), "typejb": "T", "xxfcbj[]": "2", "xxzqdm": "",
                "sortfield": "xxzqdm", "sorttype": "asc",
            },
            headers={"Referer": "https://www.bse.cn/"},
        )
        response.raise_for_status()
        text = response.text
        data = json.loads(text[text.index("(") + 1 : text.rindex(")")])[0]
        total_pages, total = int(data["totalPages"]), int(data["totalElements"])
        if total_pages > 200:
            raise ValueError("北交所名单页数异常")
        stocks += [
            r for row in data["content"] if (r := _record(row["xxzqdm"], row["xxzqjc"], "bj"))
        ]
        page += 1
    if len(stocks) != total:
        raise ValueError("北交所名单分页不完整")
    return stocks


def _shrink_problem(old: list[dict], new: list[dict]) -> str | None:
    """新目录明显变小（截断、限流、接口改版）时给出拒绝原因。"""
    for market in ("sh", "sz", "bj"):
        before = sum(s.get("market") == market for s in old)
        after = sum(s["market"] == market for s in new)
        if after == 0 or after < before * MIN_KEEP_RATIO:
            return f"{market}市场新名单仅{after}只（原{before}只），疑似源异常，保留现有目录"
    return None


class StockListService:
    """全量A股列表服务 - 内存存储"""

    def __init__(self):
        self.stocks: list[dict] = []  # 全量列表
        self.symbol_map: dict[str, dict] = {}  # symbol快速索引 (000001.SZ -> stock)
        self.code_map: dict[str, dict] = {}  # code快速索引 (sz000001 -> stock)
        self.last_updated: datetime | None = None
        self._lock = asyncio.Lock()  # 保护并发更新
        self.load_from_file()

    def load_from_file(self, file_path: str = "data/stocks_base.json"):
        """从静态JSON文件加载"""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"股票列表文件不存在: {file_path}")
                return

            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            self.stocks = data.get("stocks", [])
            self._build_indexes()

            # 解析更新时间
            updated_str = data.get("updated_at")
            if updated_str:
                self.last_updated = datetime.fromisoformat(updated_str)

            logger.info(f"成功加载 {len(self.stocks)} 只股票")
            logger.info(f"数据版本: {data.get('version')}, 来源: {data.get('source')}")

        except Exception as e:
            logger.error(f"加载股票列表失败: {e}", exc_info=True)

    def _build_indexes(self):
        """构建快速查找索引"""
        self.symbol_map.clear()
        self.code_map.clear()

        for stock in self.stocks:
            symbol = stock.get("symbol")
            code = stock.get("code")

            if symbol:
                self.symbol_map[symbol] = stock
            if code:
                self.code_map[code] = stock

        logger.debug(f"构建索引完成: {len(self.symbol_map)} symbols, {len(self.code_map)} codes")

    def search(
        self, query: str, market: str | None = None, limit: int = 50
    ) -> list[dict]:
        """
        搜索股票

        Args:
            query: 搜索关键词（股票代码或名称）
            market: 市场过滤 (sh/sz/bj/None)
            limit: 返回结果数量限制

        Returns:
            匹配的股票列表，按相关性排序
        """
        if not query:
            return []

        # 名称同样做 NFKC+小写+去空格，"万科a"/"万科Ａ" 都能命中 "万科A"。
        query = re.sub(r"\s+", "", unicodedata.normalize("NFKC", query)).lower()
        if not query:
            return []
        results = []

        for stock in self.stocks:
            # 市场过滤
            if market and stock.get("market") != market:
                continue

            symbol = stock.get("symbol", "").lower()
            code = stock.get("code", "").lower()
            name = re.sub(r"\s+", "", unicodedata.normalize("NFKC", stock.get("name", ""))).lower()

            # 计算匹配度
            score = 0

            # 精确匹配（最高优先级）
            if query == symbol or query == code:
                score = 100
            # 代码前缀匹配
            elif symbol.startswith(query) or code.startswith(query):
                score = 90
            # 代码包含匹配
            elif query in symbol or query in code:
                score = 80
            # 名称开头匹配
            elif name.startswith(query):
                score = 70
            # 名称包含匹配
            elif query in name:
                score = 60

            if score > 0:
                results.append({"stock": stock, "score": score})

        # 按相关性排序
        results.sort(key=lambda x: x["score"], reverse=True)

        # 提取stock对象并限制数量
        return [r["stock"] for r in results[:limit]]

    def get_by_symbol(self, symbol: str) -> dict | None:
        """通过symbol精确查找"""
        return self.symbol_map.get(symbol)

    def get_by_code(self, code: str) -> dict | None:
        """通过code精确查找"""
        return self.code_map.get(code)

    def get_stats(self) -> dict:
        """获取统计信息"""
        # 统计各市场数量
        by_market = {}
        for stock in self.stocks:
            market = stock.get("market", "unknown")
            by_market[market] = by_market.get(market, 0) + 1

        return {
            "total": len(self.stocks),
            "by_market": by_market,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    async def update_from_api(self, transport=None) -> tuple[bool, str]:
        """从沪深北三家交易所官方名单刷新；任一所失败或数量异常都保留现有数据。

        返回 (是否已替换, 说明)，供定时任务记录真实结果。
        """
        async with self._lock:  # 加锁保护并发更新
            try:
                async with httpx.AsyncClient(
                    timeout=30, trust_env=False, follow_redirects=True, transport=transport,
                    headers={"User-Agent": "Mozilla/5.0"},
                ) as client:
                    results = await asyncio.gather(
                        _fetch_sse(client), _fetch_szse(client), _fetch_bse(client)
                    )
            except _SOURCE_ERRORS as exc:
                message = f"交易所名单获取失败，保留现有目录: {type(exc).__name__}"
                logger.warning(message)
                return False, message
            new_stocks = list({s["symbol"]: s for group in results for s in group}.values())
            problem = _shrink_problem(self.stocks, new_stocks)
            if problem:
                logger.warning(problem)
                return False, problem
            old_count = len(self.stocks)
            self.stocks = sorted(new_stocks, key=lambda s: s["symbol"])
            self._build_indexes()
            self.last_updated = datetime.now(SHANGHAI)
            self._save_to_file()
            message = f"股票列表更新成功: {old_count} -> {len(self.stocks)}"
            logger.info(message)
            return True, message

    def _save_to_file(self, file_path: str = "data/stocks_base.json"):
        """保存到文件（原子操作）"""
        try:
            output = {
                "version": datetime.now().strftime("%Y-%m-%d"),
                "source": "上交所/深交所/北交所官方证券名单",
                "total": len(self.stocks),
                "updated_at": self.last_updated.isoformat(),
                "stocks": self.stocks,
            }

            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            # 原子性写入：先写临时文件，再重命名
            temp_path = path.with_suffix('.json.tmp')
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            # 原子性重命名
            temp_path.replace(path)

            logger.info(f"股票列表已保存到: {file_path}")

        except Exception as e:
            logger.error(f"保存股票列表失败: {e}", exc_info=True)
            # 清理临时文件
            try:
                temp_path = Path(file_path).with_suffix('.json.tmp')
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                logger.warning("临时文件清理失败", exc_info=True)


# 全局单例
stock_list_service = StockListService()


if __name__ == "__main__":
    # 手动刷新：python -m app.stock_list
    logging.basicConfig(level=logging.INFO)
    updated, detail = asyncio.run(stock_list_service.update_from_api())
    print(detail)
    raise SystemExit(0 if updated else 1)
