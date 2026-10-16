"""
板块和热点爬虫

爬取行业板块动态、市场热点、财经新闻
"""

import asyncio
import httpx
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class SectorAndHotspotCrawler:
    """板块和热点爬虫"""

    def __init__(self):
        """初始化爬虫"""
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]

        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

    def _get_headers(self) -> Dict[str, str]:
        """获取随机请求头"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }

    async def _safe_request(self, url: str, retries: int = 3) -> Optional[str]:
        """安全的 HTTP 请求"""
        for attempt in range(retries):
            try:
                await asyncio.sleep(random.uniform(1.0, 3.0))
                response = await self.client.get(url, headers=self._get_headers())
                response.raise_for_status()
                return response.text
            except Exception as e:
                logger.error(f"请求失败 (尝试 {attempt + 1}/{retries}): {str(e)}")
                if attempt == retries - 1:
                    return None
        return None

    async def crawl_sector_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        爬取行业板块新闻

        Args:
            limit: 爬取数量

        Returns:
            板块新闻列表
        """
        logger.info("开始爬取行业板块新闻")

        news_list = []

        try:
            # 东方财富 - 行业板块新闻
            url = "http://finance.eastmoney.com/a/chy.html"

            html = await self._safe_request(url)
            if not html:
                return news_list

            soup = BeautifulSoup(html, 'html.parser')

            # 解析新闻列表
            items = soup.select('.news-item')[:limit]

            for item in items:
                try:
                    title_el = item.select_one('.news-title')
                    time_el = item.select_one('.news-time')
                    link_el = item.select_one('a')

                    if not title_el:
                        continue

                    title = title_el.text.strip()
                    time_str = time_el.text.strip() if time_el else datetime.now().strftime('%Y-%m-%d')

                    # 提取板块关键词
                    sector = self._extract_sector(title)

                    news_list.append({
                        'title': title,
                        'content': f"标题：{title}\n时间：{time_str}\n板块：{sector}\n来源：东方财富",
                        'time': time_str,
                        'sector': sector,
                        'source': 'eastmoney',
                        'url': link_el.get('href', '') if link_el else ''
                    })

                except Exception as e:
                    logger.error(f"解析板块新闻失败: {str(e)}")
                    continue

            logger.info(f"成功爬取 {len(news_list)} 条板块新闻")

        except Exception as e:
            logger.error(f"爬取板块新闻失败: {str(e)}")

        return news_list

    async def crawl_daily_hotspots(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        爬取每日市场热点

        Args:
            limit: 爬取数量

        Returns:
            热点列表
        """
        logger.info("开始爬取每日市场热点")

        hotspots = []

        try:
            # 同花顺 - 热点资讯
            url = "http://news.10jqka.com.cn/today_list/"

            html = await self._safe_request(url)
            if not html:
                return hotspots

            soup = BeautifulSoup(html, 'html.parser')

            # 解析热点列表
            items = soup.select('.list-item')[:limit]

            for item in items:
                try:
                    title_el = item.select_one('.title')
                    desc_el = item.select_one('.desc')
                    time_el = item.select_one('.time')

                    if not title_el:
                        continue

                    title = title_el.text.strip()
                    desc = desc_el.text.strip() if desc_el else ''
                    time_str = time_el.text.strip() if time_el else datetime.now().strftime('%Y-%m-%d %H:%M')

                    content = f"热点：{title}\n时间：{time_str}"
                    if desc:
                        content += f"\n简介：{desc}"
                    content += "\n来源：同花顺"

                    hotspots.append({
                        'title': title,
                        'content': content,
                        'description': desc,
                        'time': time_str,
                        'source': 'tonghuashun'
                    })

                except Exception as e:
                    logger.error(f"解析热点失败: {str(e)}")
                    continue

            logger.info(f"成功爬取 {len(hotspots)} 条市场热点")

        except Exception as e:
            logger.error(f"爬取市场热点失败: {str(e)}")

        return hotspots

    async def crawl_financial_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        爬取财经要闻

        Args:
            limit: 爬取数量

        Returns:
            财经新闻列表
        """
        logger.info("开始爬取财经要闻")

        news_list = []

        try:
            # 新浪财经 - 财经要闻
            url = "https://finance.sina.com.cn/"

            html = await self._safe_request(url)
            if not html:
                return news_list

            soup = BeautifulSoup(html, 'html.parser')

            # 解析新闻列表
            items = soup.select('.feed-card-item')[:limit]

            for item in items:
                try:
                    title_el = item.select_one('.feed-card-title')
                    time_el = item.select_one('.feed-card-time')

                    if not title_el:
                        continue

                    title = title_el.text.strip()
                    time_str = time_el.text.strip() if time_el else datetime.now().strftime('%Y-%m-%d')

                    news_list.append({
                        'title': title,
                        'content': f"标题：{title}\n时间：{time_str}\n来源：新浪财经",
                        'time': time_str,
                        'source': 'sina'
                    })

                except Exception as e:
                    logger.error(f"解析财经新闻失败: {str(e)}")
                    continue

            logger.info(f"成功爬取 {len(news_list)} 条财经要闻")

        except Exception as e:
            logger.error(f"爬取财经要闻失败: {str(e)}")

        return news_list

    async def crawl_concept_sectors(self) -> List[Dict[str, Any]]:
        """
        爬取热门概念板块

        Returns:
            概念板块列表
        """
        logger.info("开始爬取热门概念板块")

        sectors = []

        try:
            # 东方财富 - 概念板块
            url = "http://quote.eastmoney.com/center/gridlist.html#bk_concept"

            html = await self._safe_request(url)
            if not html:
                return sectors

            soup = BeautifulSoup(html, 'html.parser')

            # 解析概念板块
            items = soup.select('.concept-item')[:20]

            for item in items:
                try:
                    name_el = item.select_one('.concept-name')
                    change_el = item.select_one('.concept-change')
                    desc_el = item.select_one('.concept-desc')

                    if not name_el:
                        continue

                    name = name_el.text.strip()
                    change = change_el.text.strip() if change_el else '0%'
                    desc = desc_el.text.strip() if desc_el else ''

                    content = f"概念板块：{name}\n涨跌幅：{change}"
                    if desc:
                        content += f"\n描述：{desc}"
                    content += f"\n时间：{datetime.now().strftime('%Y-%m-%d')}\n来源：东方财富"

                    sectors.append({
                        'title': f"{name}板块",
                        'content': content,
                        'sector_name': name,
                        'change': change,
                        'description': desc,
                        'source': 'eastmoney'
                    })

                except Exception as e:
                    logger.error(f"解析概念板块失败: {str(e)}")
                    continue

            logger.info(f"成功爬取 {len(sectors)} 个概念板块")

        except Exception as e:
            logger.error(f"爬取概念板块失败: {str(e)}")

        return sectors

    def _extract_sector(self, text: str) -> str:
        """
        从文本中提取板块关键词

        Args:
            text: 文本内容

        Returns:
            板块名称
        """
        # 常见板块关键词
        sectors = [
            '新能源', '半导体', '芯片', '医药', '白酒', '银行',
            '房地产', '钢铁', '煤炭', '有色', '军工', '通信',
            '电子', '汽车', '家电', '食品', '零售', '旅游',
            '互联网', '人工智能', 'AI', '大数据', '云计算'
        ]

        for sector in sectors:
            if sector in text:
                return sector

        return '其他'

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()
