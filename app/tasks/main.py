"""
定时任务主程序
支持每日定时执行和手动触发
"""
import asyncio
import argparse
from datetime import datetime
from loguru import logger
import sys

# 添加项目路径
sys.path.insert(0, '.')

from app.tasks.scheduler import scheduler
from app.services.notify import notify_service


async def run_daily_task(trade_date: str = None):
    """执行每日任务"""
    logger.info("=" * 50)
    logger.info("开始执行每日任务")
    logger.info("=" * 50)

    # 1. 数据同步
    logger.info("[1/3] 同步数据...")
    try:
        await scheduler.sync_data(trade_date)
        logger.info("数据同步完成")
    except Exception as e:
        logger.error(f"数据同步失败: {e}")
        return {"status": "error", "step": "sync_data", "message": str(e)}

    # 2. 执行分析
    logger.info("[2/3] 执行分析...")
    try:
        report_data = await scheduler.run_analysis(trade_date)
        logger.info("分析完成")
    except Exception as e:
        logger.error(f"分析执行失败: {e}")
        return {"status": "error", "step": "run_analysis", "message": str(e)}

    # 3. 推送通知
    logger.info("[3/3] 推送通知...")
    try:
        await scheduler.notify_report(trade_date, report_data)
        logger.info("通知推送完成")
    except Exception as e:
        logger.error(f"通知推送失败: {e}")
        return {"status": "error", "step": "notify_report", "message": str(e)}

    logger.info("=" * 50)
    logger.info("每日任务执行完成")
    logger.info("=" * 50)

    return {"status": "success", "trade_date": trade_date}


async def test_notify():
    """测试通知推送"""
    logger.info("测试企业微信通知...")

    test_content = """## 🧪 测试消息

这是一条测试消息，用于验证企业微信机器人是否正常工作。

**时间**: {time}
**状态**: 推送成功
""".format(time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    result = await notify_service.wecom.send_markdown(test_content)
    if result:
        logger.info("测试消息推送成功！")
    else:
        logger.error("测试消息推送失败")

    return result


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="轻舟版交易系统定时任务")
    parser.add_argument("--mode", choices=["daily", "sync", "analyze", "notify", "test"], default="daily",
                      help="执行模式: daily(完整流程), sync(仅同步), analyze(仅分析), notify(仅推送), test(测试通知)")
    parser.add_argument("--date", type=str, default=None, help="交易日，格式YYYY-MM-DD")
    parser.add_argument("--time", type=str, default=None, help="定时任务执行时间，格式HH:MM")

    args = parser.parse_args()

    # 配置日志
    logger.remove()
    logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

    trade_date = args.date or datetime.now().strftime("%Y-%m-%d")

    if args.mode == "test":
        result = asyncio.run(test_notify())
        sys.exit(0 if result else 1)

    if args.mode == "daily":
        result = asyncio.run(run_daily_task(trade_date))
    elif args.mode == "sync":
        asyncio.run(scheduler.sync_data(trade_date))
        result = {"status": "success"}
    elif args.mode == "analyze":
        result = asyncio.run(scheduler.run_analysis(trade_date))
    elif args.mode == "notify":
        report_data = asyncio.run(scheduler.run_analysis(trade_date))
        result = asyncio.run(scheduler.notify_report(trade_date, report_data))
    else:
        result = {"status": "unknown_mode"}

    logger.info(f"执行结果: {result}")
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
