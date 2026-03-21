"""
定时任务调度器
"""
from datetime import datetime, timedelta
from loguru import logger
import asyncio

from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.stock_filter import stock_filter_service
from app.services.buy_point import buy_point_service
from app.services.sell_point import sell_point_service
from app.services.account_adapter import account_adapter_service
from app.services.notify import notify_service
from app.data.tushare_client import tushare_client
from app.models.schemas import AccountInput, AccountPosition, StockInput
from app.models.holding import Holding
from app.core.config import settings
from app.core.database import async_session_factory
from sqlalchemy import select


class TaskScheduler:
    """定时任务调度器"""

    def __init__(self):
        self.logger = logger

    async def get_holdings_from_db(self) -> list:
        """从数据库获取持仓"""
        async with async_session_factory() as session:
            result = await session.execute(select(Holding))
            holdings = result.scalars().all()
            holdings_list = [h.to_dict() for h in holdings]
            
            # 刷新现价
            for h in holdings_list:
                try:
                    detail = tushare_client.get_stock_detail(
                        h["ts_code"], 
                        datetime.now().strftime("%Y%m%d")
                    )
                    if detail and detail.get("close"):
                        h["market_price"] = detail.get("close")
                        if h.get("cost_price"):
                            h["pnl_pct"] = round(
                                (h["market_price"] - h["cost_price"]) / h["cost_price"] * 100, 
                                2
                            )
                        if h.get("holding_qty"):
                            h["holding_market_value"] = h["holding_qty"] * h["market_price"]
                except:
                    pass
            
            return holdings_list

    async def run_daily_analysis(self, trade_date: str = None):
        """
        执行每日分析任务

        Args:
            trade_date: 交易日，默认今天
        """
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        self.logger.info(f"开始执行每日分析任务: {trade_date}")

        try:
            # 1. 同步数据 (16:30)
            await self.sync_data(trade_date)

            # 2. 执行分析 (16:40)
            report_data = await self.run_analysis(trade_date)

            # 3. 推送通知
            await self.notify_report(trade_date, report_data)

            self.logger.info(f"每日分析任务完成: {trade_date}")
            return {"status": "success", "trade_date": trade_date}

        except Exception as e:
            self.logger.error(f"每日分析任务失败: {e}")
            return {"status": "error", "message": str(e)}

    async def sync_data(self, trade_date: str):
        """同步数据"""
        self.logger.info("同步数据...")

        # 获取当日行情数据
        index_data = tushare_client.get_index_quote(trade_date.replace("-", ""))
        sector_data = tushare_client.get_sector_data(trade_date.replace("-", ""))
        stock_data = tushare_client.get_stock_list(trade_date.replace("-", ""), limit=100)

        self.logger.info(f"数据同步完成: 指数{len(index_data)}, 板块{len(sector_data)}, 个股{len(stock_data)}")

    async def run_analysis(self, trade_date: str) -> dict:
        """执行分析，返回完整报告数据"""
        self.logger.info("执行市场环境分析...")
        market_env = market_env_service.get_current_env(trade_date)
        market_env_dict = {
            "market_env_tag": market_env.market_env_tag.value,
            "breakout_allowed": market_env.breakout_allowed,
            "risk_level": market_env.risk_level.value,
            "market_comment": market_env.market_comment,
            "index_score": market_env.index_score,
            "sentiment_score": market_env.sentiment_score,
            "overall_score": market_env.overall_score
        }
        self.logger.info(f"市场环境: {market_env.market_env_tag.value}")

        self.logger.info("执行板块扫描...")
        sector_scan = sector_scan_service.scan(trade_date)
        sector_dict = {
            "mainline_sectors": [s.model_dump() for s in sector_scan.mainline_sectors],
            "sub_mainline_sectors": [s.model_dump() for s in sector_scan.sub_mainline_sectors],
            "mainline_count": len(sector_scan.mainline_sectors),
            "sub_mainline_count": len(sector_scan.sub_mainline_sectors)
        }
        self.logger.info(f"主线板块数: {len(sector_scan.mainline_sectors)}")

        # 获取个股数据用于筛选
        self.logger.info("获取个股数据...")
        stock_list = tushare_client.get_stock_list(trade_date.replace("-", ""), limit=50)

        from app.models.schemas import StockInput
        stocks = [
            StockInput(
                ts_code=s["ts_code"],
                stock_name=s["stock_name"],
                sector_name=s.get("sector_name", "未知"),
                close=s["close"],
                change_pct=s["change_pct"],
                turnover_rate=s["turnover_rate"],
                amount=s["amount"],
                vol_ratio=s.get("vol_ratio"),
                high=s["high"],
                low=s["low"],
                open=s["open"],
                pre_close=s["pre_close"],
            )
            for s in stock_list
        ]

        # 从数据库获取持仓
        holdings_list = await self.get_holdings_from_db()
        holdings = [AccountPosition(**h) for h in holdings_list]

        self.logger.info("执行三池分类...")
        stock_pools = stock_filter_service.classify_pools(trade_date, stocks, holdings_list)
        pools_dict = {
            "market_watch_pool": [s.model_dump() for s in stock_pools.market_watch_pool[:10]],
            "account_executable_pool": [s.model_dump() for s in stock_pools.account_executable_pool[:10]],
            "holding_process_pool": [s.model_dump() for s in stock_pools.holding_process_pool],
            "market_watch_count": len(stock_pools.market_watch_pool),
            "account_executable_count": len(stock_pools.account_executable_pool),
            "holding_process_count": len(stock_pools.holding_process_pool)
        }

        self.logger.info("执行买点分析...")
        buy_analysis = buy_point_service.analyze(trade_date, stocks)
        buy_dict = {
            "available_buy_points": [bp.model_dump() for bp in buy_analysis.available_buy_points[:5]],
            "observe_buy_points": [bp.model_dump() for bp in buy_analysis.observe_buy_points[:5]],
            "market_env_tag": buy_analysis.market_env_tag.value
        }

        self.logger.info("执行卖点分析...")
        sell_analysis = sell_point_service.analyze(trade_date, holdings)
        sell_dict = {
            "sell_positions": [sp.model_dump() for sp in sell_analysis.sell_positions],
            "reduce_positions": [sp.model_dump() for sp in sell_analysis.reduce_positions],
            "hold_positions": [sp.model_dump() for sp in sell_analysis.hold_positions]
        }

        self.logger.info("执行账户适配...")
        account = AccountInput(
            total_asset=settings.qingzhou_total_asset,
            available_cash=settings.qingzhou_available_cash,
            total_position_ratio=settings.qingzhou_total_position_ratio,
            holding_count=len(holdings),
            today_new_buy_count=0
        )
        account_adapt = account_adapter_service.adapt(trade_date, account, holdings)

        # 生成摘要
        summary = self._generate_summary(trade_date, market_env, account_adapt, holdings)

        return {
            "trade_date": trade_date,
            "market_env": market_env_dict,
            "sector_scan": sector_dict,
            "stock_pools": pools_dict,
            "buy_analysis": buy_dict,
            "sell_analysis": sell_dict,
            "account_fit": account_adapt.model_dump(),
            "summary": summary
        }

    def _generate_summary(self, trade_date: str, market_env, account_output, holdings) -> dict:
        """生成执行摘要"""
        from app.models.schemas import MarketEnvTag

        if not account_output.new_position_allowed:
            today_action = "少出手或不出手"
        elif market_env.market_env_tag == MarketEnvTag.ATTACK:
            today_action = "可适度出手"
        elif market_env.market_env_tag == MarketEnvTag.NEUTRAL:
            today_action = "谨慎出手"
        else:
            today_action = "防守为主"

        if holdings:
            loss_holdings = [h for h in holdings if h.pnl_pct < 0]
            if loss_holdings:
                focus = "优先处理亏损持仓"
            else:
                focus = "持仓盈利，可考虑新机会"
        else:
            focus = "关注主线板块核心股"

        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            avoid = "弱势股、杂毛股、跟风股"
        elif market_env.market_env_tag == MarketEnvTag.NEUTRAL:
            avoid = "高位追涨、纯跟风"
        else:
            avoid = "无明确逻辑的杂毛股"

        return {
            "trade_date": trade_date,
            "today_action": today_action,
            "focus": focus,
            "avoid": avoid,
            "market_env_tag": market_env.market_env_tag.value,
            "breakout_allowed": market_env.breakout_allowed,
            "account_action_tag": account_output.account_action_tag,
            "new_position_allowed": account_output.new_position_allowed,
            "priority_action": account_output.priority_action
        }

    async def notify_report(self, trade_date: str, report_data: dict):
        """推送报告"""
        if not settings.notify_enabled:
            self.logger.info("通知未启用，跳过推送")
            return

        self.logger.info("推送每日报告...")
        await notify_service.notify_daily_report(report_data)
        self.logger.info("报告推送完成")

    async def run_summary(self, trade_date: str = None):
        """生成执行摘要"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        self.logger.info(f"生成执行摘要: {trade_date}")

        # 获取各项数据
        market_env = market_env_service.get_current_env(trade_date)
        # ... 其他分析

        summary = {
            "trade_date": trade_date,
            "market_env_tag": market_env.market_env_tag.value,
            "today_action": "根据市场环境判断",
            "focus": "关注主线板块",
            "avoid": "规避弱势股"
        }

        return summary


# 全局调度器实例
scheduler = TaskScheduler()


# 如果直接运行
if __name__ == "__main__":
    import sys
    trade_date = sys.argv[1] if len(sys.argv) > 1 else None
    result = asyncio.run(scheduler.run_daily_analysis(trade_date))
    print(result)
