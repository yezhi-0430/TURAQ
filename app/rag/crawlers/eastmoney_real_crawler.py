"""
东方财富爬虫实现（实际可用版本）

数据来源：
1. 公司公告 - 东方财富
2. 研报 - 东方财富数据中心
3. 财务数据 - 东方财富F10
4. 新闻资讯 - 东方财富资讯
"""

import asyncio
import httpx
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class EastmoneyRealCrawler:
    """东方财富实际可用爬虫"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

        # 东方财富不同功能的headers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'http://quote.eastmoney.com/',
        }

    def _convert_stock_code(self, code: str) -> tuple:
        """
        转换股票代码格式

        Args:
            code: 6位股票代码 (如 600519)

        Returns:
            (市场代码, 完整代码) 如 (1, 600519) 或 (0, 000858)
        """
        if code.startswith('6'):
            return '1', code  # 上海
        elif code.startswith('0') or code.startswith('3'):
            return '0', code  # 深圳
        else:
            return '1', code  # 默认上海

    async def crawl_stock_announcements(
        self,
        stock_code: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        爬取公司公告（东方财富数据接口）

        Args:
            stock_code: 股票代码 (如 600519)
            limit: 爬取数量

        Returns:
            公告列表
        """
        logger.info(f"开始爬取 {stock_code} 的公告")

        announcements = []

        try:
            market_code, code = self._convert_stock_code(stock_code)

            # 东方财富公告接口
            url = f"http://datacenter-web.eastmoney.com/api/data/v1/get"

            params = {
                'reportName': 'RPT_F10_EH_AUDIT',
                'columns': 'ALL',
                'filter': f'(SECURITY_CODE="{code}")',
                'pageNumber': '1',
                'pageSize': str(limit),
                'sortTypes': '-1',
                'sortColumns': 'NOTICE_DATE',
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                data = response.json()

                if data.get('result') and data['result'].get('data'):
                    items = data['result']['data']

                    for item in items:
                        try:
                            title = item.get('TITLE', '')
                            notice_date = item.get('NOTICE_DATE', '')
                            type_name = item.get('CATEGORY', '')

                            # 格式化日期
                            if notice_date:
                                try:
                                    date_obj = datetime.strptime(notice_date[:10], '%Y-%m-%d')
                                    date_str = date_obj.strftime('%Y-%m-%d')
                                except:
                                    date_str = notice_date[:10]
                            else:
                                date_str = datetime.now().strftime('%Y-%m-%d')

                            announcements.append({
                                'title': title,
                                'date': date_str,
                                'type': type_name,
                                'content': f"公告标题：{title}\n类型：{type_name}\n发布日期：{date_str}\n股票代码：{stock_code}\n来源：东方财富",
                                'source': 'eastmoney',
                                'stock_code': stock_code
                            })

                        except Exception as e:
                            logger.error(f"解析公告项失败: {str(e)}")
                            continue

                    logger.info(f"成功爬取 {len(announcements)} 条公告")
                else:
                    logger.warning("API返回数据为空")
            else:
                logger.error(f"请求失败，状态码: {response.status_code}")

        except Exception as e:
            logger.error(f"爬取公告失败: {str(e)}")

        return announcements

    async def crawl_stock_news(
        self,
        stock_code: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        爬取股票新闻（东方财富资讯）

        Args:
            stock_code: 股票代码
            limit: 爬取数量

        Returns:
            新闻列表
        """
        logger.info(f"开始爬取 {stock_code} 的新闻")

        news_list = []

        try:
            market_code, code = self._convert_stock_code(stock_code)

            # 东方财富个股新闻接口
            url = f"http://search-api-web.eastmoney.com/search/jsonp"

            params = {
                'cb': 'jQuery',
                'param': json.dumps({
                    'uid': '',
                    'keyword': stock_code,
                    'type': ['cmsArticleWebOld'],
                    'client': 'web',
                    'clientType': 'web',
                    'clientVersion': 'curr',
                    'param': {
                        'cmsArticleWebOld': {
                            'searchScope': 'default',
                            'sort': 'default',
                            'pageIndex': 1,
                            'pageSize': limit,
                        }
                    }
                }),
                '_': str(int(datetime.now().timestamp() * 1000))
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                # 提取JSONP中的JSON数据
                text = response.text
                json_str = re.search(r'jQuery\d+_\d+\((.*)\)', text)

                if json_str:
                    data = json.loads(json_str.group(1))

                    if data.get('result') and data['result'].get('cmsArticleWebOld'):
                        items = data['result']['cmsArticleWebOld']

                        for item in items:
                            try:
                                title = item.get('title', '')
                                date_str = item.get('date', '')
                                summary = item.get('summary', '')

                                # 格式化日期
                                if date_str:
                                    try:
                                        date_obj = datetime.strptime(date_str[:10], '%Y-%m-%d')
                                        date_str = date_obj.strftime('%Y-%m-%d')
                                    except:
                                        pass

                                content = f"新闻标题：{title}\n"
                                if summary:
                                    content += f"摘要：{summary}\n"
                                content += f"发布日期：{date_str}\n股票代码：{stock_code}\n来源：东方财富"

                                news_list.append({
                                    'title': title,
                                    'date': date_str,
                                    'summary': summary,
                                    'content': content,
                                    'source': 'eastmoney',
                                    'stock_code': stock_code
                                })

                            except Exception as e:
                                logger.error(f"解析新闻项失败: {str(e)}")
                                continue

                        logger.info(f"成功爬取 {len(news_list)} 条新闻")

        except Exception as e:
            logger.error(f"爬取新闻失败: {str(e)}")

        return news_list

    async def crawl_stock_financial(
        self,
        stock_code: str
    ) -> List[Dict[str, Any]]:
        """
        爬取财务数据（东方财富F10）

        Args:
            stock_code: 股票代码

        Returns:
            财务数据列表
        """
        logger.info(f"开始爬取 {stock_code} 的财务数据")

        financials = []

        try:
            market_code, code = self._convert_stock_code(stock_code)

            # 主要财务指标接口
            url = f"http://datacenter-web.eastmoney.com/api/data/v1/get"

            params = {
                'reportName': 'RPT_F10_FINANCE_MAININDEX',
                'columns': 'ALL',
                'filter': f'(SECURITY_CODE="{code}")',
                'pageNumber': '1',
                'pageSize': '10',
                'sortTypes': '-1',
                'sortColumns': 'REPORT_DATE',
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                data = response.json()

                if data.get('result') and data['result'].get('data'):
                    items = data['result']['data']

                    for item in items:
                        try:
                            report_date = item.get('REPORT_DATE', '')[:10]

                            # 主要指标
                            basic_eps = item.get('BASIC_EPS', 0)  # 每股收益
                            total_operate_income = item.get('TOTAL_OPERATE_INCOME', 0)  # 营业收入
                            net_profit = item.get('PARENT_NETPROFIT', 0)  # 净利润
                            roe = item.get('WEIGHTAVG_ROE', 0)  # ROE

                            content = f"财务数据摘要\n"
                            content += f"报告期：{report_date}\n"
                            content += f"股票代码：{stock_code}\n"
                            content += f"每股收益(EPS)：{basic_eps} 元\n"
                            content += f"营业收入：{total_operate_income/100000000:.2f} 亿元\n"
                            content += f"净利润：{net_profit/100000000:.2f} 亿元\n"
                            content += f"ROE：{roe}%\n"
                            content += f"来源：东方财富"

                            financials.append({
                                'title': f"{stock_code} {report_date} 财务数据",
                                'content': content,
                                'period': report_date,
                                'eps': basic_eps,
                                'revenue': total_operate_income,
                                'profit': net_profit,
                                'roe': roe,
                                'source': 'eastmoney',
                                'stock_code': stock_code
                            })

                        except Exception as e:
                            logger.error(f"解析财务数据失败: {str(e)}")
                            continue

                    logger.info(f"成功爬取 {len(financials)} 份财务数据")

        except Exception as e:
            logger.error(f"爬取财务数据失败: {str(e)}")

        return financials

    async def crawl_market_hotspots(
        self,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        爬取市场热点（东方财富要闻）

        Args:
            limit: 爬取数量

        Returns:
            热点列表
        """
        logger.info("开始爬取市场热点")

        hotspots = []

        try:
            # 东方财富要闻接口
            url = "http://finance.eastmoney.com/a/cyw.html"

            response = await self.client.get(url, headers=self.headers)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # 查找新闻列表
                items = soup.select('div.news-item')[:limit]

                for item in items:
                    try:
                        title_el = item.select_one('.news-title a')
                        time_el = item.select_one('.news-time')

                        if title_el:
                            title = title_el.text.strip()
                            time_str = time_el.text.strip() if time_el else datetime.now().strftime('%Y-%m-%d %H:%M')

                            content = f"市场热点：{title}\n时间：{time_str}\n来源：东方财富"

                            hotspots.append({
                                'title': title,
                                'content': content,
                                'time': time_str,
                                'source': 'eastmoney'
                            })

                    except Exception as e:
                        logger.error(f"解析热点失败: {str(e)}")
                        continue

                logger.info(f"成功爬取 {len(hotspots)} 条市场热点")

        except Exception as e:
            logger.error(f"爬取市场热点失败: {str(e)}")

        return hotspots

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()


# 测试代码
async def test_eastmoney_crawler():
    """测试东方财富爬虫"""
    print("=" * 70)
    print("东方财富爬虫测试")
    print("=" * 70)

    crawler = EastmoneyRealCrawler()

    # 测试1：爬取公告
    print("\n[测试1] 爬取贵州茅台(600519)公告...")
    announcements = await crawler.crawl_stock_announcements('600519', limit=5)
    print(f"结果: {len(announcements)} 条公告")
    if announcements:
        print(f"示例: {announcements[0]['title']}")
        print(f"日期: {announcements[0]['date']}")

    # 测试2：爬取新闻
    print("\n[测试2] 爬取股票新闻...")
    news = await crawler.crawl_stock_news('600519', limit=5)
    print(f"结果: {len(news)} 条新闻")
    if news:
        print(f"示例: {news[0]['title'][:50]}")

    # 测试3：爬取财务数据
    print("\n[测试3] 爬取财务数据...")
    financials = await crawler.crawl_stock_financial('600519')
    print(f"结果: {len(financials)} 份财务数据")
    if financials:
        print(f"示例: {financials[0]['title']}")
        print(f"ROE: {financials[0].get('roe', 0)}%")

    # 测试4：爬取市场热点
    print("\n[测试4] 爬取市场热点...")
    hotspots = await crawler.crawl_market_hotspots(limit=5)
    print(f"结果: {len(hotspots)} 条热点")
    if hotspots:
        print(f"示例: {hotspots[0]['title'][:50]}")

    await crawler.close()

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_eastmoney_crawler())
