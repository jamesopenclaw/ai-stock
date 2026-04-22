"""
市场环境分析服务
"""
import time
from threading import RLock
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
    INDEX_NEUTRAL_BAND = 0.3
    INDEX_SCORE_SENSITIVITY = 18.0
    INDEX_RESONANCE_STRONG_BONUS = 12.0
    INDEX_RESONANCE_WEAK_BONUS = 6.0

    # 情绪评分阈值
    SENTIMENT_EXCELLENT = 80  # 情绪评分 > 80
    SENTIMENT_GOOD = 60      # 情绪评分 > 60
    SENTIMENT_BAD = 40       # 情绪评分 < 40
    MARKET_ENV_CACHE_TTL_SECONDS = 5 * 60
    REALTIME_MARKET_ENV_CACHE_TTL_SECONDS = 30

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @classmethod
    def _lerp(cls, value: float, left: float, right: float, out_left: float, out_right: float) -> float:
        if right == left:
            return out_right
        ratio = (value - left) / (right - left)
        return out_left + ratio * (out_right - out_left)

    @staticmethod
    def _normalize_market_turnover(value: Optional[float]) -> float:
        """Normalize nullable turnover payloads before building the Pydantic model."""
        return float(value or 0.0)

    def __init__(self):
        self.client = market_data_gateway
        self._env_cache = {}
        self._env_cache_lock = RLock()

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
        market_env_profile = self._determine_env_profile(
            market_env_tag=market_env_tag,
            overall_score=overall_score,
            index_score=index_score,
            sentiment_score=sentiment_score,
            data=market_data,
        )
        breakout_allowed = self._determine_breakout_allowed(market_env_tag, market_data)
        risk_level = self._determine_risk_level(overall_score)
        market_comment = self._generate_comment(market_env_tag, index_score, sentiment_score, market_data)
        market_headline = self._generate_market_headline(market_env_profile)
        dominant_factor_label = self._determine_dominant_factor_label(index_score, sentiment_score, market_data)
        market_subheadline = f"{dominant_factor_label}，综合分 {overall_score:.1f}"
        trading_tempo_label = self._determine_trading_tempo_label(market_env_profile, breakout_allowed)

        return MarketEnvOutput(
            trade_date=market_data.trade_date,
            market_env_tag=market_env_tag,
            market_env_profile=market_env_profile,
            breakout_allowed=breakout_allowed,
            risk_level=risk_level,
            market_comment=market_comment,
            market_headline=market_headline,
            market_subheadline=market_subheadline,
            trading_tempo_label=trading_tempo_label,
            dominant_factor_label=dominant_factor_label,
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
        effective_trade_date = compact_trade_date
        if not self.client.should_use_market_snapshot(compact_trade_date):
            effective_trade_date = str(
                self.client.get_last_completed_trade_date(compact_trade_date)
            ).replace("-", "")[:8] or compact_trade_date

        cached = self._get_cached_env(compact_trade_date)
        if cached:
            return cached

        request_trade_date = (
            compact_trade_date
            if self.client.should_use_market_snapshot(compact_trade_date)
            else effective_trade_date
        )

        index_payload = self.client.get_index_quote_with_meta(request_trade_date)
        limit_payload = self.client.get_limit_stats_with_meta(request_trade_date)
        turnover_payload = self.client.get_market_turnover_with_meta(request_trade_date)
        up_down_payload = self.client.get_up_down_ratio_with_meta(request_trade_date)

        if any(
            payload.get("status") == "unavailable"
            for payload in (limit_payload, turnover_payload, up_down_payload)
        ):
            fallback_trade_date = str(self.client.get_last_completed_trade_date(compact_trade_date)).replace("-", "")[:8]
            if fallback_trade_date and fallback_trade_date != compact_trade_date:
                return self.get_current_env(
                    f"{fallback_trade_date[:4]}-{fallback_trade_date[4:6]}-{fallback_trade_date[6:8]}"
                )

        index_quotes = index_payload.get("rows", [])
        limit_stats = limit_payload.get("stats", {})
        market_turnover = self._normalize_market_turnover(turnover_payload.get("market_turnover"))
        up_down_ratio = up_down_payload.get("up_down_ratio", {})

        resolved_candidates = [
            str(index_payload.get("data_trade_date") or ""),
            str(limit_payload.get("data_trade_date") or ""),
            str(turnover_payload.get("data_trade_date") or ""),
            str(up_down_payload.get("data_trade_date") or ""),
        ]
        resolved_candidates = [d for d in resolved_candidates if d]
        resolved_trade_date = effective_trade_date
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

        result = self.analyze(market_data)
        self._cache_env(compact_trade_date, resolved_trade_date, result)
        return result

    def _cache_ttl_seconds(self, compact_trade_date: str, resolved_trade_date: str) -> int:
        if (
            compact_trade_date == self.client.now_trade_date().replace("-", "")
            and self.client.should_use_market_snapshot(compact_trade_date)
        ):
            return self.REALTIME_MARKET_ENV_CACHE_TTL_SECONDS
        if compact_trade_date != resolved_trade_date:
            return self.MARKET_ENV_CACHE_TTL_SECONDS
        return self.MARKET_ENV_CACHE_TTL_SECONDS

    def _get_cached_env(self, compact_trade_date: str) -> Optional[MarketEnvOutput]:
        now_ts = time.monotonic()
        with self._env_cache_lock:
            cached = self._env_cache.get(compact_trade_date)
            if not cached:
                return None
            if now_ts - float(cached.get("fetched_at") or 0) > float(cached.get("ttl") or 0):
                self._env_cache.pop(compact_trade_date, None)
                return None
            return cached.get("value")

    def _cache_env(self, compact_trade_date: str, resolved_trade_date: str, result: MarketEnvOutput) -> None:
        now_ts = time.monotonic()
        ttl = self._cache_ttl_seconds(compact_trade_date, resolved_trade_date)
        entry = {
            "fetched_at": now_ts,
            "ttl": ttl,
            "value": result,
        }
        alias_keys = {compact_trade_date}
        if resolved_trade_date:
            alias_keys.add(str(resolved_trade_date).replace("-", "")[:8])
        with self._env_cache_lock:
            for key in alias_keys:
                if key:
                    self._env_cache[key] = entry

    def _calculate_index_score(self, data: MarketEnvInput) -> float:
        """计算指数评分 (0-100)"""
        index_changes = [data.index_sh, data.index_sz, data.index_cyb]
        base_score = sum(self._score_single_index(change_pct) for change_pct in index_changes) / len(index_changes)
        resonance_adjustment = self._calculate_index_resonance_adjustment(index_changes)
        return max(0, min(100, base_score + resonance_adjustment))

    def _score_single_index(self, change_pct: float) -> float:
        """
        将单个指数涨跌幅映射到连续分值。

        0% 附近保持中性分，随涨跌幅线性扩张；大跌时快速压低分数，
        避免过去“普跌也能因为同向而加分”的问题。
        """
        return max(5.0, min(95.0, 50.0 + change_pct * self.INDEX_SCORE_SENSITIVITY))

    def _calculate_index_resonance_adjustment(self, index_changes) -> float:
        """指数共振只在同向上涨时加分，同向下跌时减分。"""
        positive_count = sum(1 for change in index_changes if change > self.INDEX_NEUTRAL_BAND)
        negative_count = sum(1 for change in index_changes if change < -self.INDEX_NEUTRAL_BAND)

        if positive_count == len(index_changes):
            return self.INDEX_RESONANCE_STRONG_BONUS
        if negative_count == len(index_changes):
            return -self.INDEX_RESONANCE_STRONG_BONUS
        if positive_count >= 2 and negative_count == 0:
            return self.INDEX_RESONANCE_WEAK_BONUS
        if negative_count >= 2 and positive_count == 0:
            return -self.INDEX_RESONANCE_WEAK_BONUS
        return 0.0

    def _calculate_sentiment_score(self, data: MarketEnvInput) -> float:
        """计算情绪评分 (0-100)"""
        breadth_score = self._calculate_breadth_score(data)
        speculative_score = self._calculate_speculative_score(data)
        liquidity_score = self._calculate_liquidity_score(data)

        score = 50 + breadth_score + speculative_score + liquidity_score

        if (
            (data.limit_up_count or 0) >= 60
            and (data.limit_down_count or 0) <= 5
            and (data.broken_board_rate or 0) <= 12
        ):
            score += 3

        if (
            (data.limit_down_count or 0) >= 20
            and (data.broken_board_rate or 0) >= 30
        ):
            score -= 3

        return self._clamp(score, 0, 100)

    def _calculate_breadth_score(self, data: MarketEnvInput) -> float:
        up = (data.up_down_ratio or {}).get("up", 0)
        down = (data.up_down_ratio or {}).get("down", 0)
        ratio = up / max(down, 1)

        if ratio >= 2.5:
            return self._clamp(10.0 + (ratio - 2.5) * 2.0, 10.0, 14.0)
        if ratio >= 1.0:
            return self._lerp(ratio, 1.0, 2.5, 0.0, 10.0)
        if ratio >= 0.5:
            return self._lerp(ratio, 0.5, 1.0, -8.0, 0.0)
        return self._clamp(-8.0 - (0.5 - ratio) * 16.0, -16.0, -8.0)

    def _calculate_speculative_score(self, data: MarketEnvInput) -> float:
        limit_up = float(data.limit_up_count or 0)
        limit_down = float(data.limit_down_count or 0)
        broken_board_rate = float(data.broken_board_rate or 0)

        limit_up_score = self._clamp((limit_up - 15.0) * 0.22, -8.0, 14.0)
        limit_down_penalty = self._clamp((limit_down - 3.0) * 0.5, 0.0, 16.0)

        if broken_board_rate <= 8:
            broken_board_score = 6.0
        elif broken_board_rate <= 15:
            broken_board_score = self._lerp(broken_board_rate, 8.0, 15.0, 6.0, 2.0)
        elif broken_board_rate <= 25:
            broken_board_score = self._lerp(broken_board_rate, 15.0, 25.0, 2.0, -6.0)
        elif broken_board_rate <= 40:
            broken_board_score = self._lerp(broken_board_rate, 25.0, 40.0, -6.0, -12.0)
        else:
            broken_board_score = self._clamp(
                self._lerp(broken_board_rate, 40.0, 60.0, -12.0, -18.0),
                -18.0,
                -12.0,
            )

        return limit_up_score - limit_down_penalty + broken_board_score

    def _calculate_liquidity_score(self, data: MarketEnvInput) -> float:
        turnover = float(data.market_turnover or 0)
        if turnover <= 0:
            return 0.0
        if turnover < 5000:
            return self._lerp(turnover, 0.0, 5000.0, -8.0, -4.0)
        if turnover < 7000:
            return self._lerp(turnover, 5000.0, 7000.0, -4.0, -1.0)
        if turnover < 12000:
            return self._lerp(turnover, 7000.0, 12000.0, -1.0, 1.0)
        if turnover < 18000:
            return self._lerp(turnover, 12000.0, 18000.0, 1.0, 5.0)
        return self._clamp(self._lerp(turnover, 18000.0, 25000.0, 5.0, 7.0), 5.0, 7.0)

    def _determine_env_tag(self, overall_score: float) -> MarketEnvTag:
        """根据综合评分确定环境标签"""
        if overall_score >= 70:
            return MarketEnvTag.ATTACK
        elif overall_score >= 40:
            return MarketEnvTag.NEUTRAL
        else:
            return MarketEnvTag.DEFENSE

    def _determine_env_profile(
        self,
        market_env_tag: MarketEnvTag,
        overall_score: float,
        index_score: float,
        sentiment_score: float,
        data: MarketEnvInput,
    ) -> str:
        breadth_ratio = self._breadth_ratio(data)
        speculative_state = self._speculative_state(data)
        avg_change = (data.index_sh + data.index_sz + data.index_cyb) / 3

        if market_env_tag == MarketEnvTag.ATTACK:
            if overall_score >= 82:
                return "强进攻"
            return "进攻"

        if market_env_tag == MarketEnvTag.DEFENSE:
            if overall_score < 30:
                return "强防守"
            return "防守"

        if overall_score >= 55:
            return "中性偏强"
        if avg_change < -0.2 and breadth_ratio > 1.2 and speculative_state == "weak":
            return "中性偏谨慎"
        if speculative_state == "weak" or overall_score < 45:
            return "弱中性"
        if sentiment_score - index_score >= 8:
            return "情绪修复"
        return "中性"

    def _determine_breakout_allowed(self, env_tag: MarketEnvTag, data: MarketEnvInput) -> bool:
        """判断是否允许突破型操作"""
        up = (data.up_down_ratio or {}).get("up", 0)
        down = (data.up_down_ratio or {}).get("down", 0)
        breadth_ratio = up / max(down, 1)

        if env_tag == MarketEnvTag.DEFENSE:
            return False

        if env_tag == MarketEnvTag.NEUTRAL:
            if data.broken_board_rate and data.broken_board_rate > 20:
                return False
            if data.limit_down_count and data.limit_down_count > 12:
                return False
            if breadth_ratio < 1.0:
                return False
            return True

        if data.broken_board_rate and data.broken_board_rate > 25:
            return False
        if data.limit_up_count and data.limit_up_count < 30:
            return False
        if breadth_ratio < 1.0:
            return False
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
        lead = self._comment_lead(env_tag, data)
        reasons = self._comment_reasons(data, index_score, sentiment_score)
        action = self._comment_action_hint(env_tag, data)

        parts = [lead]
        if reasons:
            parts.append(reasons)
        if action:
            parts.append(action)
        return "；".join(parts)

    def _generate_market_headline(self, profile: str) -> str:
        mapping = {
            "强进攻": "可以积极围绕主线做强更强",
            "进攻": "可以做确认后的主动进攻",
            "中性偏强": "可以盯主线，但先等确认再上",
            "中性偏谨慎": "可以盯盘，但优先低吸和回踩确认",
            "弱中性": "少追价，只看最强分歧转强",
            "情绪修复": "情绪有修复，但先别急着扩仓",
            "防守": "先守住回撤，再等下一次舒服机会",
            "强防守": "先控仓位，今天不适合主动进攻",
            "中性": "可以盯盘，但别急着抢第一笔",
        }
        return mapping.get(profile, "可以盯盘，但别急着抢第一笔")

    def _determine_trading_tempo_label(self, profile: str, breakout_allowed: bool) -> str:
        if profile in {"强进攻", "进攻"}:
            return "可盯确认突破" if breakout_allowed else "只做主线确认"
        if profile == "中性偏强":
            return "主线确认后参与"
        if profile in {"中性偏谨慎", "弱中性", "情绪修复"}:
            return "观望低吸"
        if profile in {"防守", "强防守"}:
            return "暂停主动出击"
        return "暂停追突破" if not breakout_allowed else "等待确认"

    def _determine_dominant_factor_label(self, index_score: float, sentiment_score: float, data: MarketEnvInput) -> str:
        breadth_ratio = self._breadth_ratio(data)
        if breadth_ratio > 1.3 and self._speculative_state(data) == "weak":
            return "广度强于接力"
        delta = abs(index_score - sentiment_score)
        if delta < 6:
            return "指数与情绪接近均衡"
        if sentiment_score > index_score:
            return "情绪端主导"
        return "指数端主导"

    def _comment_lead(self, env_tag: MarketEnvTag, data: MarketEnvInput) -> str:
        avg_change = (data.index_sh + data.index_sz + data.index_cyb) / 3
        breadth_ratio = self._breadth_ratio(data)
        speculative_state = self._speculative_state(data)
        if env_tag == MarketEnvTag.ATTACK:
            if avg_change > 1.0:
                return "市场偏进攻，指数与情绪基本同向走强"
            return "市场偏进攻，但强度主要来自情绪侧"
        if env_tag == MarketEnvTag.DEFENSE:
            if avg_change < -1.0:
                return "市场偏防守，指数端已经明显转弱"
            return "市场偏防守，情绪端承接不足"
        if avg_change < -0.2 and breadth_ratio > 1.3 and speculative_state == "weak":
            return "市场中性偏谨慎，指数偏弱但个股仍有活跃度"
        if avg_change < -0.5:
            return "市场中性偏弱，先按分歧市看待"
        if breadth_ratio > 1.5 and speculative_state == "weak":
            return "市场中性偏谨慎，广度尚可但接力质量一般"
        if avg_change > 0.5:
            return "市场中性偏强，但还没强到可以无脑追价"
        return "市场中性，指数和情绪都没有形成明显主导"

    def _comment_reasons(self, data: MarketEnvInput, index_score: float, sentiment_score: float) -> str:
        reasons = []
        avg_change = (data.index_sh + data.index_sz + data.index_cyb) / 3
        breadth_ratio = self._breadth_ratio(data)
        speculative_state = self._speculative_state(data)

        if avg_change > 1.0:
            reasons.append("三大指数同步上行")
        elif avg_change > 0.3:
            reasons.append("指数端维持温和走强")
        elif avg_change < -1.0:
            reasons.append("三大指数同步走弱")
        elif avg_change < -0.3:
            reasons.append("指数端处于回落状态")

        if data.limit_up_count >= 50 and (data.broken_board_rate or 0) < 15:
            reasons.append(f"涨停 {data.limit_up_count} 家且炸板率仅 {data.broken_board_rate:.1f}%")
        elif speculative_state == "weak":
            reasons.append(
                f"炸板率 {data.broken_board_rate:.1f}% 且跌停 {data.limit_down_count} 家，高位接力承压"
            )
        elif data.limit_up_count >= 30:
            reasons.append(f"涨停维持在 {data.limit_up_count} 家，题材仍有活跃度")

        if breadth_ratio > 1.8:
            reasons.append(f"涨跌家数比 {breadth_ratio:.2f}，个股广度明显占优")
        elif breadth_ratio > 1.2:
            reasons.append(f"涨跌家数比 {breadth_ratio:.2f}，多数个股仍有赚钱效应")
        elif breadth_ratio < 0.8:
            reasons.append(f"涨跌家数比 {breadth_ratio:.2f}，个股普遍偏弱")

        if data.market_turnover >= 15000:
            reasons.append(f"成交额 {data.market_turnover / 10000:.1f} 万亿，流动性充足")
        elif data.market_turnover and data.market_turnover < 7000:
            reasons.append(f"成交额 {data.market_turnover / 10000:.1f} 万亿，量能偏弱")

        if not reasons:
            dominant = "指数" if index_score >= sentiment_score else "情绪"
            reasons.append(f"{dominant}侧暂无明显失真，但强弱差距不大")

        return "，".join(reasons[:3])

    def _comment_action_hint(self, env_tag: MarketEnvTag, data: MarketEnvInput) -> str:
        breadth_ratio = self._breadth_ratio(data)

        if env_tag == MarketEnvTag.ATTACK:
            if (data.broken_board_rate or 0) > 20:
                return "可以做强势确认，但别在高炸板率环境里追最后一笔"
            return "允许做强势突破，优先主线和强更强，不做后排跟风"
        if env_tag == MarketEnvTag.DEFENSE:
            if breadth_ratio < 0.8:
                return "先收缩仓位，少做突破，多看反抽减仓和低风险承接"
            return "控制仓位，只有回踩承接清晰时才考虑试错"

        if (data.broken_board_rate or 0) > 20 or breadth_ratio < 1.0:
            return "先等确认，不抢突破，优先做更舒服的回踩或分歧转强"
        return "可以小仓位参与确认型机会，但不适合激进追价"

    def _breadth_ratio(self, data: MarketEnvInput) -> float:
        up = (data.up_down_ratio or {}).get("up", 0)
        down = (data.up_down_ratio or {}).get("down", 0)
        return up / max(down, 1)

    def _speculative_state(self, data: MarketEnvInput) -> str:
        broken_board_rate = float(data.broken_board_rate or 0)
        limit_down_count = int(data.limit_down_count or 0)
        limit_up_count = int(data.limit_up_count or 0)

        if broken_board_rate >= 30 or limit_down_count >= 15:
            return "weak"
        if broken_board_rate <= 15 and limit_up_count >= 50 and limit_down_count <= 5:
            return "strong"
        return "neutral"


# 全局服务实例
market_env_service = MarketEnvService()
