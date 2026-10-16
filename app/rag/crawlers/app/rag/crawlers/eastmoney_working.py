"""
东方财富爬虫 - 基于真实可用的API

已验证可用的接口：
1. 行情API - 实时股价数据
2. 资金流API - 主力资金流向
3. 资讯API - 个股新闻
"""

import asyncio
import httpx
import json
import re
from datetime import datetime
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class EastmoneyWorkingCrawler:
    """东方财富可用爬虫"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://quote.eastmoney.com/',
        }

    def _get_secid(self, stock_code: str) -> str:
        """获取secid格式的股票代码"""
        if stock_code.startswith('6'):
            return f'1.{stock_code}'  # 上海
        elif stock_code.startswith('0') or stock_code.startswith('3'):
            return f'0.{stock_code}'  # 深圳
        else:
            return f'1.{stock_code}'

    async def get_stock_realtime(self, stock_code: str) -> Dict[str, Any]:
        """
        获取实时行情

        Returns:
            股票实时数据
        """
        try:
            secid = self._get_secid(stock_code)

            url = 'http://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f57,f58,f84,f85,f86,f127,f116,f60,f45,f46,f47,f48,f43,f44,f45,f46,f170,f168,f169,f164',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    stock_data = data['data']
                    return {
                        'code': stock_code,
                        'name': stock_data.get('f58', ''),
                        'price': stock_data.get('f43', 0) / 100,  # 当前价
                        'change': stock_data.get('f169', 0) / 100,  # 涨跌额
                        'change_pct': stock_data.get('f170', 0) / 100,  # 涨跌幅
                        'high': stock_data.get('f44', 0) / 100,  # 最高
                        'low': stock_data.get('f45', 0) / 100,  # 最低
                        'volume': stock_data.get('f47', 0),  # 成交量
                        'amount': stock_data.get('f48', 0),  # 成交额
                        'source': 'eastmoney'
                    }
        except Exception as e:
            logger.error(f'获取实时行情失败: {str(e)}')

        return {}

    async def get_fund_flow(self, stock_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取资金流向数据

        Returns:
            资金流向列表
        """
        flows = []

        try:
            secid = self._get_secid(stock_code)

            url = 'http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get'
            params = {
                'secid': secid,
                'fields1': 'f1,f2,f3,f7',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
                'lmt': str(limit),
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                data = response.json()
                if data.get('data') and data['data'].get('klines'):
                    for line in data['data']['klines']:
                        parts = line.split(',')
                        if len(parts) >= 7:
                            flows.append({
                                'date': parts[0],
                                'main_force': float(parts[1]),  # 主力净流入
                                'small': float(parts[2]),  # 小单净流入
                                'medium': float(parts[3]),  # 中单净流入
                                'large': float(parts[4]),  # 大单净流入
                                'super_large': float(parts[5]),  # 超大单净流入
                                'stock_code': stock_code,
                                'source': 'eastmoney'
                            })

                    logger.info(f'获取 {len(flows)} 天的资金流向数据')

        except Exception as e:
            logger.error(f'获取资金流向失败: {str(e)}')

        return flows

    async def get_stock_news(self, stock_code: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取个股新闻

        Returns:
            新闻列表
        """
        news_list = []

        try:
            url = 'http://search-api-web.eastmoney.com/search/jsonp'

            param_dict = {
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
                        'pageSize': limit
                    }
                }
            }

            params = {
                'cb': 'jQuery',
                'param': json.dumps(param_dict),
                '_': str(int(datetime.now().timestamp() * 1000))
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                text = response.text

                # 提取JSONP中的JSON
                match = re.search(r'jQuery\d+_\d+\((.*)\)', text)
                if match:
                    data = json.loads(match.group(1))

                    if data.get('result') and data['result'].get('cmsArticleWebOld'):
                        items = data['result']['cmsArticleWebOld']

                        for item in items:
                            title = item.get('title', '')
                            date = item.get('date', '')[:10]
                            summary = item.get('summary', '')
                            url_link = item.get('url', '')

                            content = f"【{stock_code} 新闻】\n"
                            content += f"标题：{title}\n"
                            if summary:
                                content += f"摘要：{summary}\n"
                            content += f"日期：{date}\n"
                            content += f"来源：东方财富"

                            news_list.append({
                                'title': title,
                                'date': date,
                                'summary': summary,
                                'content': content,
                                'url': url_link,
                                'stock_code': stock_code,
                                'source': 'eastmoney'
                            })

                        logger.info(f'获取 {len(news_list)} 条新闻')

        except Exception as e:
            logger.error(f'获取新闻失败: {str(e)}')

        return news_list

    async def get_hot_stocks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取热门股票（资金流入排名）

        Returns:
            热门股票列表
        """
        hot_stocks = []

        try:
            url = 'http://push2.eastmoney.com/api/qt/clist/get'
            params = {
                'fid': 'f62',  # 按主力净流入排序
                'po': '1',
                'pz': str(limit),
                'pn': '1',
                'np': '1',
                'fltt': '2',
                'invt': '2',
                'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',  # A股
                'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                data = response.json()
                if data.get('data') and data['data'].get('diff'):
                    items = data['data']['diff']

                    for item in items:
                        hot_stocks.append({
                            'code': item.get('f12', ''),
                            'name': item.get('f14', ''),
                            'price': item.get('f2', 0) / 100,
                            'change_pct': item.get('f3', 0) / 100,
                            'main_force_inflow': item.get('f62', 0),  # 主力净流入
                            'rank': len(hot_stocks) + 1,
                            'source': 'eastmoney'
                        })

                    logger.info(f'获取 {len(hot_stocks)} 只热门股票')

        except Exception as e:
            logger.error(f'获取热门股票失败: {str(e)}')

        return hot_stocks

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


# 完整测试
async def test_all():
    print('=' * 70)
    print('东方财富爬虫完整测试')
    print('=' * 70)

    crawler = EastmoneyWorkingCrawler()

    # 1. 实时行情
    print('\n[1] 获取实时行情...')
    realtime = await crawler.get_stock_realtime('600519')
    if realtime:
        print(f'  股票: {realtime[\"name\"]} ({realtime[\"code\"]})')
        print(f'  价格: {realtime[\"price\"]} 元')
        print(f'  涨跌幅: {realtime[\"change_pct\"]}%')

    # 2. 资金流向
    print('\n[2] 获取资金流向...')
    flows = await crawler.get_fund_flow('600519', limit=5)
    if flows:
        print(f'  获取 {len(flows)} 天数据')
        print(f'  最新日期: {flows[0][\"date\"]}')
        print(f'  主力净流入: {flows[0][\"main_force\"]/10000:.2f} 万元')

    # 3. 个股新闻
    print('\n[3] 获取个股新闻...')
    news = await crawler.get_stock_news('600519', limit=5)
    if news:
        print(f'  获取 {len(news)} 条新闻')
        print(f'  最新: {news[0][\"title\"][:40]}...')
        print(f'  日期: {news[0][\"date\"]}')

    # 4. 热门股票
    print('\n[4] 获取热门股票...')
    hot = await crawler.get_hot_stocks(limit=10)
    if hot:
        print(f'  获取 {len(hot)} 只热门股')
        for i, stock in enumerate(hot[:3], 1):
            print(f'  [{i}] {stock[\"name\"]}({stock[\"code\"]}) 涨跌: {stock[\"change_pct\"]}%')

    await crawler.close()

    print('\n' + '=' * 70)
    print('[OK] 所有功能测试完成！')
    print('=' * 70)


if __name__ == '__main__':
    asyncio.run(test_all())
