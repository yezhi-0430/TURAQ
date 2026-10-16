"""
测试爬虫功能

测试爬虫调度器和立即执行功能
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_crawler():
    """测试爬虫功能"""
    print("=" * 60)
    print("爬虫功能测试")
    print("=" * 60)

    from app.rag.crawlers.stock_crawler import StockDataCrawler

    crawler = StockDataCrawler()

    # 测试单只股票爬取
    print("\n[测试] 爬取股票公告...")
    try:
        announcements = await crawler.crawl_cninfo_announcements("600519", days=7)
        print(f"  找到 {len(announcements)} 条公告")
        if announcements:
            print(f"  示例: {announcements[0]['title'][:50]}...")
    except Exception as e:
        print(f"  错误: {str(e)}")

    print("\n[测试] 爬取券商研报...")
    try:
        reports = await crawler.crawl_eastmoney_reports("600519", limit=3)
        print(f"  找到 {len(reports)} 条研报")
        if reports:
            print(f"  示例: {reports[0]['title'][:50]}...")
    except Exception as e:
        print(f"  错误: {str(e)}")

    print("\n[测试] 爬取财务数据...")
    try:
        financials = await crawler.crawl_sina_financial_data("600519")
        print(f"  找到 {len(financials)} 份财务数据")
        if financials:
            print(f"  示例: {financials[0]['title'][:50]}...")
    except Exception as e:
        print(f"  错误: {str(e)}")

    await crawler.close()

    print("\n" + "=" * 60)
    print("爬虫功能测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_crawler())
