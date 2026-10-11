"""
定时任务调度器
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
        old_count = len(stock_list_service.stocks)

        await stock_list_service.update_from_api()

        new_count = len(stock_list_service.stocks)

        # 检查是否真的更新成功
        if new_count == old_count and old_count > 0:
            logger.warning("定时任务: 股票数量未变化，可能更新失败")
            _consecutive_failures += 1
        elif new_count == 0:
            logger.error("定时任务: 更新后股票列表为空！")
            _consecutive_failures += 1
        else:
            logger.info(f"定时任务: 股票列表更新完成 ({old_count} -> {new_count})")
            _consecutive_failures = 0  # 重置失败计数

        # 连续失败告警
        if _consecutive_failures >= _MAX_FAILURES_BEFORE_ALERT:
            logger.critical(
                f"定时任务: 股票列表已连续{_consecutive_failures}次更新失败或无变化，请检查！"
            )

    except Exception as e:
        _consecutive_failures += 1
        logger.error(f"定时任务: 股票列表更新失败: {e}", exc_info=True)

        if _consecutive_failures >= _MAX_FAILURES_BEFORE_ALERT:
            logger.critical(
                f"定时任务: 已连续{_consecutive_failures}次失败，请立即检查！"
            )


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
