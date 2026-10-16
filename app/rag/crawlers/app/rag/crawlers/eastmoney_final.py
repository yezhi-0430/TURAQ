"""
东方财富爬虫 - 实际可用版本

已验证可用：
1. 实时行情 ✓
2. 资金流向 ✓
3. 公司公告 ✓
4. 热门股票 ✓
"""

import asyncio
import httpx
import json
from datetime import datetime
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class EastmoneyCrawler:
    """东方财富实际可用爬虫"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://quote.eastmoney.com/',
        }

    def _get_secid(self, stock_code: str) -> str:
        """转换股票代码格式"""
        if stock_code.startswith('6'):
            return f'1.{stock_code}'
        elif stock_code.startswith('0') or stock_code.startswith('3'):
            return f'0.{stock_code}'
        return f'1.{stock_code}'

    async def get_stock_info(self, stock_code: str) -> Dict[str, Any]:
        """获取股票实时信息（已验证可用）"""
        try:
            secid = self._get_secid(stock_code)
            url = 'http://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f57,f58,f43,f44,f45,f46,f170,f47,f48',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    d = data['data']

                    content = f"【{stock_code} 实时行情】\n"
                    content += f"股票名称：{d.get('f58', '')}\n"
                    content += f"当前价格：{d.get('f43', 0)/100} 元\n"
                    content += f"涨跌幅：{d.get('f170', 0)/100}%\n"
                    content += f"最高价：{d.get('f44', 0)/100} 元\n"
                    content += f"最低价：{d.get('f45', 0)/100} 元\n"
                    content += f"成交量：{d.get('f47', 0)} 手\n"
                    content += f"成交额：{d.get('f48', 0)/100000000:.2f} 亿元\n"
                    content += f"数据来源：东方财富"

                    return {
                        'title': f"{d.get('f58', '')}({stock_code}) 实时行情",
                        'content': content,
                        'stock_code': stock_code,
                        'source': 'eastmoney',
                        'type': 'realtime'
                    }
        except Exception as e:
            logger.error(f'获取股票信息失败: {str(e)}')

        return {}

    async def get_announcements(self, stock_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取公司公告（已验证可用）"""
        announcements = []

        try:
            url = 'http://np-anotice-stock.eastmoney.com/api/security/ann'
            params = {
                'sr': '-1',
                'page_size': str(limit),
                'page_index': '1',
                'ann_type': 'SHA,SZA',
                'stock_list': stock_code,
                'f_node': '0'
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                data = response.json()

                if data.get('data') and data['data'].get('list'):
                    items = data['data']['list']

                    for item in items[:limit]:
                        title = item.get('title', '')
                        time_str = item.get('display_time', '')[:10]

                        content = f"【{stock_code} 公告】\n"
                        content += f"标题：{title}\n"
                        content += f"日期：{time_str}\n"
                        content += f"来源：东方财富"

                        announcements.append({
                            'title': title,
                            'content': content,
                            'date': time_str,
                            'stock_code': stock_code,
                            'source': 'eastmoney',
                            'type': 'announcement'
                        })

                    logger.info(f'获取 {len(announcements)} 条公告')

        except Exception as e:
            logger.error(f'获取公告失败: {str(e)}')

        return announcements

    async def get_fund_flow(self, stock_code: str, days: int = 5) -> List[Dict[str, Any]]:
        """获取资金流向（已验证可用）"""
        flows = []

        try:
            secid = self._get_secid(stock_code)
            url = 'http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get'
            params = {
                'secid': secid,
                'fields1': 'f1,f2,f3,f7',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
                'lmt': str(days),
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                data = response.json()

                if data.get('data') and data['data'].get('klines'):
                    for line in data['data']['klines']:
                        parts = line.split(',')
                        if len(parts) >= 5:
                            date = parts[0]
                            main_force = float(parts[1])

                            content = f"【{stock_code} 资金流向】\n"
                            content += f"日期：{date}\n"
                            content += f"主力净流入：{main_force/10000:.2f} 万元\n"
                            content += f"来源：东方财富"

                            flows.append({
                                'title': f"{stock_code} {date} 资金流向",
                                'content': content,
                                'date': date,
                                'main_force': main_force,
                                'stock_code': stock_code,
                                'source': 'eastmoney',
                                'type': 'fund_flow'
                            })

                    logger.info(f'获取 {len(flows)} 天资金流向')

        except Exception as e:
            logger.error(f'获取资金流向失败: {str(e)}')

        return flows

    async def get_hot_stocks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取热门股票（已验证可用）"""
        hot_stocks = []

        try:
            url = 'http://push2.eastmoney.com/api/qt/clist/get'
            params = {
                'fid': 'f62',
                'po': '1',
                'pz': str(limit),
                'pn': '1',
                'np': '1',
                'fltt': '2',
                'invt': '2',
                'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
                'fields': 'f12,f14,f2,f3,f62',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
            }

            response = await self.client.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                data = response.json()

                if data.get('data') and data['data'].get('diff'):
                    items = data['data']['diff']

                    content = "【今日热门股票】\n"

                    for i, item in enumerate(items[:limit], 1):
                        code = item.get('f12', '')
                        name = item.get('f14', '')
                        price = item.get('f2', 0) / 100
                        change_pct = item.get('f3', 0) / 100

                        content += f"{i}. {name}({code}) "
                        content += f"价格:{price} 涨跌:{change_pct}%\n"

                        hot_stocks.append({
                            'code': code,
                            'name': name,
                            'rank': i
                        })

                    content += f"来源：东方财富"

                    # 返回一个汇总文档
                    if hot_stocks:
                        logger.info(f'获取 {len(hot_stocks)} 只热门股票')
                        return [{
                            'title': '今日热门股票排行',
                            'content': content,
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'source': 'eastmoney',
                            'type': 'hot_stocks',
                            'stocks': hot_stocks
                        }]

        except Exception as e:
            logger.error(f'获取热门股票失败: {str(e)}')

        return []

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


# 测试函数
async def test_crawler():
    print('=' * 70)
    print('东方财富爬虫完整测试')
    print('=' * 70)

    crawler = EastmoneyCrawler()

    # 1. 实时行情
    print('\n[1] 实时行情')
    info = await crawler.get_stock_info('600519')
    if info:
        print(f'  [OK] {info.get("title")}')
    else:
        print('  [FAIL]')

    # 2. 公司公告
    print('\n[2] 公司公告')
    announcements = await crawler.get_announcements('600519', 3)
    if announcements:
        print(f'  [OK] 获取 {len(announcements)} 条')
        print(f'  示例: {announcements[0].get("title")[:40]}')
    else:
        print('  [FAIL]')

    # 3. 资金流向
    print('\n[3] 资金流向')
    flows = await crawler.get_fund_flow('600519', 3)
    if flows:
        print(f'  [OK] 获取 {len(flows)} 天')
    else:
        print('  [FAIL]')

    # 4. 热门股票
    print('\n[4] 热门股票')
    hot = await crawler.get_hot_stocks(10)
    if hot:
        print(f'  [OK] 获取成功')
    else:
        print('  [FAIL]')

    await crawler.close()

    print('\n' + '=' * 70)
    print('[完成] 东方财富爬虫测试完成')
    print('=' * 70)


if __name__ == '__main__':
    asyncio.run(test_crawler())
