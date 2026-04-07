"""
数据模型 - Pydantic schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


class MarketEnvTag(str, Enum):
    """市场环境标签"""
    ATTACK = "进攻"  # 进攻
    NEUTRAL = "中性"  # 中性
    DEFENSE = "防守"  # 防守


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"


class SectorMainlineTag(str, Enum):
    """板块主线标签"""
    MAINLINE = "主线"  # 主线
    SUB_MAINLINE = "次主线"  # 次主线
    FOLLOW = "跟风"  # 跟风
    TRASH = "杂毛"  # 杂毛


class SectorContinuityTag(str, Enum):
    """板块连续性标签"""
    SUSTAINABLE = "可持续"  # 可持续
    OBSERVABLE = "可观察"  # 可观察
    CAUTION = "末端谨慎"  # 末端谨慎


class SectorTradeabilityTag(str, Enum):
    """板块交易性标签"""
    TRADABLE = "可交易"  # 可交易
    CAUTION = "谨慎"  # 谨慎
    NOT_RECOMMENDED = "不建议"  # 不建议


class SectorTierTag(str, Enum):
    """板块交易分级"""
    A = "A"
    B = "B"
    C = "C"


class SectorActionHint(str, Enum):
    """板块执行建议"""
    EXECUTABLE = "可执行"
    OBSERVE = "只观察"
    AVOID = "不碰"


class SectorRotationTag(str, Enum):
    """板块方向状态"""
    STRENGTHENING = "强化中"
    ROTATING = "切换中"
    STABLE = "稳定主线"
    WEAKENING = "衰减中"
    NEUTRAL = "中性"


# ========== 市场环境相关 ==========

class MarketEnvInput(BaseModel):
    """市场环境输入"""
    trade_date: str = Field(..., description="交易日，格式YYYY-MM-DD")
    index_sh: float = Field(..., description="上证指数涨跌幅(%)")
    index_sz: float = Field(..., description="深成指涨跌幅(%)")
    index_cyb: float = Field(..., description="创业板涨跌幅(%)")
    up_down_ratio: Optional[dict] = Field(None, description="涨跌家数对比")
    limit_up_count: Optional[int] = Field(None, description="涨停数量")
    limit_down_count: Optional[int] = Field(None, description="跌停数量")
    broken_board_rate: Optional[float] = Field(None, description="炸板率(%)")
    market_turnover: float = Field(..., description="两市成交额(亿元)")
    risk_appetite_tag: str = Field(default="中性", description="风险偏好标签")
    sentiment_comment: Optional[str] = Field(None, description="情绪备注")


class MarketEnvOutput(BaseModel):
    """市场环境输出"""
    trade_date: str
    market_env_tag: MarketEnvTag
    market_env_profile: str = Field("", description="市场环境细分状态")
    breakout_allowed: bool
    risk_level: RiskLevel
    market_comment: str
    market_headline: str = Field("", description="市场环境主标题")
    market_subheadline: str = Field("", description="市场环境副标题")
    trading_tempo_label: str = Field("", description="交易节奏标签")
    dominant_factor_label: str = Field("", description="主导因子标签")
    # 详细评分
    index_score: float = Field(..., description="指数评分")
    sentiment_score: float = Field(..., description="情绪评分")
    overall_score: float = Field(..., description="综合评分")


class IndexQuote(BaseModel):
    """指数行情"""
    ts_code: str
    name: str
    close: float
    change_pct: float
    volume: float
    amount: float
    trade_date: str
    quote_time: Optional[str] = None
    data_source: Optional[str] = None


# ========== 板块相关 ==========

class SectorInput(BaseModel):
    """板块输入"""
    sector_name: str = Field(..., description="板块名称")
    sector_change_pct: float = Field(..., description="板块涨跌幅(%)")
    sector_turnover: Optional[float] = Field(None, description="板块成交额(亿元)")
    sector_strength_rank: Optional[int] = Field(None, description="板块强度排序")
    sector_continuity_days: Optional[int] = Field(None, description="连续活跃天数")
    sector_news_summary: Optional[str] = Field(None, description="板块催化摘要")
    sector_falsification: Optional[str] = Field(None, description="板块证伪线索")


class SectorDimensionScores(BaseModel):
    """板块五维评分"""
    linkage_score: float = Field(0.0, description="联动度")
    capital_score: float = Field(0.0, description="资金强度")
    continuity_score: float = Field(0.0, description="持续性")
    resilience_score: float = Field(0.0, description="抗分化能力")
    tradeability_score: float = Field(0.0, description="可交易性")


class SectorLeaderStock(BaseModel):
    """板块风向标个股"""
    ts_code: str
    stock_name: str
    change_pct: float
    amount: float = Field(0.0, description="成交额(万元)")
    candidate_source_tag: Optional[str] = Field(None, description="候选来源")
    leader_reason: Optional[str] = Field(None, description="风向标说明")
    quote_time: Optional[str] = None
    data_source: Optional[str] = None


class SectorTopStock(BaseModel):
    """板块 Top 股票"""
    rank: int
    ts_code: str
    stock_name: str
    change_pct: float
    amount: float = Field(0.0, description="成交额(万元)")
    turnover_rate: float = Field(0.0, description="换手率(%)")
    vol_ratio: float = Field(1.0, description="量比")
    role_tag: Optional[str] = Field(None, description="角色标签")
    candidate_source_tag: Optional[str] = Field(None, description="候选来源")
    top_reason: Optional[str] = Field(None, description="入选原因")
    quote_time: Optional[str] = None
    data_source: Optional[str] = None


class SectorOutput(BaseModel):
    """板块扫描输出"""
    sector_name: str
    sector_source_type: str = Field("industry", description="板块来源类型")
    sector_change_pct: float
    sector_score: float = Field(0.0, description="板块综合评分")
    sector_strength_rank: int
    sector_mainline_tag: SectorMainlineTag
    sector_continuity_tag: SectorContinuityTag
    sector_tradeability_tag: SectorTradeabilityTag
    sector_continuity_days: int = Field(0, description="连续活跃天数")
    sector_turnover: Optional[float] = Field(None, description="板块成交额(亿元)")
    sector_stock_count: Optional[int] = Field(None, description="板块成分股数量")
    sector_reason_tags: List[str] = Field(default_factory=list, description="板块判定原因")
    sector_comment: str = ""
    sector_dimension_scores: Optional[SectorDimensionScores] = Field(
        None,
        description="五维评分",
    )
    sector_tier: Optional[SectorTierTag] = Field(None, description="A/B/C 分级")
    sector_action_hint: Optional[SectorActionHint] = Field(
        None,
        description="执行建议",
    )
    sector_rotation_tag: Optional[SectorRotationTag] = Field(
        None,
        description="方向状态",
    )
    sector_rotation_reason: Optional[str] = Field(
        None,
        description="方向状态说明",
    )
    sector_summary_reason: Optional[str] = Field(None, description="主线总结")
    sector_news_summary: Optional[str] = None
    sector_falsification: Optional[str] = None
    front_runner_count: Optional[int] = Field(None, description="板块前排股数量")
    follow_runner_count: Optional[int] = Field(None, description="板块跟风股数量")
    afternoon_rebound_strength: Optional[float] = Field(None, description="板块午后回流力度")
    leader_broken: Optional[bool] = Field(None, description="龙头是否失守")


class SectorScanRequest(BaseModel):
    """板块扫描请求"""
    trade_date: str = Field(..., description="交易日")


class SectorScanResponse(BaseModel):
    """板块扫描响应"""
    trade_date: str
    resolved_trade_date: Optional[str] = Field(None, description="实际使用的交易日")
    sector_data_mode: Optional[str] = Field(None, description="板块数据口径")
    concept_data_status: Optional[str] = Field(None, description="题材聚合状态")
    concept_data_message: Optional[str] = Field(None, description="题材聚合说明")
    threshold_profile: Optional[str] = Field(None, description="阈值档位")
    mainline_sectors: List[SectorOutput] = Field(default_factory=list, description="主线板块")
    sub_mainline_sectors: List[SectorOutput] = Field(default_factory=list, description="次主线板块")
    follow_sectors: List[SectorOutput] = Field(default_factory=list, description="跟风板块")
    trash_sectors: List[SectorOutput] = Field(default_factory=list, description="杂毛板块")
    total_sectors: int


class LeaderSectorResponse(BaseModel):
    """主线板块响应"""
    trade_date: str
    resolved_trade_date: Optional[str] = Field(None, description="实际使用的交易日")
    sector_data_mode: Optional[str] = Field(None, description="板块数据口径")
    threshold_profile: Optional[str] = Field(None, description="阈值档位")
    concept_data_status: Optional[str] = Field(None, description="题材聚合状态")
    concept_data_message: Optional[str] = Field(None, description="题材聚合说明")
    sector: SectorOutput
    leader_stocks: List[SectorLeaderStock] = Field(
        default_factory=list,
        description="板块风向标",
    )


class SectorTopStocksResponse(BaseModel):
    """板块 Top 股票响应"""
    trade_date: str
    resolved_trade_date: Optional[str] = Field(None, description="实际使用的交易日")
    sector_data_mode: Optional[str] = Field(None, description="板块数据口径")
    threshold_profile: Optional[str] = Field(None, description="阈值档位")
    concept_data_status: Optional[str] = Field(None, description="题材聚合状态")
    concept_data_message: Optional[str] = Field(None, description="题材聚合说明")
    sector: SectorOutput
    top_stocks: List[SectorTopStock] = Field(default_factory=list, description="板块 Top 股票")
    total: int = Field(0, description="返回数量")


class HotSectorItem(BaseModel):
    """实时热门板块条目"""
    sector_id: Optional[str] = Field(None, description="外部源板块 ID")
    sector_name: str
    sector_source_type: str = Field(..., description="leader / industry / concept")
    sector_change_pct: float = Field(0.0, description="板块涨跌幅(%)")
    leader_stock_name: Optional[str] = Field(None, description="领涨股名称")
    leader_stock_ts_code: Optional[str] = Field(None, description="领涨股 ts_code")
    stock_count: Optional[int] = Field(None, description="成分股数量")
    quote_time: Optional[str] = Field(None, description="行情时间")
    data_source: Optional[str] = Field(None, description="数据源")


class HotSectorBoardsResponse(BaseModel):
    """实时热门板块响应"""
    trade_date: str
    resolved_trade_date: Optional[str] = Field(None, description="实际使用的交易日")
    data_source: str = Field("sina_hot_sector", description="数据源")
    leader_boards: List[HotSectorItem] = Field(default_factory=list, description="领涨板块")
    industry_boards: List[HotSectorItem] = Field(default_factory=list, description="热门行业")
    concept_boards: List[HotSectorItem] = Field(default_factory=list, description="热门概念")


# ========== 个股相关 ==========

class StockStrengthTag(str, Enum):
    """个股强弱标签"""
    STRONG = "强"
    MEDIUM = "中"
    WEAK = "弱"


class StockContinuityTag(str, Enum):
    """个股连续性标签"""
    SUSTAINABLE = "可持续"
    OBSERVABLE = "可观察"
    CAUTION = "末端谨慎"


class StockTradeabilityTag(str, Enum):
    """个股交易性标签"""
    TRADABLE = "可交易"
    CAUTION = "谨慎"
    NOT_RECOMMENDED = "不建议"


class StockCoreTag(str, Enum):
    """个股核心属性标签"""
    CORE = "核心"
    FOLLOW = "跟随"
    TRASH = "杂毛"


class StockPoolTag(str, Enum):
    """个股所属池"""
    MARKET_WATCH = "市场最强观察池"
    ACCOUNT_EXECUTABLE = "账户可参与池"
    HOLDING_PROCESS = "持仓处理池"
    NOT_IN_POOL = "不入池"


class TradeGateStatus(str, Enum):
    """三池总闸门状态"""
    ATTACK = "允许进攻"
    TRIAL = "允许试错"
    DEFENSE = "以防守为主"
    HOLDINGS_FIRST = "优先处理持仓，不建议新开"


class HoldingActionBucket(str, Enum):
    """持仓处理池分档"""
    IMMEDIATE = "立即处理"
    REDUCE_FIRST = "优先减仓"
    OBSERVE = "继续观察"
    HOLD_STRONG = "持有/强留仓"


class SectorProfileTag(str, Enum):
    """板块属性画像"""
    A_MAINLINE = "A类主线"
    B_SUB_MAINLINE = "B类次主线"
    NON_MAINSTREAM = "非主流方向"


class StockRoleTag(str, Enum):
    """个股地位画像"""
    LEADER = "龙头"
    FRONT = "前排"
    MID_CAPTAIN = "中军"
    FOLLOW = "跟风"
    TRASH = "杂毛"


class RepresentativeRoleTag(str, Enum):
    """主线样本角色"""
    LEADER = "龙头"
    MID_CAPTAIN = "中军"
    TREND_CORE = "趋势核心"
    ELASTIC_FRONT = "弹性前排"


class DayStrengthTag(str, Enum):
    """当日强度画像"""
    LIMIT_STRONG = "涨停级别强"
    TREND_STRONG = "趋势大阳强"
    REBOUND_STRONG = "分歧转强"
    FOLLOW_RISE = "只是跟涨"
    SPIKE_FADE = "冲高回落"


class StructureStateTag(str, Enum):
    """结构状态画像"""
    START = "启动"
    ACCELERATE = "加速"
    DIVERGENCE = "分歧"
    REPAIR = "修复"
    LATE_STAGE = "高位末端"


class NextTradeabilityTag(str, Enum):
    """次日可交易性画像"""
    LOW_SUCK = "有低吸点"
    RETRACE_CONFIRM = "有回踩确认点"
    BREAKTHROUGH = "有突破点"
    CHASE_ONLY = "只能追高"
    NO_GOOD_ENTRY = "基本没法做"


class StockInput(BaseModel):
    """个股输入"""
    ts_code: str = Field(..., description="股票代码")
    stock_name: str = Field(..., description="股票简称")
    sector_name: str = Field(..., description="所属板块")
    close: float = Field(..., description="收盘价")
    change_pct: float = Field(..., description="涨跌幅(%)")
    turnover_rate: float = Field(..., description="换手率(%)")
    amount: float = Field(..., description="成交额(万元)")
    vol_ratio: Optional[float] = Field(None, description="量比")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    open: float = Field(..., description="开盘价")
    pre_close: float = Field(..., description="前收价")
    trend_tag: str = Field(default="震荡", description="趋势标签")
    stage_tag: str = Field(default="震荡", description="阶段位置标签")
    news_catalyst: Optional[str] = Field(None, description="消息催化")
    news_risk: Optional[str] = Field(None, description="风险/证伪信息")
    candidate_source_tag: str = Field(default="", description="候选来源标签")
    volume: Optional[float] = Field(None, description="成交量")
    avg_price: Optional[float] = Field(None, description="盘中均价/VWAP")
    intraday_volume_ratio: Optional[float] = Field(None, description="盘中实时相对放量")
    quote_time: Optional[str] = Field(None, description="行情时间")
    data_source: Optional[str] = Field(None, description="行情来源")
    concept_names: List[str] = Field(default_factory=list, description="候选题材列表")


class StockOutput(BaseModel):
    """个股筛选输出"""
    ts_code: str
    stock_name: str
    sector_name: str
    change_pct: float
    amount: float = 0.0
    close: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    pre_close: float = 0.0
    vol_ratio: Optional[float] = None
    turnover_rate: float = 0.0
    stock_score: float = Field(0.0, description="综合评分")
    market_strength_score: float = Field(0.0, description="市场强度分")
    execution_opportunity_score: float = Field(0.0, description="执行机会分")
    account_entry_score: float = Field(0.0, description="账户执行优先级分")
    candidate_source_tag: str = Field(default="", description="候选来源标签")
    candidate_bucket_tag: str = Field(default="", description="候选分层标签")
    volume: Optional[float] = None
    avg_price: Optional[float] = None
    intraday_volume_ratio: Optional[float] = None
    quote_time: Optional[str] = Field(None, description="行情时间")
    data_source: Optional[str] = Field(None, description="行情来源")
    concept_names: List[str] = Field(default_factory=list, description="候选题材列表")
    # 评分标签
    stock_strength_tag: StockStrengthTag
    stock_continuity_tag: StockContinuityTag
    stock_tradeability_tag: StockTradeabilityTag
    stock_core_tag: StockCoreTag
    stock_pool_tag: StockPoolTag
    sector_profile_tag: Optional[SectorProfileTag] = None
    sector_tier_tag: Optional[SectorTierTag] = None
    stock_role_tag: Optional[StockRoleTag] = None
    representative_role_tag: Optional[RepresentativeRoleTag] = None
    day_strength_tag: Optional[DayStrengthTag] = None
    structure_state_tag: Optional[StructureStateTag] = None
    next_tradeability_tag: Optional[NextTradeabilityTag] = None
    direction_signal_tag: Optional[str] = None
    direction_signal_reason: Optional[str] = None
    # 证伪条件
    stock_falsification_cond: str = ""
    # 简评
    stock_comment: str = ""
    why_this_pool: Optional[str] = None
    not_other_pools: List[str] = Field(default_factory=list)
    pool_decision_summary: Optional[str] = None
    miss_risk_note: Optional[str] = None
    why_not_executable_but_should_watch: Optional[str] = None
    hard_filter_failed_rules: List[str] = Field(default_factory=list)
    hard_filter_failed_count: int = 0
    hard_filter_pass_count: int = 0
    hard_filter_summary: Optional[str] = None
    # 持仓上下文（仅持仓处理池使用）
    holding_qty: Optional[int] = None
    cost_price: Optional[float] = None
    holding_market_value: Optional[float] = None
    pnl_pct: Optional[float] = None
    buy_date: Optional[str] = None
    can_sell_today: Optional[bool] = None
    holding_reason: Optional[str] = None
    holding_days: Optional[int] = None
    # 持仓处理建议（由卖点分析回填）
    sell_signal_tag: Optional[str] = None
    sell_point_type: Optional[str] = None
    sell_trigger_cond: Optional[str] = None
    sell_reason: Optional[str] = None
    sell_priority: Optional[str] = None
    sell_comment: Optional[str] = None
    holding_action_bucket: Optional[HoldingActionBucket] = None
    # 账户可参与池补充说明
    account_entry_mode: Optional[str] = None
    pool_entry_reason: Optional[str] = None
    position_hint: Optional[str] = None
    execution_reference_price: Optional[float] = None
    execution_reference_gap_pct: Optional[float] = None
    execution_proximity_tag: Optional[str] = None
    execution_proximity_note: Optional[str] = None
    # LLM 辅助解释
    llm_plain_note: Optional[str] = None
    llm_risk_note: Optional[str] = None
    # 复盘反馈
    review_bias_score: float = Field(0.0, description="复盘反馈加减分")
    review_bias_label: Optional[str] = Field(None, description="复盘反馈标签")
    review_bias_reason: Optional[str] = Field(None, description="复盘反馈说明")


class IntradayFeatureSet(BaseModel):
    """盘中特征集合"""
    above_avg_line: Optional[bool] = Field(None, description="是否站上均价线")
    close_quality: float = Field(0.0, description="收盘位置质量")
    pullback_ratio: float = Field(0.0, description="冲高回落比例")
    rebound_strength: float = Field(0.0, description="反抽强度")
    breaks_prev_low: bool = Field(False, description="是否跌破前低")
    reclaims_avg_line: bool = Field(False, description="是否重新站回均价线")
    afternoon_rebound: bool = Field(False, description="是否存在午后回流")
    volume_ratio: float = Field(0.0, description="量能比率")


# ========== 三池相关 ==========

class GlobalTradeGateOutput(BaseModel):
    """三池上层总闸门"""
    status: TradeGateStatus
    allow_new_positions: bool = Field(..., description="是否允许新增仓位")
    dominant_reason: str = Field(default="", description="主导结论")
    reasons: List[str] = Field(default_factory=list, description="触发原因列表")
    account_pool_limit: int = Field(default=0, description="账户可参与池最大展示数")


class StockPoolsOutput(BaseModel):
    """三池输出"""
    trade_date: str
    resolved_trade_date: Optional[str] = Field(None, description="实际使用的候选行情交易日")
    sector_scan_trade_date: Optional[str] = Field(None, description="三池实际使用的板块扫描请求日")
    sector_scan_resolved_trade_date: Optional[str] = Field(None, description="三池实际使用的板块扫描数据日")
    snapshot_version: Optional[int] = Field(None, description="三池规则快照版本")
    global_trade_gate: GlobalTradeGateOutput = Field(default_factory=lambda: GlobalTradeGateOutput(
        status=TradeGateStatus.TRIAL,
        allow_new_positions=True,
        dominant_reason="默认允许试错",
        reasons=[],
        account_pool_limit=3,
    ))
    market_watch_pool: List[StockOutput] = Field(default_factory=list, description="市场最强观察池")
    account_executable_pool: List[StockOutput] = Field(default_factory=list, description="账户可参与池")
    holding_process_pool: List[StockOutput] = Field(default_factory=list, description="持仓处理池")
    total_count: int


# ========== 买点相关 ==========

class BuyPointType(str, Enum):
    """买点类型"""
    BREAKTHROUGH = "突破"  # 突破
    RETRACE_SUPPORT = "回踩承接"  # 回踩承接
    REPAIR_STRENGTHEN = "修复转强"  # 修复转强
    LOW_SUCK = "低吸"  # 低吸（待确认）


class BuySignalTag(str, Enum):
    """买点信号标签"""
    CAN_BUY = "可买"
    OBSERVE = "观察"
    NOT_BUY = "不买"


class BuyPointOutput(BaseModel):
    """买点分析输出"""
    ts_code: str
    stock_name: str
    sector_name: str = Field(default="", description="所属板块/行业")
    candidate_source_tag: str = Field(default="", description="候选来源标签")
    candidate_bucket_tag: str = Field(default="", description="候选分层标签")
    stock_pool_tag: str = Field(default="", description="来源池标签")
    pool_entry_reason: str = Field(default="", description="入池原因")
    account_entry_mode: str = Field(default="", description="账户执行模式")
    hard_filter_failed_rules: List[str] = Field(default_factory=list, description="硬过滤未通过项")
    hard_filter_failed_count: int = Field(default=0, description="硬过滤失败条数")
    hard_filter_pass_count: int = Field(default=0, description="硬过滤通过条数")
    hard_filter_summary: str = Field(default="", description="硬过滤摘要")
    # 买点信号
    buy_signal_tag: BuySignalTag
    buy_point_type: BuyPointType
    # 条件
    buy_trigger_cond: str = Field(..., description="触发条件")
    buy_confirm_cond: str = Field(..., description="确认条件")
    buy_invalid_cond: str = Field(..., description="失效条件")
    buy_current_price: Optional[float] = Field(None, description="最新可用价格")
    buy_current_change_pct: Optional[float] = Field(None, description="最新涨跌幅")
    buy_quote_time: Optional[str] = Field(None, description="行情时间")
    buy_data_source: Optional[str] = Field(None, description="行情来源")
    buy_trigger_price: Optional[float] = Field(None, description="触发价格")
    buy_invalid_price: Optional[float] = Field(None, description="失效价格")
    buy_trigger_gap_pct: Optional[float] = Field(None, description="距触发价百分比")
    buy_invalid_gap_pct: Optional[float] = Field(None, description="距失效价百分比")
    buy_required_volume_ratio: Optional[float] = Field(None, description="所需量比")
    buy_requires_sector_resonance: bool = Field(False, description="是否要求板块共振")
    # 风险评估
    buy_risk_level: RiskLevel
    buy_account_fit: str = Field(..., description="适合/一般/不适合")
    # 简评
    buy_comment: str = ""
    recommended_order_pct: Optional[float] = Field(None, description="建议本次下单仓位比例")
    recommended_order_amount: Optional[float] = Field(None, description="建议本次下单金额")
    recommended_shares: Optional[int] = Field(None, description="建议本次下单股数")
    recommended_lots: Optional[int] = Field(None, description="建议本次下单手数")
    sizing_reference_price: Optional[float] = Field(None, description="测算参考价格")
    sizing_note: Optional[str] = Field(None, description="仓位测算说明")
    # 复盘反馈
    review_bias_score: float = Field(0.0, description="复盘反馈加减分")
    review_bias_label: Optional[str] = Field(None, description="复盘反馈标签")
    review_bias_reason: Optional[str] = Field(None, description="复盘反馈说明")


class BuyPointRequest(BaseModel):
    """买点分析请求"""
    trade_date: str = Field(..., description="交易日")
    ts_codes: Optional[List[str]] = Field(None, description="股票代码列表，为空则分析全部")


class BuyPointResponse(BaseModel):
    """买点分析响应"""
    trade_date: str
    market_env_tag: MarketEnvTag
    available_buy_points: List[BuyPointOutput] = Field(default_factory=list, description="可买候选")
    observe_buy_points: List[BuyPointOutput] = Field(default_factory=list, description="观察候选")
    not_buy_points: List[BuyPointOutput] = Field(default_factory=list, description="不建议买")
    total_count: int


class BuyPointSopBasicInfo(BaseModel):
    """单股买点分析基础信息"""
    ts_code: str
    stock_name: str
    sector_name: str
    market_env_tag: str = ""
    stable_market_env_tag: str = ""
    realtime_market_env_tag: str = ""
    buy_signal_tag: str = ""
    buy_point_type: str = ""
    candidate_bucket_tag: str = ""
    quote_time: Optional[str] = None
    data_source: Optional[str] = None


class BuyPointSopAccountContext(BaseModel):
    """账户语境"""
    position_status: str = ""
    same_direction_exposure: str = ""
    current_use: str = ""
    market_suitability: str = ""
    account_conclusion: str = ""
    same_code_holding_qty: Optional[int] = None
    same_code_cost_price: Optional[float] = None
    same_code_market_price: Optional[float] = None
    same_code_pnl_pct: Optional[float] = None


class BuyPointSopDailyJudgement(BaseModel):
    """日线买点级别"""
    current_stage: str = ""
    buy_signal: str = ""
    buy_point_level: str = ""
    reason: str = ""
    risk_items: List[str] = Field(default_factory=list)
    reference_levels: List[str] = Field(default_factory=list)


class BuyPointSopIntradayJudgement(BaseModel):
    """分时执行判断"""
    price_vs_avg_line: str = ""
    intraday_structure: str = ""
    volume_quality: str = ""
    key_level_status: str = ""
    conclusion: str = ""
    note: str = ""


class BuyPointSopOrderPlan(BaseModel):
    """挂单计划"""
    low_absorb_price: str = ""
    breakout_price: str = ""
    retrace_confirm_price: str = ""
    give_up_price: str = ""
    trigger_condition: str = ""
    invalid_condition: str = ""
    above_no_chase: str = ""
    below_no_buy: str = ""


class BuyPointSopAddPositionDecision(BaseModel):
    """加仓决策"""
    eligible: bool = False
    decision: str = ""
    score_total: int = 0
    trend_score: int = 0
    position_score: int = 0
    volume_price_score: int = 0
    sector_sentiment_score: int = 0
    account_risk_score: int = 0
    trigger_scene: str = ""
    blockers: List[str] = Field(default_factory=list)
    reason: str = ""


class BuyPointSopPositionAdvice(BaseModel):
    """仓位建议"""
    suggestion: str = ""
    reason: str = ""
    invalidation_level: str = ""
    invalidation_action: str = ""
    plan_position_pct: Optional[float] = None
    increment_position_pct: Optional[float] = None
    max_position_pct: Optional[float] = None
    recommended_position_pct: Optional[float] = None
    recommended_order_pct: Optional[float] = None
    recommended_order_amount: Optional[float] = None
    recommended_shares: Optional[int] = None
    recommended_lots: Optional[int] = None
    sizing_reference_price: Optional[float] = None
    sizing_note: Optional[str] = None
    risk_control_action: Optional[str] = None
    exit_priority: Optional[str] = None


class BuyPointSopExecution(BaseModel):
    """一句话执行"""
    action: str = ""
    reason: str = ""


class BuyPointSopResponse(BaseModel):
    """单股买点分析 SOP 响应"""
    trade_date: str
    resolved_trade_date: Optional[str] = None
    stock_found_in_candidates: bool = False
    basic_info: BuyPointSopBasicInfo
    account_context: BuyPointSopAccountContext
    daily_judgement: BuyPointSopDailyJudgement
    intraday_judgement: BuyPointSopIntradayJudgement
    order_plan: BuyPointSopOrderPlan
    add_position_decision: Optional[BuyPointSopAddPositionDecision] = None
    position_advice: BuyPointSopPositionAdvice
    execution: BuyPointSopExecution


# ========== 卖点相关 ==========

class SellPointType(str, Enum):
    """卖点类型"""
    STOP_LOSS = "止损"  # 止损
    STOP_PROFIT = "止盈"  # 止盈
    REDUCE_POSITION = "减仓"  # 减仓
    INVALID_EXIT = "失效退出"  # 失效退出


class SellSignalTag(str, Enum):
    """卖点信号标签"""
    HOLD = "持有"
    REDUCE = "减仓"
    SELL = "卖出"
    OBSERVE = "观察"


class SellPriority(str, Enum):
    """卖点优先级"""
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class SellPointOutput(BaseModel):
    """卖点分析输出"""
    ts_code: str
    stock_name: str
    market_price: Optional[float] = Field(None, description="当前价格")
    quote_time: Optional[str] = Field(None, description="行情时间")
    data_source: Optional[str] = Field(None, description="行情来源")
    cost_price: Optional[float] = Field(None, description="成本价")
    pnl_pct: Optional[float] = Field(None, description="浮盈亏比例")
    holding_qty: Optional[int] = Field(None, description="持仓数量")
    holding_days: Optional[int] = Field(None, description="持有天数")
    can_sell_today: Optional[bool] = Field(None, description="今日是否可卖")
    # 卖点信号
    sell_signal_tag: SellSignalTag
    sell_point_type: SellPointType
    # 条件
    sell_trigger_cond: str = Field(..., description="卖点触发条件")
    sell_reason: str = Field(..., description="卖出/减仓原因")
    reduce_reason_code: Optional[str] = Field(None, description="减仓原因代码")
    # 优先级
    sell_priority: SellPriority
    # 简评
    sell_comment: str = ""
    # 持有观察下的加仓提示
    add_signal_tag: Optional[str] = Field(None, description="建议加仓/仅可小加/可关注加仓")
    add_signal_reason: Optional[str] = Field(None, description="加仓提示原因")
    # LLM 辅助解释
    llm_plain_note: Optional[str] = None
    llm_action_sentence: Optional[str] = None
    llm_trigger_sentence: Optional[str] = None
    llm_risk_sentence: Optional[str] = None


class SellPointResponse(BaseModel):
    """卖点分析响应"""
    trade_date: str
    hold_positions: List[SellPointOutput] = Field(default_factory=list, description="持有观察")
    reduce_positions: List[SellPointOutput] = Field(default_factory=list, description="建议减仓")
    sell_positions: List[SellPointOutput] = Field(default_factory=list, description="建议卖出")
    total_count: int


class SellPointSopBasicInfo(BaseModel):
    """单股卖点分析基础信息"""
    ts_code: str
    stock_name: str
    market_env_tag: str = ""
    stable_market_env_tag: str = ""
    realtime_market_env_tag: str = ""
    sell_signal_tag: str = ""
    sell_point_type: str = ""
    quote_time: Optional[str] = None
    data_source: Optional[str] = None


class SellPointSopAccountContext(BaseModel):
    """卖点账户语境"""
    position_status: str = ""
    pnl_status: str = ""
    role: str = ""
    priority: str = ""
    context_summary: str = ""


class SellPointSopDailyJudgement(BaseModel):
    """日线卖点级别"""
    current_stage: str = ""
    sell_signal: str = ""
    sell_point_level: str = ""
    reason: str = ""


class SellPointSopIntradayJudgement(BaseModel):
    """分时执行判断"""
    price_vs_avg_line: str = ""
    intraday_structure: str = ""
    volume_quality: str = ""
    conclusion: str = ""
    note: str = ""


class SellPointSopOrderPlan(BaseModel):
    """卖点挂单计划"""
    priority_exit_price: str = ""
    proactive_take_profit_price: str = ""
    rebound_sell_price: str = ""
    break_stop_price: str = ""
    observe_level: str = ""
    priority_exit_condition: str = ""
    take_profit_condition: str = ""
    rebound_condition: str = ""
    stop_condition: str = ""
    hold_condition: str = ""


class SellPointSopExecution(BaseModel):
    """卖点一句话执行"""
    action: str = ""
    partial_plan: str = ""
    key_level: str = ""
    reason: str = ""


class SellPointSopResponse(BaseModel):
    """单股卖点 SOP 响应"""
    trade_date: str
    resolved_trade_date: Optional[str] = None
    stock_found_in_holdings: bool = False
    basic_info: SellPointSopBasicInfo
    account_context: SellPointSopAccountContext
    daily_judgement: SellPointSopDailyJudgement
    intraday_judgement: SellPointSopIntradayJudgement
    order_plan: SellPointSopOrderPlan
    execution: SellPointSopExecution


# ========== 账户相关 ==========

class AccountPosition(BaseModel):
    """持仓明细"""
    id: Optional[str] = None
    ts_code: str
    stock_name: str
    holding_qty: int
    cost_price: float
    market_price: float
    pnl_pct: float
    holding_market_value: float
    buy_date: str
    can_sell_today: bool
    holding_reason: Optional[str] = None
    pre_close: Optional[float] = None
    holding_days: int = 0
    pnl_amount: float = 0.0
    today_pnl_amount: float = 0.0
    avg_price: Optional[float] = None
    quote_time: Optional[str] = None
    data_source: Optional[str] = None


class AccountInput(BaseModel):
    """账户输入"""
    total_asset: float = Field(..., description="总资产(元)")
    available_cash: float = Field(..., description="可用资金(元)")
    total_position_ratio: float = Field(..., description="总仓位(0-1)")
    holding_count: int = Field(..., description="持仓数量")
    today_new_buy_count: int = Field(0, description="当日新开仓数量")
    t1_locked_positions: List[AccountPosition] = Field(default_factory=list, description="T+1锁定持仓")


class AccountOutput(BaseModel):
    """账户适配输出"""
    account_action_tag: str = Field(..., description="账户操作标签: 可执行/谨慎执行/不执行")
    position_pressure_tag: str = Field(..., description="仓位压力: 低/中/高")
    new_position_allowed: bool = Field(..., description="是否允许新开仓")
    priority_action: str = Field(..., description="当前优先动作")
    account_comment: str = Field(..., description="账户适配说明")


class AccountProfile(BaseModel):
    """账户概况"""
    total_asset: float
    available_cash: float
    total_position_ratio: float
    holding_count: int
    today_new_buy_count: int
    t1_locked_count: int
    market_value: float
    total_pnl_amount: float = 0.0
    today_pnl_amount: float = 0.0


# ========== 执行摘要相关 ==========

class DecisionSummary(BaseModel):
    """执行摘要"""
    trade_date: str
    today_action: str = Field(..., description="今天该不该出手")
    focus: str = Field(..., description="优先看谁")
    avoid: str = Field(..., description="哪些绝对不碰")
    # 市场环境
    market_env_tag: str
    breakout_allowed: bool
    # 账户适配
    account_action_tag: str
    new_position_allowed: bool
    priority_action: str
    # 统计
    buy_recommend_count: int
    sell_recommend_count: int


class FullDecisionResponse(BaseModel):
    """完整决策分析响应"""
    trade_date: str
    # 市场环境
    market_env: dict
    # 板块扫描
    sector_scan: dict
    # 三池
    stock_pools: dict
    # 买点分析
    buy_analysis: dict
    # 卖点分析
    sell_analysis: dict
    # 账户适配
    account_fit: dict
    # 执行摘要
    summary: DecisionSummary


# ========== LLM 辅助相关 ==========

class LlmStockNote(BaseModel):
    """LLM 对单只股票的辅助说明"""
    ts_code: str
    plain_note: str = ""
    risk_note: str = ""


class LlmPoolsSummary(BaseModel):
    """三池页 LLM 摘要"""
    page_summary: str = ""
    top_focus_summary: str = ""
    pool_empty_reason: str = ""
    stock_notes: List[LlmStockNote] = Field(default_factory=list)


class LlmSellNote(BaseModel):
    """卖点页 LLM 对单只持仓的辅助说明"""
    ts_code: str
    plain_note: str = ""
    action_sentence: str = ""
    trigger_sentence: str = ""
    risk_sentence: str = ""


class LlmSellSummary(BaseModel):
    """卖点页 LLM 摘要"""
    page_summary: str = ""
    action_summary: str = ""
    notes: List[LlmSellNote] = Field(default_factory=list)


class StockCheckupTarget(str, Enum):
    """个股体检目标"""
    OBSERVE = "观察型"
    HOLDING = "持仓型"
    TRADING = "交易型"


class StockCheckupBasicInfo(BaseModel):
    """个股体检基础信息"""
    ts_code: str
    stock_name: str
    sector_name: str
    board: str = ""
    special_tags: List[str] = Field(default_factory=list)
    data_source: Optional[str] = None
    quote_time: Optional[str] = None


class StockCheckupMarketContext(BaseModel):
    """体检中的市场环境结论"""
    market_env_tag: str
    market_phase: str = ""
    market_comment: str = ""
    stock_market_alignment: str = ""
    tolerance_comment: str = ""


class StockCheckupDirectionPosition(BaseModel):
    """方向与地位"""
    direction_name: str = ""
    sector_level: str = ""
    sector_trend: str = ""
    sector_linkage: str = ""
    stock_role: str = ""
    relative_strength: str = ""


class StockCheckupDailyStructure(BaseModel):
    """日线结构体检"""
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma_position_summary: str = ""
    stage_position: str = ""
    range_position_20d: str = ""
    range_position_60d: str = ""
    pattern_integrity: str = ""
    structure_conclusion: str = ""


class StockCheckupIntradayStrength(BaseModel):
    """短线强度"""
    change_pct: Optional[float] = None
    turnover_rate: Optional[float] = None
    vol_ratio: Optional[float] = None
    close_position: str = ""
    candle_label: str = ""
    volume_state: str = ""
    strength_level: str = ""


class StockCheckupFundQuality(BaseModel):
    """资金质量"""
    recent_fund_flow: str = ""
    big_order_status: str = ""
    volume_behavior: str = ""
    cash_flow_quality: str = ""
    note: str = ""


class StockCheckupPeerItem(BaseModel):
    """同类对比条目"""
    ts_code: str
    stock_name: str
    sector_name: str = ""
    change_pct: Optional[float] = None
    turnover_rate: Optional[float] = None
    amount: Optional[float] = None
    role_hint: str = ""
    relative_note: str = ""


class StockCheckupPeerComparison(BaseModel):
    """同类横向对比"""
    peers: List[StockCheckupPeerItem] = Field(default_factory=list)
    relative_strength: str = ""
    recognizability: str = ""
    note: str = ""


class StockCheckupValuationProfile(BaseModel):
    """估值与属性"""
    pe: Optional[float] = None
    pb: Optional[float] = None
    ps: Optional[float] = None
    market_value: Optional[float] = None
    valuation_level: str = ""
    drive_type: str = ""
    note: str = ""


class StockCheckupKeyLevels(BaseModel):
    """关键位"""
    pressure_levels: List[float] = Field(default_factory=list)
    support_levels: List[float] = Field(default_factory=list)
    defense_level: Optional[float] = None
    note: str = ""


class StockCheckupBuyView(BaseModel):
    """买点相关视角"""
    buy_signal_tag: Optional[str] = None
    buy_point_type: Optional[str] = None
    buy_trigger_cond: str = ""
    buy_confirm_cond: str = ""
    buy_invalid_cond: str = ""
    buy_comment: str = ""


class StockCheckupSellView(BaseModel):
    """卖点相关视角"""
    sell_signal_tag: Optional[str] = None
    sell_point_type: Optional[str] = None
    sell_trigger_cond: str = ""
    sell_reason: str = ""
    reduce_reason_code: Optional[str] = None
    sell_comment: str = ""
    can_sell_today: Optional[bool] = None


class StockCheckupStrategy(BaseModel):
    """策略适配结论"""
    current_characterization: str = ""
    current_role: str = ""
    current_strategy: str = ""
    strategy_reason: str = ""
    risk_points: List[str] = Field(default_factory=list)


class StockCheckupFinalConclusion(BaseModel):
    """一句话体检结论"""
    one_line_conclusion: str = ""
    summary_note: str = ""


class StockCheckupRuleSnapshot(BaseModel):
    """个股体检规则快照"""
    basic_info: StockCheckupBasicInfo
    market_context: StockCheckupMarketContext
    direction_position: StockCheckupDirectionPosition
    daily_structure: StockCheckupDailyStructure
    intraday_strength: StockCheckupIntradayStrength
    fund_quality: StockCheckupFundQuality
    peer_comparison: StockCheckupPeerComparison
    valuation_profile: StockCheckupValuationProfile
    key_levels: StockCheckupKeyLevels
    buy_view: Optional[StockCheckupBuyView] = None
    sell_view: Optional[StockCheckupSellView] = None
    strategy: StockCheckupStrategy
    final_conclusion: StockCheckupFinalConclusion


class LlmStockCheckupSection(BaseModel):
    """LLM 体检章节"""
    key: str
    title: str
    content: str = ""


class LlmStockCheckupReport(BaseModel):
    """单股体检 LLM 报告"""
    overall_summary: str = ""
    llm_report_sections: List[LlmStockCheckupSection] = Field(default_factory=list)
    key_risks: List[str] = Field(default_factory=list)
    one_line_conclusion: str = ""


class StockCheckupRequest(BaseModel):
    """个股体检请求"""
    ts_code: str = Field(..., description="股票代码")
    trade_date: str = Field(..., description="交易日")
    checkup_target: StockCheckupTarget = Field(
        default=StockCheckupTarget.OBSERVE,
        description="体检目标",
    )
    force_llm_refresh: bool = Field(False, description="是否强制刷新 LLM 缓存")


class StockCheckupResponse(BaseModel):
    """个股体检响应"""
    trade_date: str
    resolved_trade_date: Optional[str] = None
    checkup_target: StockCheckupTarget
    stock_found_in_candidates: bool = False
    rule_snapshot: StockCheckupRuleSnapshot
    llm_report: Optional[LlmStockCheckupReport] = None
    llm_status: "LlmCallStatus"


class LlmCallStatus(BaseModel):
    """LLM 调用状态"""
    enabled: bool = False
    success: bool = False
    status: str = "disabled"
    message: str = ""


# ========== 通知相关 ==========

class NotificationCategory(str, Enum):
    MARKET = "market"
    HOLDING = "holding"
    CANDIDATE = "candidate"
    SYSTEM = "system"


class NotificationPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    READ = "read"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"
    RESOLVED = "resolved"


class NotificationActionTargetType(str, Enum):
    ROUTE = "route"
    BUY_ANALYSIS = "buy_analysis"
    SELL_ANALYSIS = "sell_analysis"
    CHECKUP = "checkup"
    EXTERNAL = "external"


class NotificationItem(BaseModel):
    id: str
    event_type: str
    category: NotificationCategory
    priority: NotificationPriority
    status: NotificationStatus
    title: str
    message: str
    action_label: str
    action_target_type: NotificationActionTargetType
    action_target_payload: dict = Field(default_factory=dict)
    entity_type: str
    entity_code: Optional[str] = None
    trade_date: str
    data_source: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    read_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    items: List[NotificationItem] = Field(default_factory=list)
    unread_count: int = 0
    critical_count: int = 0
    next_cursor: Optional[str] = None


class NotificationSummaryResponse(BaseModel):
    unread_count: int = 0
    critical_count: int = 0
    latest_items: List[NotificationItem] = Field(default_factory=list)
    quiet_window_active: bool = False
    quiet_window_label: Optional[str] = None


class NotificationReadRequest(BaseModel):
    ids: List[str] = Field(default_factory=list)
    status: Optional[NotificationStatus] = None
    category: Optional[NotificationCategory] = None
    priority: Optional[NotificationPriority] = None
    exclude_priorities: List[NotificationPriority] = Field(default_factory=list)


class NotificationSnoozeRequest(BaseModel):
    minutes: int = Field(..., ge=5, le=480)


class NotificationSettingsPayload(BaseModel):
    in_app_enabled: bool = True
    wecom_enabled: bool = False
    rules: dict = Field(default_factory=dict)
    quiet_windows: List[dict] = Field(default_factory=list)


# ========== 通用响应 ==========

class ApiResponse(BaseModel):
    """通用 API 响应"""
    code: int = 200
    message: str = "success"
    data: Optional[dict] = None


StockCheckupResponse.model_rebuild()
