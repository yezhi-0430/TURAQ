"""
爬虫定时任务调度器

每天凌晨 2 点、9 点、12 点自动爬取股票数据
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from typing import List
import logging

from app.rag.core import get_rag_system
from app.rag.crawlers.stock_crawler import StockDataCrawler
from app.rag.crawlers.sector_crawler import SectorAndHotspotCrawler
from app.database import SessionLocal, Watchlist, WatchlistItem, Stock

logger = logging.getLogger(__name__)


class CrawlerScheduler:
    """爬虫调度器"""

    def __init__(self):
        """初始化调度器"""
        self.scheduler = AsyncIOScheduler()
        self.crawler = StockDataCrawler()
        self.rag = get_rag_system()
        self.is_running = False

    async def crawl_watchlist_stocks(self):
        """
        爬取所有用户自选股的数据

        从数据库读取所有自选股，批量爬取
        """
        try:
            logger.info("=" * 60)
            logger.info(f"开始定时爬虫任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)

            # 从数据库获取所有自选股
            with SessionLocal() as session:
                # 获取所有自选股代码（去重）
                stock_codes = session.query(Stock.symbol).join(WatchlistItem).distinct().all()
                stock_codes = [code[0] for code in stock_codes]

            if not stock_codes:
                logger.info("没有自选股，跳过爬取")
                return

            logger.info(f"准备爬取 {len(stock_codes)} 只股票")

            total_added = 0

            # 逐个爬取
            for i, stock_code in enumerate(stock_codes, 1):
                try:
                    logger.info(f"[{i}/{len(stock_codes)}] 正在爬取 {stock_code}")

                    # 1. 爬取公告
                    announcements = await self.crawler.crawl_cninfo_announcements(
                        stock_code,
                        days=7
                    )

                    for ann in announcements:
                        result = self.rag.add_text(
                            text=ann['content'],
                            metadata={
                                'category': 'announcement',
                                'stock_code': stock_code,
                                'title': ann['title'],
                                'publish_date': ann['date'],
                                'source': 'cninfo',
                                'crawled_at': datetime.now().isoformat()
                            }
                        )
                        if result['success']:
                            total_added += 1

                    # 2. 爬取研报
                    reports = await self.crawler.crawl_eastmoney_reports(
                        stock_code,
                        limit=3
                    )

                    for report in reports:
                        result = self.rag.add_text(
                            text=report['content'],
                            metadata={
                                'category': 'stock_report',
                                'stock_code': stock_code,
                                'title': report['title'],
                                'analyst': report.get('analyst', ''),
                                'rating': report.get('rating', ''),
                                'source': 'eastmoney',
                                'crawled_at': datetime.now().isoformat()
                            }
                        )
                        if result['success']:
                            total_added += 1

                    # 3. 爬取财务数据（每只股票只爬一次，避免重复）
                    # 检查当前时间，只在凌晨 2 点执行
                    if datetime.now().hour == 2:
                        financials = await self.crawler.crawl_sina_financial_data(stock_code)

                        for fin in financials:
                            result = self.rag.add_text(
                                text=fin['content'],
                                metadata={
                                    'category': 'financial_report',
                                    'stock_code': stock_code,
                                    'title': fin['title'],
                                    'period': fin['period'],
                                    'source': 'sina',
                                    'crawled_at': datetime.now().isoformat()
                                }
                            )
                            if result['success']:
                                total_added += 1

                    logger.info(f"  ✓ {stock_code} 爬取完成")

                except Exception as e:
                    logger.error(f"  ✗ {stock_code} 爬取失败: {str(e)}")
                    continue

            logger.info("=" * 60)
            logger.info(f"爬虫任务完成 - 共添加 {total_added} 条数据到知识库")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"爬虫任务执行失败: {str(e)}")

    def start(self):
        """
        启动定时任务

        每天 2:00、9:00、12:00 自动执行
        """
        if self.is_running:
            logger.warning("爬虫调度器已在运行")
            return

        try:
            # 添加定时任务 - 凌晨 2 点（全量爬取）
            self.scheduler.add_job(
                self.crawl_watchlist_stocks,
                CronTrigger(hour=2, minute=0),
                id='crawler_02am',
                name='凌晨2点爬虫任务',
                replace_existing=True
            )

            # 添加定时任务 - 上午 9 点（市场开盘前）
            self.scheduler.add_job(
                self.crawl_watchlist_stocks,
                CronTrigger(hour=9, minute=0),
                id='crawler_09am',
                name='上午9点爬虫任务',
                replace_existing=True
            )

            # 添加定时任务 - 中午 12 点（午间）
            self.scheduler.add_job(
                self.crawl_watchlist_stocks,
                CronTrigger(hour=12, minute=0),
                id='crawler_12pm',
                name='中午12点爬虫任务',
                replace_existing=True
            )

            # 启动调度器
            self.scheduler.start()
            self.is_running = True

            logger.info("爬虫调度器启动成功")
            logger.info("定时任务: 每天 2:00、9:00、12:00 自动爬取")

        except Exception as e:
            logger.error(f"启动爬虫调度器失败: {str(e)}")

    def stop(self):
        """停止定时任务"""
        if not self.is_running:
            return

        try:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("爬虫调度器已停止")

        except Exception as e:
            logger.error(f"停止爬虫调度器失败: {str(e)}")

    async def run_now(self):
        """立即执行一次爬虫任务（用于测试）"""
        logger.info("手动触发爬虫任务")
        await self.crawl_watchlist_stocks()


# 全局调度器实例
_scheduler = None


def get_crawler_scheduler() -> CrawlerScheduler:
    """获取爬虫调度器单例"""
    global _scheduler

    if _scheduler is None:
        _scheduler = CrawlerScheduler()

    return _scheduler


def start_crawler_scheduler():
    """启动爬虫调度器（在应用启动时调用）"""
    scheduler = get_crawler_scheduler()
    scheduler.start()


def stop_crawler_scheduler():
    """停止爬虫调度器（在应用关闭时调用）"""
    scheduler = get_crawler_scheduler()
    scheduler.stop()
