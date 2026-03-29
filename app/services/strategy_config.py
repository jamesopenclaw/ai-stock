"""
规则策略配置对象
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class StockFilterStrategyConfig:
    hard_filter_rule_labels: Dict[str, str] = field(
        default_factory=lambda: {
            "not_pure_emotion_small_cap": "不是纯情绪小票",
            "not_hot_but_weak_logic": "不是高换手高波动但逻辑弱",
            "not_weaker_than_group": "不是趋势明显弱于同组其他票",
            "not_chase_only_tomorrow": "不是次日大概率只能追高",
            "not_account_style_conflict": "不是账户风格冲突票",
        }
    )
    hard_filter_fail_labels: Dict[str, str] = field(
        default_factory=lambda: {
            "not_pure_emotion_small_cap": "偏纯情绪小票",
            "not_hot_but_weak_logic": "高换手高波动但逻辑偏弱",
            "not_weaker_than_group": "趋势明显弱于同组更强票",
            "not_chase_only_tomorrow": "次日大概率只能追高或缺少舒服买点",
            "not_account_style_conflict": "账户条件或风格不匹配",
        }
    )
    strong_change_threshold: float = 7.0
    medium_change_threshold: float = 3.0
    strong_score_confirm: float = 85.0
    medium_score_threshold: float = 55.0
    high_turnover: float = 15.0
    medium_turnover: float = 8.0
    min_amount: float = 30000.0
    min_close_price: float = 2.0
    watch_pool_min_score: float = 55.0
    defense_trial_min_score: float = 85.0
    pure_emotion_amount_max: float = 100000.0
    high_volatility_pct: float = 8.0
    market_watch_limit: int = 3
    trend_recognition_limit: int = 6
    account_executable_limit: int = 5
    sector_representative_limit: int = 4


@dataclass(frozen=True)
class BuyPointStrategyConfig:
    max_available: int = 10
    max_observe: int = 10
    max_not_buy: int = 10


@dataclass(frozen=True)
class SellPointStrategyConfig:
    stop_loss_pct: float = -5.0
    stop_loss_pct_strict: float = -3.0
    stop_profit_pct: float = 15.0
    stop_profit_pct_tight: float = 10.0
    reduce_pct: float = 8.0


DEFAULT_STOCK_FILTER_STRATEGY = StockFilterStrategyConfig()
DEFAULT_BUY_POINT_STRATEGY = BuyPointStrategyConfig()
DEFAULT_SELL_POINT_STRATEGY = SellPointStrategyConfig()
