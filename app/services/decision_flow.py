"""
决策编排服务
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.models.schemas import BuyPointResponse, SellPointResponse, StockPoolsOutput, StockOutput
from app.services.buy_point import buy_point_service
from app.services.decision_context import DecisionContext, decision_context_service
from app.services.review_snapshot import review_snapshot_service
from app.services.sell_point import sell_point_service
from app.services.stock_filter import stock_filter_service


@dataclass
class CandidateAnalysisBundle:
    """候选股侧分析编排结果。"""

    context: DecisionContext
    review_bias_profile: Dict
    scored_stocks: List[StockOutput]
    stock_pools: StockPoolsOutput


@dataclass
class FullDecisionBundle(CandidateAnalysisBundle):
    """完整决策编排结果。"""

    buy_analysis: BuyPointResponse
    sell_analysis: SellPointResponse


class DecisionFlowService:
    """复用决策主链路的编排逻辑，避免路由层重复拼装。"""

    async def build_candidate_analysis(
        self,
        trade_date: str,
        *,
        top_gainers: int,
        include_holdings: bool,
    ) -> CandidateAnalysisBundle:
        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=top_gainers,
            include_holdings=include_holdings,
        )
        review_bias_profile = await review_snapshot_service.get_review_bias_profile_safe(
            limit_days=10
        )
        scored_stocks = stock_filter_service.filter_with_context(
            trade_date,
            context.stocks,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
            account=context.account,
            holdings=context.holdings_list,
        )
        stock_pools = stock_filter_service.classify_pools(
            trade_date,
            context.stocks,
            context.holdings_list,
            context.account,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
            scored_stocks=scored_stocks,
            review_bias_profile=review_bias_profile,
        )
        return CandidateAnalysisBundle(
            context=context,
            review_bias_profile=review_bias_profile,
            scored_stocks=scored_stocks,
            stock_pools=stock_pools,
        )

    async def build_full_decision(
        self,
        trade_date: str,
        *,
        top_gainers: int = 200,
    ) -> FullDecisionBundle:
        candidate_bundle = await self.build_candidate_analysis(
            trade_date,
            top_gainers=top_gainers,
            include_holdings=True,
        )
        buy_analysis = buy_point_service.analyze(
            trade_date,
            candidate_bundle.context.stocks,
            candidate_bundle.context.account,
            market_env=candidate_bundle.context.market_env,
            sector_scan=candidate_bundle.context.sector_scan,
            scored_stocks=candidate_bundle.scored_stocks,
            stock_pools=candidate_bundle.stock_pools,
            review_bias_profile=candidate_bundle.review_bias_profile,
        )
        sell_analysis = sell_point_service.analyze(
            trade_date,
            candidate_bundle.context.holdings,
            market_env=candidate_bundle.context.market_env,
            sector_scan=candidate_bundle.context.sector_scan,
        )
        stock_pools = stock_filter_service.attach_sell_analysis(
            candidate_bundle.stock_pools,
            sell_analysis,
        )
        return FullDecisionBundle(
            context=candidate_bundle.context,
            review_bias_profile=candidate_bundle.review_bias_profile,
            scored_stocks=candidate_bundle.scored_stocks,
            stock_pools=stock_pools,
            buy_analysis=buy_analysis,
            sell_analysis=sell_analysis,
        )


decision_flow_service = DecisionFlowService()
