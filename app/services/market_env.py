"""
市场环境分析服务
"""
from typing import Dict, Optional
from collections import Counter
from loguru import logger

from app.models.schemas import (
    MarketEnvInput,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    IndexQuote
)
from app.services.market_data_gateway import market_data_gateway


class MarketEnvService:
    """市场环境分析服务"""

    # 评分阈值配置
    INDEX_SCORE_WEIGHT = 0.4  # 指数评分权重
    SENTIMENT_SCORE_WEIGHT = 0.6  # 情绪评分权重

    # 指数评分阈值
    INDEX_EXCELLENT = 2.0  # 指数涨幅 > 2%
    INDEX_GOOD = 0.5       # 指数涨幅 > 0.5%
    INDEX_BAD = -0.5      # 指数跌幅 > -0.5%

    # 情绪评分阈值
    SENTIMENT_EXCELLENT = 80  # 情绪评分 > 80
    SENTIMENT_GOOD = 60      # 情绪评分 > 60
    SENTIMENT_BAD = 40       # 情绪评分 < 40

    def __init__(self):
        self.client = market_data_gateway

    def analyze(self, market_data: MarketEnvInput) -> MarketEnvOutput:
        """
        分析市场环境

        Args:
            market_data: 市场环境输入数据

        Returns:
            市场环境分析结果
        """
        # 计算各项评分
        index_score = self._calculate_index_score(market_data)
        sentiment_score = self._calculate_sentiment_score(market_data)
        overall_score = index_score * self.INDEX_SCORE_WEIGHT + sentiment_score * self.SENTIMENT_SCORE_WEIGHT

        # 判断环境标签
        market_env_tag = self._determine_env_tag(overall_score)
        breakout_allowed = self._determine_breakout_allowed(market_env_tag, market_data)
        risk_level = self._determine_risk_level(overall_score)
        market_comment = self._generate_comment(market_env_tag, index_score, sentiment_score, market_data)

        return MarketEnvOutput(
            trade_date=market_data.trade_date,
            market_env_tag=market_env_tag,
            breakout_allowed=breakout_allowed,
            risk_level=risk_level,
            market_comment=market_comment,
            index_score=index_score,
            sentiment_score=sentiment_score,
            overall_score=overall_score
        )

    def get_current_env(self, trade_date: str) -> MarketEnvOutput:
        """
        获取当前市场环境（从 Tushare 拉取数据）

        Args:
            trade_date: 交易日

        Returns:
            当前市场环境
        """
        compact_trade_date = trade_date.replace("-", "")

        index_payload = self.client.get_index_quote_with_meta(compact_trade_date)
        limit_payload = self.client.get_limit_stats_with_meta(compact_trade_date)
        turnover_payload = self.client.get_market_turnover_with_meta(compact_trade_date)
        up_down_payload = self.client.get_up_down_ratio_with_meta(compact_trade_date)

        index_quotes = index_payload.get("rows", [])
        limit_stats = limit_payload.get("stats", {})
        market_turnover = turnover_payload.get("market_turnover", 0)
        up_down_ratio = up_down_payload.get("up_down_ratio", {})

        resolved_candidates = [
            str(index_payload.get("data_trade_date") or ""),
            str(limit_payload.get("data_trade_date") or ""),
            str(turnover_payload.get("data_trade_date") or ""),
            str(up_down_payload.get("data_trade_date") or ""),
        ]
        resolved_candidates = [d for d in resolved_candidates if d]
        resolved_trade_date = compact_trade_date
        if resolved_candidates:
            resolved_trade_date = Counter(resolved_candidates).most_common(1)[0][0]

        # 构建输入数据
        index_sh = index_quotes[0]["change_pct"] if len(index_quotes) > 0 else 0
        index_sz = index_quotes[1]["change_pct"] if len(index_quotes) > 1 else 0
        index_cyb = index_quotes[2]["change_pct"] if len(index_quotes) > 2 else 0

        market_data = MarketEnvInput(
            trade_date=f"{resolved_trade_date[:4]}-{resolved_trade_date[4:6]}-{resolved_trade_date[6:8]}",
            index_sh=index_sh,
            index_sz=index_sz,
            index_cyb=index_cyb,
            up_down_ratio=up_down_ratio,
            limit_up_count=limit_stats.get("limit_up_count", 0),
            limit_down_count=limit_stats.get("limit_down_count", 0),
            broken_board_rate=limit_stats.get("broken_board_rate", 0),
            market_turnover=market_turnover,
            risk_appetite_tag="中性"
        )

        return self.analyze(market_data)

    def _calculate_index_score(self, data: MarketEnvInput) -> float:
        """计算指数评分 (0-100)"""
        scores = []

        # 上证指数评分
        if data.index_sh > self.INDEX_EXCELLENT:
            scores.append(100)
        elif data.index_sh > self.INDEX_GOOD:
            scores.append(70)
        elif data.index_sh > self.INDEX_BAD:
            scores.append(50)
        else:
            scores.append(20)

        # 深成指评分
        if data.index_sz > self.INDEX_EXCELLENT:
            scores.append(100)
        elif data.index_sz > self.INDEX_GOOD:
            scores.append(70)
        elif data.index_sz > self.INDEX_BAD:
            scores.append(50)
        else:
            scores.append(20)

        # 创业板评分
        if data.index_cyb > self.INDEX_EXCELLENT:
            scores.append(100)
        elif data.index_cyb > self.INDEX_GOOD:
            scores.append(70)
        elif data.index_cyb > self.INDEX_BAD:
            scores.append(50)
        else:
            scores.append(20)

        # 计算共振程度（指数同向程度）
        same_direction = sum(1 for s in [data.index_sh, data.index_sz, data.index_cyb] if s * data.index_sh > 0)
        resonance_bonus = same_direction * 10  # 共振加分

        return sum(scores) / len(scores) + resonance_bonus

    def _calculate_sentiment_score(self, data: MarketEnvInput) -> float:
        """计算情绪评分 (0-100)"""
        score = 50  # 基础分

        # 涨跌停评分
        if data.limit_up_count:
            if data.limit_up_count > 50:
                score += 20
            elif data.limit_up_count > 30:
                score += 10
            elif data.limit_up_count < 10:
                score -= 10

        # 跌停评分
        if data.limit_down_count:
            if data.limit_down_count > 20:
                score -= 20
            elif data.limit_down_count > 10:
                score -= 10
            elif data.limit_down_count < 5:
                score += 5

        # 炸板率评分
        if data.broken_board_rate:
            if data.broken_board_rate > 30:
                score -= 15
            elif data.broken_board_rate > 20:
                score -= 10
            elif data.broken_board_rate < 10:
                score += 10

        # 涨跌家数比评分
        if data.up_down_ratio:
            up = data.up_down_ratio.get("up", 0)
            down = data.up_down_ratio.get("down", 1)
            ratio = up / max(down, 1)
            if ratio > 3:
                score += 15
            elif ratio > 2:
                score += 10
            elif ratio > 1:
                score += 5
            elif ratio < 0.5:
                score -= 15
            elif ratio < 0.8:
                score -= 5

        # 成交额评分
        if data.market_turnover:
            if data.market_turnover > 15000:
                score += 10
            elif data.market_turnover > 10000:
                score += 5
            elif data.market_turnover < 6000:
                score -= 10

        return max(0, min(100, score))

    def _determine_env_tag(self, overall_score: float) -> MarketEnvTag:
        """根据综合评分确定环境标签"""
        if overall_score >= 70:
            return MarketEnvTag.ATTACK
        elif overall_score >= 40:
            return MarketEnvTag.NEUTRAL
        else:
            return MarketEnvTag.DEFENSE

    def _determine_breakout_allowed(self, env_tag: MarketEnvTag, data: MarketEnvInput) -> bool:
        """判断是否允许突破型操作"""
        if env_tag == MarketEnvTag.DEFENSE:
            return False

        if env_tag == MarketEnvTag.NEUTRAL:
            # 中性环境下，炸板率高不允许
            if data.broken_board_rate and data.broken_board_rate > 25:
                return False
            return True

        # 进攻环境，检查是否满足进攻条件
        # 涨停数足够、炸板率不高
        if data.limit_up_count and data.limit_up_count > 30:
            if data.broken_board_rate and data.broken_board_rate < 20:
                return True

        return True

    def _determine_risk_level(self, overall_score: float) -> RiskLevel:
        """确定风险等级"""
        if overall_score >= 70:
            return RiskLevel.LOW
        elif overall_score >= 40:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.HIGH

    def _generate_comment(
        self,
        env_tag: MarketEnvTag,
        index_score: float,
        sentiment_score: float,
        data: MarketEnvInput
    ) -> str:
        """生成市场环境简评"""
        comments = []

        # 环境定性
        if env_tag == MarketEnvTag.ATTACK:
            comments.append("市场处于进攻状态，氛围活跃")
        elif env_tag == MarketEnvTag.NEUTRAL:
            comments.append("市场处于中性状态，谨慎操作")
        else:
            comments.append("市场处于防守状态，控制仓位")

        # 指数情况
        avg_change = (data.index_sh + data.index_sz + data.index_cyb) / 3
        if avg_change > 1:
            comments.append("指数共振上涨，强度较高")
        elif avg_change > 0:
            comments.append("指数温和上涨")
        elif avg_change > -1:
            comments.append("指数小幅调整")
        else:
            comments.append("指数明显回落")

        # 情绪情况
        if data.limit_up_count and data.limit_up_count > 40:
            comments.append("涨停家数较多")
        if data.limit_down_count and data.limit_down_count > 15:
            comments.append("跌停家数较多，注意风险")

        # 炸板率
        if data.broken_board_rate and data.broken_board_rate > 25:
            comments.append("炸板率偏高，追高风险大")

        return "，".join(comments)


# 全局服务实例
market_env_service = MarketEnvService()
