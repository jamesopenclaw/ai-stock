"""
定时任务调度器
"""
import asyncio
from datetime import datetime

from loguru import logger

from app.services.account_adapter import account_adapter_service
from app.services.decision_flow import decision_flow_service
from app.core.config import settings
from app.services.market_data_gateway import market_data_gateway
from app.services.market_env import market_env_service
from app.services.notify import notify_service
from app.services.review_snapshot import review_snapshot_service
from app.services.task_run_service import task_run_service
from app.models.schemas import AccountInput


class TaskScheduler:
    """定时任务调度器"""

    TASK_RETRY_LIMITS = {
        "daily": 2,
        "sync": 2,
        "analyze": 2,
        "notify": 2,
    }
    RETRY_DELAY_SECONDS = 1.0
    REVIEW_OUTCOME_REFRESH_BATCH_ROWS = 20
    REVIEW_OUTCOME_REFRESH_MAX_PASSES = 5
    REVIEW_OUTCOME_REFRESH_SLEEP_SECONDS = 0.5

    def __init__(self):
        self.logger = logger

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
            await self._run_daily_pipeline(trade_date)

            self.logger.info(f"每日分析任务完成: {trade_date}")
            return {"status": "success", "trade_date": trade_date}

        except Exception as e:
            self.logger.error(f"每日分析任务失败: {e}")
            return {"status": "error", "message": str(e)}

    async def sync_data(self, trade_date: str):
        """同步数据"""
        self.logger.info("同步数据...")

        # 获取当日行情数据
        index_data = market_data_gateway.get_index_quote(trade_date)
        sector_data = market_data_gateway.get_sector_data(trade_date)
        stock_data = market_data_gateway.get_expanded_stock_list_with_meta(
            trade_date,
            top_gainers=100,
        )
        stock_rows = stock_data.get("rows") or []

        self.logger.info(f"数据同步完成: 指数{len(index_data)}, 板块{len(sector_data)}, 个股{len(stock_rows)}")

    async def run_analysis(self, trade_date: str) -> dict:
        """执行分析，返回完整报告数据"""
        self.logger.info("执行市场环境分析...")
        bundle = await decision_flow_service.build_full_decision(
            trade_date,
            top_gainers=200,
        )
        context = bundle.context
        market_env = context.market_env
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
        sector_scan = context.sector_scan
        sector_dict = {
            "mainline_sectors": [s.model_dump() for s in sector_scan.mainline_sectors[:5]],
            "sub_mainline_sectors": [s.model_dump() for s in sector_scan.sub_mainline_sectors[:5]],
            "mainline_count": len(sector_scan.mainline_sectors),
            "sub_mainline_count": len(sector_scan.sub_mainline_sectors)
        }
        self.logger.info(f"主线板块数: {len(sector_scan.mainline_sectors)}")

        stocks = context.stocks
        holdings_list = context.holdings_list
        holdings = context.holdings
        account = context.account

        self.logger.info("执行三池分类...")
        stock_pools = bundle.stock_pools
        pools_dict = {
            "market_watch_pool": [s.model_dump() for s in stock_pools.market_watch_pool[:10]],
            "trend_recognition_pool": [s.model_dump() for s in stock_pools.trend_recognition_pool[:10]],
            "account_executable_pool": [s.model_dump() for s in stock_pools.account_executable_pool[:10]],
            "holding_process_pool": [s.model_dump() for s in stock_pools.holding_process_pool],
            "market_watch_count": len(stock_pools.market_watch_pool),
            "trend_recognition_count": len(stock_pools.trend_recognition_pool),
            "account_executable_count": len(stock_pools.account_executable_pool),
            "holding_process_count": len(stock_pools.holding_process_pool)
        }

        self.logger.info("执行买点分析...")
        buy_analysis = bundle.buy_analysis
        buy_dict = {
            "available_buy_points": [bp.model_dump() for bp in buy_analysis.available_buy_points[:5]],
            "observe_buy_points": [bp.model_dump() for bp in buy_analysis.observe_buy_points[:5]],
            "market_env_tag": buy_analysis.market_env_tag.value
        }

        self.logger.info("执行卖点分析...")
        sell_analysis = bundle.sell_analysis
        pools_dict["holding_process_pool"] = [s.model_dump() for s in stock_pools.holding_process_pool]
        sell_dict = {
            "sell_positions": [sp.model_dump() for sp in sell_analysis.sell_positions],
            "reduce_positions": [sp.model_dump() for sp in sell_analysis.reduce_positions],
            "hold_positions": [sp.model_dump() for sp in sell_analysis.hold_positions]
        }

        self.logger.info("执行账户适配...")
        account_adapt = account_adapter_service.adapt(
            trade_date,
            account,
            holdings,
            market_env=context.market_env,
        )

        # 生成摘要
        summary = self._generate_summary(trade_date, market_env, account_adapt, holdings)
        risk_alerts = self._build_risk_alerts(market_env, account, buy_analysis, holdings)
        snapshot_count = await review_snapshot_service.save_analysis_snapshot_safe(
            trade_date,
            stock_pools,
            buy_analysis,
        )

        return {
            "trade_date": trade_date,
            "market_env": market_env_dict,
            "sector_scan": sector_dict,
            "stock_pools": pools_dict,
            "buy_analysis": buy_dict,
            "sell_analysis": sell_dict,
            "account_fit": account_adapt.model_dump(),
            "summary": summary,
            "risk_alerts": risk_alerts,
            "review_snapshot_count": snapshot_count,
        }

    async def refresh_review_outcomes_for_scheduler(self, limit_days: int = 20) -> int:
        """由调度器低速补齐复盘收益，避免页面访问触发高频详情查询。"""
        total_updated = 0
        for _ in range(self.REVIEW_OUTCOME_REFRESH_MAX_PASSES):
            updated = await review_snapshot_service.refresh_snapshot_outcomes(
                limit_days=limit_days,
                max_rows=self.REVIEW_OUTCOME_REFRESH_BATCH_ROWS,
            )
            total_updated += updated
            if updated < self.REVIEW_OUTCOME_REFRESH_BATCH_ROWS:
                break
            await asyncio.sleep(self.REVIEW_OUTCOME_REFRESH_SLEEP_SECONDS)
        return total_updated

    def _build_risk_alerts(self, market_env, account: AccountInput, buy_analysis, holdings) -> list:
        """构建风控提醒。"""
        alerts = []
        if market_env.market_env_tag.value == "防守" and account.today_new_buy_count >= 2:
            alerts.append("市场防守期仍频繁开仓，建议降频")
        if market_env.market_env_tag.value == "防守" and len(buy_analysis.available_buy_points) > 0:
            alerts.append("弱市仍出现可买信号，请提高买点门槛")
        if account.today_new_buy_count >= 3:
            alerts.append("当日开仓次数偏高，注意节奏风险")
        if any(h.pnl_pct < -3 for h in holdings) and account.total_position_ratio >= 0.5:
            alerts.append("弱票未充分处理前不宜继续加新仓")
        return alerts

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

    async def enqueue_task(
        self,
        mode: str,
        trade_date: str | None = None,
        *,
        trigger_source: str = "manual",
        force: bool = False,
    ) -> dict:
        """创建任务运行记录并执行幂等判定。"""
        resolved_trade_date = trade_date or datetime.now().strftime("%Y-%m-%d")
        created = await task_run_service.create_task_run(
            mode,
            resolved_trade_date,
            trigger_source=trigger_source,
            max_attempts=self.TASK_RETRY_LIMITS.get(mode, 1),
            force=force,
        )
        run = created["run"]
        return {
            "created": bool(created["created"]),
            "reason": created["reason"],
            "task_id": run["id"],
            "trade_date": run["trade_date"],
            "mode": run["mode"],
            "status": run["status"],
        }

    async def execute_task_run(self, task_id: str) -> dict:
        """执行已登记任务，带重试和状态更新。"""
        run = await task_run_service.get_task_run(task_id)
        if run is None:
            raise ValueError(f"任务不存在: {task_id}")

        if run["status"] == "success":
            return {"status": "success", "task_id": task_id, "deduplicated": True, "result": run.get("result")}

        last_error = ""
        started_at = None
        for attempt in range(1, run["max_attempts"] + 1):
            started_at = datetime.utcnow()
            await task_run_service.mark_running(task_id, attempt)
            self.logger.info(f"开始执行任务 {task_id}: mode={run['mode']} trade_date={run['trade_date']} attempt={attempt}/{run['max_attempts']}")
            try:
                result = await self._execute_mode(run["mode"], run["trade_date"])
                await task_run_service.mark_success(task_id, result, started_at)
                self.logger.info(f"任务执行成功 {task_id}: mode={run['mode']} trade_date={run['trade_date']}")
                return {"status": "success", "task_id": task_id, "result": result}
            except Exception as exc:
                last_error = str(exc)
                self.logger.warning(
                    f"任务执行失败 {task_id}: mode={run['mode']} trade_date={run['trade_date']} attempt={attempt}/{run['max_attempts']} error={last_error}"
                )
                if attempt < run["max_attempts"]:
                    await task_run_service.mark_retrying(task_id, attempt, last_error)
                    await asyncio.sleep(self.RETRY_DELAY_SECONDS)
                else:
                    await task_run_service.mark_failed(task_id, last_error, started_at, attempt)
                    raise

        raise RuntimeError(last_error or "任务执行失败")

    async def get_task_status(self, task_id: str | None = None, limit: int = 20) -> dict:
        """返回任务运行状态。"""
        if task_id:
            run = await task_run_service.get_task_run(task_id)
            if run is None:
                return {"status": "missing", "task": None}
            return {"status": "ok", "task": run}
        runs = await task_run_service.list_task_runs(limit=limit)
        return {"status": "ok", "tasks": runs}

    async def _execute_mode(self, mode: str, trade_date: str) -> dict:
        if mode == "daily":
            report = await self._run_daily_pipeline(trade_date)
            return {"trade_date": trade_date, "pipeline": "daily", "report": report}
        if mode == "sync":
            await self.sync_data(trade_date)
            return {"trade_date": trade_date, "pipeline": "sync"}
        if mode == "analyze":
            report = await self.run_analysis(trade_date)
            return {"trade_date": trade_date, "pipeline": "analyze", "report": report}
        if mode == "notify":
            report = await self.run_analysis(trade_date)
            await self.notify_report(trade_date, report)
            return {"trade_date": trade_date, "pipeline": "notify"}
        raise ValueError(f"不支持的任务模式: {mode}")

    async def _run_daily_pipeline(self, trade_date: str) -> dict:
        await self.sync_data(trade_date)
        report_data = await self.run_analysis(trade_date)
        try:
            refreshed_outcomes = await self.refresh_review_outcomes_for_scheduler()
            report_data["review_outcome_refresh_count"] = refreshed_outcomes
        except Exception as exc:
            self.logger.warning(f"调度器补齐复盘收益失败: {exc}")
            report_data["review_outcome_refresh_count"] = 0
        await self.notify_report(trade_date, report_data)
        return report_data


# 全局调度器实例
scheduler = TaskScheduler()


# 如果直接运行
if __name__ == "__main__":
    import sys
    trade_date = sys.argv[1] if len(sys.argv) > 1 else None
    result = asyncio.run(scheduler.run_daily_analysis(trade_date))
    print(result)
