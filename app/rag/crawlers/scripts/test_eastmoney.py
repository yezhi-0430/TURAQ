"""测试东方财富爬虫"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.rag.crawlers.eastmoney_working import EastmoneyWorkingCrawler


async def test():
    print('=' * 70)
    print('东方财富爬虫测试')
    print('=' * 70)

    crawler = EastmoneyWorkingCrawler()

    # 1. 实时行情
    print('\n[1] 获取实时行情...')
    realtime = await crawler.get_stock_realtime('600519')
    if realtime:
        print(f'  股票: {realtime.get("name")} ({realtime.get("code")})')
        print(f'  价格: {realtime.get("price")} 元')
        print(f'  涨跌幅: {realtime.get("change_pct")}%')
    else:
        print('  [失败] 未获取到数据')

    # 2. 资金流向
    print('\n[2] 获取资金流向...')
    flows = await crawler.get_fund_flow('600519', limit=5)
    if flows:
        print(f'  获取 {len(flows)} 天数据')
        print(f'  最新: {flows[0].get("date")}')
        print(f'  主力净流入: {flows[0].get("main_force", 0)/10000:.2f} 万元')
    else:
        print('  [失败] 未获取到数据')

    # 3. 个股新闻
    print('\n[3] 获取个股新闻...')
    news = await crawler.get_stock_news('600519', limit=5)
    if news:
        print(f'  获取 {len(news)} 条新闻')
        print(f'  最新: {news[0].get("title", "")[:40]}')
    else:
        print('  [失败] 未获取到数据')

    # 4. 热门股票
    print('\n[4] 获取热门股票...')
    hot = await crawler.get_hot_stocks(limit=10)
    if hot:
        print(f'  获取 {len(hot)} 只热门股')
        for i, stock in enumerate(hot[:3], 1):
            print(f'  [{i}] {stock.get("name")}({stock.get("code")}) {stock.get("change_pct")}%')
    else:
        print('  [失败] 未获取到数据')

    await crawler.close()

    print('\n' + '=' * 70)
    print('测试完成')
    print('=' * 70)


if __name__ == '__main__':
    asyncio.run(test())
