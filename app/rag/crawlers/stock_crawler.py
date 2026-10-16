"""
实际的股票数据爬虫实现

支持：
1. 巨潮资讯网 - 公司公告
2. 东方财富网 - 券商研报
3. 新浪财经 - 财务数据
"""

import asyncio
import httpx
import re
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class StockDataCrawler:
    """股票数据爬虫"""

    def __init__(self):
        """初始化爬虫"""
        # 随机 User-Agent 池，模拟真实浏览器
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]

        # HTTP 客户端配置
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

    def _get_headers(self) -> Dict[str, str]:
        """
        获取随机请求头，避免被识别为爬虫

        Returns:
            请求头字典
        """
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    async def _safe_request(self, url: str, retries: int = 3) -> Optional[str]:
        """
        安全的 HTTP 请求（带重试和延迟）

        Args:
            url: 请求地址
            retries: 重试次数

        Returns:
            响应内容
        """
        for attempt in range(retries):
            try:
                # 随机延迟 1-3 秒，避免请求过快
                await asyncio.sleep(random.uniform(1.0, 3.0))

                response = await self.client.get(url, headers=self._get_headers())
                response.raise_for_status()

                return response.text

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Too Many Requests
                    wait_time = (attempt + 1) * 5
                    logger.warning(f"请求过快，等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"HTTP 错误 {e.response.status_code}: {url}")
                    if attempt == retries - 1:
                        return None

            except Exception as e:
                logger.error(f"请求失败 (尝试 {attempt + 1}/{retries}): {str(e)}")
                if attempt == retries - 1:
                    return None

        return None

    async def crawl_cninfo_announcements(
        self,
        stock_code: str,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        从巨潮资讯网爬取公司公告

        Args:
            stock_code: 股票代码（如 600519）
            days: 爬取最近几天的公告

        Returns:
            公告列表
        """
        logger.info(f"开始爬取 {stock_code} 的巨潮公告")

        announcements = []

        try:
            # 转换股票代码格式
            if stock_code.startswith('6'):
                full_code = f"sh{stock_code}"
            else:
                full_code = f"sz{stock_code}"

            # 构建请求 URL
            # 注意：这是示例 URL，实际使用时需要根据巨潮的真实接口调整
            base_url = "http://www.cninfo.com.cn/new/disclosure"

            # 使用搜索接口获取公告列表
            search_url = f"{base_url}/search?keyword={stock_code}"

            html = await self._safe_request(search_url)
            if not html:
                return announcements

            soup = BeautifulSoup(html, 'html.parser')

            # 解析公告列表
            # 注意：以下选择器需要根据实际网页结构调整
            items = soup.select('.disclosure-item')[:10]  # 限制最多 10 条

            for item in items:
                try:
                    title_el = item.select_one('.title')
                    date_el = item.select_one('.date')
                    link_el = item.select_one('a')

                    if not (title_el and date_el):
                        continue

                    title = title_el.text.strip()
                    date_str = date_el.text.strip()

                    # 检查日期是否在范围内
                    try:
                        pub_date = datetime.strptime(date_str, '%Y-%m-%d')
                        if (datetime.now() - pub_date).days > days:
                            continue
                    except:
                        pass

                    announcements.append({
                        'title': title,
                        'date': date_str,
                        'content': f"公告标题：{title}\n发布日期：{date_str}\n来源：巨潮资讯网",
                        'source': 'cninfo',
                        'url': link_el.get('href', '') if link_el else ''
                    })

                except Exception as e:
                    logger.error(f"解析公告项失败: {str(e)}")
                    continue

            logger.info(f"成功爬取 {len(announcements)} 条公告")

        except Exception as e:
            logger.error(f"爬取巨潮公告失败: {str(e)}")

        return announcements

    async def crawl_eastmoney_reports(
        self,
        stock_code: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        从东方财富爬取券商研报

        Args:
            stock_code: 股票代码
            limit: 爬取数量

        Returns:
            研报列表
        """
        logger.info(f"开始爬取 {stock_code} 的券商研报")

        reports = []

        try:
            # 东方财富研报 API（示例）
            # 注意：实际 API 地址需要抓包分析
            api_url = f"http://data.eastmoney.com/report/stock.jshtml?code={stock_code}"

            html = await self._safe_request(api_url)
            if not html:
                return reports

            soup = BeautifulSoup(html, 'html.parser')

            # 解析研报列表
            items = soup.select('.report-item')[:limit]

            for item in items:
                try:
                    title = item.select_one('.title').text.strip()
                    analyst = item.select_one('.analyst').text.strip() if item.select_one('.analyst') else '未知'
                    rating = item.select_one('.rating').text.strip() if item.select_one('.rating') else '未知'
                    date_str = item.select_one('.date').text.strip()

                    reports.append({
                        'title': title,
                        'content': f"研报标题：{title}\n分析师：{analyst}\n评级：{rating}\n发布日期：{date_str}\n来源：东方财富",
                        'analyst': analyst,
                        'rating': rating,
                        'date': date_str,
                        'source': 'eastmoney'
                    })

                except Exception as e:
                    logger.error(f"解析研报项失败: {str(e)}")
                    continue

            logger.info(f"成功爬取 {len(reports)} 条研报")

        except Exception as e:
            logger.error(f"爬取东方财富研报失败: {str(e)}")

        return reports

    async def crawl_sina_financial_data(
        self,
        stock_code: str
    ) -> List[Dict[str, Any]]:
        """
        从新浪财经爬取财务数据

        Args:
            stock_code: 股票代码

        Returns:
            财务数据列表
        """
        logger.info(f"开始爬取 {stock_code} 的财务数据")

        financials = []

        try:
            # 新浪财经财报接口（示例）
            api_url = f"http://money.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/{stock_code}.phtml"

            html = await self._safe_request(api_url)
            if not html:
                return financials

            soup = BeautifulSoup(html, 'html.parser')

            # 解析财务数据表格
            tables = soup.select('table.FIN_data')

            for table in tables[:3]:  # 只取前3个表格
                try:
                    caption = table.select_one('caption')
                    if not caption:
                        continue

                    title = caption.text.strip()

                    # 提取表格数据
                    rows = table.select('tr')
                    data_text = f"财报类型：{title}\n\n"

                    for row in rows[:10]:  # 只取前10行
                        cells = row.select('td')
                        if cells:
                            row_text = ' | '.join([cell.text.strip() for cell in cells])
                            data_text += row_text + '\n'

                    financials.append({
                        'title': f"{stock_code} - {title}",
                        'content': data_text,
                        'period': datetime.now().strftime('%Y-%m'),
                        'source': 'sina'
                    })

                except Exception as e:
                    logger.error(f"解析财务表格失败: {str(e)}")
                    continue

            logger.info(f"成功爬取 {len(financials)} 份财务数据")

        except Exception as e:
            logger.error(f"爬取新浪财务数据失败: {str(e)}")

        return financials

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()
