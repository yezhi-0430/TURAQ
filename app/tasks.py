"""
定时任务调度器
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.paper_trading.tasks import match_pending_orders, record_daily_snapshots
from app.stock_list import stock_list_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# 记录连续失败次数
_consecutive_failures = 0
_MAX_FAILURES_BEFORE_ALERT = 3


@scheduler.scheduled_job('cron', hour=2, minute=0, timezone='Asia/Shanghai')
async def update_stock_list():
    """每天凌晨2点更新股票列表"""
    global _consecutive_failures

    try:
        logger.info("定时任务: 开始更新股票列表...")
        # 数量不变是正常情况；只有源失败或被保护规则拒绝才算失败。
        updated, detail = await stock_list_service.update_from_api()
        if updated:
            logger.info(f"定时任务: {detail}")
            _consecutive_failures = 0
        else:
            _consecutive_failures += 1
            logger.warning(f"定时任务: 股票列表未更新: {detail}")
    except Exception as e:
        _consecutive_failures += 1
        logger.error(f"定时任务: 股票列表更新失败: {e}", exc_info=True)

    if _consecutive_failures >= _MAX_FAILURES_BEFORE_ALERT:
        logger.critical(
            f"定时任务: 股票列表已连续{_consecutive_failures}次未能更新，请检查交易所名单源！"
        )


@scheduler.scheduled_job('cron', day_of_week='mon-fri', hour='9-11,13-14', minute='*',
                         timezone='Asia/Shanghai', max_instances=1, coalesce=True)
async def paper_trading_match():
    """交易时段每分钟按真实行情撮合挂单（时段边界由撮合函数判断）"""
    try:
        await match_pending_orders()
    except Exception as e:
        logger.error(f"定时任务: 模拟交易撮合失败: {e}", exc_info=True)


@scheduler.scheduled_job('cron', day_of_week='mon-fri', hour=15, minute=5,
                         timezone='Asia/Shanghai', max_instances=1, coalesce=True)
async def paper_trading_close():
    """收盘后撤销当日未成交委托并记录日终快照"""
    try:
        await record_daily_snapshots()
    except Exception as e:
        logger.error(f"定时任务: 模拟交易日终快照失败: {e}", exc_info=True)


def start_scheduler():
    """启动调度器"""
    if not scheduler.running:
        scheduler.start()
        logger.info("定时任务调度器已启动")


def shutdown_scheduler():
    """关闭调度器"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("定时任务调度器已关闭")
