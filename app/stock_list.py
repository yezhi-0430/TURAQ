"""
全量A股列表服务 - 内存存储方案
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


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

            with open(path, "r", encoding="utf-8") as f:
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

        query = query.strip().lower()
        results = []

        for stock in self.stocks:
            # 市场过滤
            if market and stock.get("market") != market:
                continue

            symbol = stock.get("symbol", "").lower()
            code = stock.get("code", "").lower()
            name = stock.get("name", "")

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

    async def update_from_api(self):
        """
        从API更新列表（优先akshare，失败时尝试东方财富API）

        这个方法会被定时任务调用，失败时保留现有数据
        """
        async with self._lock:  # 加锁保护并发更新
            try:
                logger.info("开始从API更新股票列表...")

                # 优先尝试akshare
                new_stocks = await self._fetch_from_akshare()

                # 如果akshare失败，尝试东方财富API
                if not new_stocks:
                    logger.warning("akshare获取失败，尝试东方财富API...")
                    new_stocks = await self._fetch_from_eastmoney()

                if not new_stocks:
                    logger.warning("所有数据源均失败，保留现有数据")
                    return

                # 原子性更新
                old_count = len(self.stocks)
                self.stocks = new_stocks
                self._build_indexes()
                self.last_updated = datetime.now()

                logger.info(f"股票列表更新成功: {old_count} -> {len(self.stocks)}")

                # 保存到文件
                self._save_to_file()

            except Exception as e:
                logger.error(f"从API更新股票列表失败: {e}", exc_info=True)
                # 保留现有数据，不抛出异常

    async def _fetch_from_akshare(self) -> list[dict]:
        """从akshare获取股票列表"""
        try:
            import akshare as ak
        except ImportError:
            logger.warning("akshare未安装，跳过此数据源")
            return []

        all_stocks = []

        try:
            # 获取沪市A股 - 在线程池中执行避免阻塞
            logger.info("正在从akshare获取沪市A股...")
            sh_stocks = await self._run_in_executor(
                ak.stock_info_sh_name_code, symbol="主板A股"
            )
            for _, row in sh_stocks.iterrows():
                code = str(row['证券代码']).zfill(6)
                name = row['证券简称']
                all_stocks.append({
                    'symbol': f"{code}.SH",
                    'code': f"sh{code}",
                    'name': name,
                    'market': 'sh'
                })
            logger.info(f"  获取到 {len(sh_stocks)} 只沪市股票")
        except Exception as e:
            logger.warning(f"获取沪市股票失败: {e}")

        try:
            # 获取深市A股 - 在线程池中执行
            logger.info("正在从akshare获取深市A股...")
            sz_stocks = await self._run_in_executor(
                ak.stock_info_sz_name_code, symbol="A股列表"
            )
            for _, row in sz_stocks.iterrows():
                code = str(row.get('A股代码') or row.get('证券代码', '')).strip()
                name = str(row.get('A股简称') or row.get('证券简称', '')).strip()
                # 跳过空值
                if not code or not name or code in ['nan', 'None', '']:
                    continue
                if code.isdigit() and len(code) <= 6:
                    code = code.zfill(6)
                    all_stocks.append({
                        'symbol': f"{code}.SZ",
                        'code': f"sz{code}",
                        'name': name,
                        'market': 'sz'
                    })
            logger.info(f"  获取到深市股票数量: {len([s for s in all_stocks if s['market'] == 'sz'])}")
        except Exception as e:
            logger.warning(f"获取深市股票失败: {e}")

        try:
            # 获取北交所股票 - 在线程池中执行
            logger.info("正在从akshare获取北交所股票...")
            bj_stocks = await self._run_in_executor(ak.stock_info_bj_name_code)
            for _, row in bj_stocks.iterrows():
                code = str(row.get('code') or row.get('证券代码', '')).strip()
                name = str(row.get('name') or row.get('证券简称', '')).strip()
                if not code or not name or code in ['nan', 'None', '']:
                    continue
                if code.isdigit() and len(code) <= 6:
                    code = code.zfill(6)
                    all_stocks.append({
                        'symbol': f"{code}.BJ",
                        'code': f"bj{code}",
                        'name': name,
                        'market': 'bj'
                    })
            logger.info(f"  获取到北交所股票数量: {len([s for s in all_stocks if s['market'] == 'bj'])}")
        except Exception as e:
            logger.warning(f"获取北交所股票失败: {e}")

        logger.info(f"akshare获取完成，共 {len(all_stocks)} 只股票")
        return all_stocks

    async def _run_in_executor(self, func, *args, **kwargs):
        """在线程池中运行同步函数（akshare是同步的）避免阻塞事件循环"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def _fetch_from_eastmoney(self) -> list[dict]:
        """从东方财富API获取股票列表"""
        all_stocks = []
        page_size = 1000

        # 分别获取不同市场的股票
        markets = [
            ("m:0+t:6,m:0+t:80", "深市"),
            ("m:1+t:2,m:1+t:23", "沪市"),
        ]

        async with httpx.AsyncClient(timeout=30) as client:
            for market_filter, market_name in markets:
                logger.info(f"正在获取{market_name}股票...")
                page = 1

                while page <= 10:  # 最多10页，防止无限循环
                    url = "http://80.push2.eastmoney.com/api/qt/clist/get"
                    params = {
                        "pn": page,
                        "pz": page_size,
                        "po": 1,
                        "np": 1,
                        "fltt": 2,
                        "invt": 2,
                        "fid": "f3",
                        "fs": market_filter,
                        "fields": "f12,f13,f14",
                    }

                    try:
                        response = await client.get(url, params=params)
                        response.raise_for_status()

                        data = response.json()
                        if data.get("rc") != 0 or not data.get("data"):
                            break

                        stocks_data = data["data"].get("diff", [])
                        if not stocks_data:
                            break

                        # 标准化格式
                        for item in stocks_data:
                            stock = self._normalize_stock(item)
                            if stock:
                                all_stocks.append(stock)

                        logger.info(f"  第{page}页: {len(stocks_data)} 只")

                        if len(stocks_data) < page_size:
                            break

                        page += 1

                    except Exception as e:
                        logger.warning(f"获取{market_name}第{page}页失败: {e}")
                        break

        logger.info(f"API获取完成，共 {len(all_stocks)} 只股票")
        return all_stocks

    def _normalize_stock(self, item: dict) -> dict | None:
        """标准化股票数据格式"""
        try:
            code_num = item["f12"]  # 如: 000001
            market_code = item["f13"]  # 0=深圳, 1=上海, 2=北交所
            name = item["f14"]

            # 转换市场代码
            if market_code == 0:
                market = "sz"
            elif market_code == 1:
                market = "sh"
            elif market_code == 2:
                market = "bj"
            else:
                return None

            # 生成标准格式
            code = f"{market}{code_num}"  # sz000001
            symbol = f"{code_num}.{market.upper()}"  # 000001.SZ

            return {
                "symbol": symbol,
                "code": code,
                "name": name,
                "market": market,
            }
        except (KeyError, ValueError):
            return None

    def _save_to_file(self, file_path: str = "data/stocks_base.json"):
        """保存到文件（原子操作）"""
        try:
            output = {
                "version": datetime.now().strftime("%Y-%m-%d"),
                "source": "东方财富",
                "total": len(self.stocks),
                "updated_at": datetime.now().isoformat(),
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
            except:
                pass


# 全局单例
stock_list_service = StockListService()
