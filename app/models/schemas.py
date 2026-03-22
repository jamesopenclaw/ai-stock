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
    breakout_allowed: bool
    risk_level: RiskLevel
    market_comment: str
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
    sector_news_summary: Optional[str] = None
    sector_falsification: Optional[str] = None


class SectorScanRequest(BaseModel):
    """板块扫描请求"""
    trade_date: str = Field(..., description="交易日")


class SectorScanResponse(BaseModel):
    """板块扫描响应"""
    trade_date: str
    resolved_trade_date: Optional[str] = Field(None, description="实际使用的交易日")
    sector_data_mode: Optional[str] = Field(None, description="板块数据口径")
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
    sector: SectorOutput


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


class StockOutput(BaseModel):
    """个股筛选输出"""
    ts_code: str
    stock_name: str
    sector_name: str
    change_pct: float
    close: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    pre_close: float = 0.0
    vol_ratio: Optional[float] = None
    turnover_rate: float = 0.0
    stock_score: float = Field(0.0, description="综合评分")
    candidate_source_tag: str = Field(default="", description="候选来源标签")
    candidate_bucket_tag: str = Field(default="", description="候选分层标签")
    # 评分标签
    stock_strength_tag: StockStrengthTag
    stock_continuity_tag: StockContinuityTag
    stock_tradeability_tag: StockTradeabilityTag
    stock_core_tag: StockCoreTag
    stock_pool_tag: StockPoolTag
    # 证伪条件
    stock_falsification_cond: str = ""
    # 简评
    stock_comment: str = ""
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
    # 账户可参与池补充说明
    pool_entry_reason: Optional[str] = None
    position_hint: Optional[str] = None


# ========== 三池相关 ==========

class StockPoolsOutput(BaseModel):
    """三池输出"""
    trade_date: str
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
    candidate_source_tag: str = Field(default="", description="候选来源标签")
    candidate_bucket_tag: str = Field(default="", description="候选分层标签")
    # 买点信号
    buy_signal_tag: BuySignalTag
    buy_point_type: BuyPointType
    # 条件
    buy_trigger_cond: str = Field(..., description="触发条件")
    buy_confirm_cond: str = Field(..., description="确认条件")
    buy_invalid_cond: str = Field(..., description="失效条件")
    buy_current_price: Optional[float] = Field(None, description="最新可用价格")
    buy_current_change_pct: Optional[float] = Field(None, description="最新涨跌幅")
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
    # 优先级
    sell_priority: SellPriority
    # 简评
    sell_comment: str = ""


class SellPointResponse(BaseModel):
    """卖点分析响应"""
    trade_date: str
    hold_positions: List[SellPointOutput] = Field(default_factory=list, description="持有观察")
    reduce_positions: List[SellPointOutput] = Field(default_factory=list, description="建议减仓")
    sell_positions: List[SellPointOutput] = Field(default_factory=list, description="建议卖出")
    total_count: int


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


# ========== 通用响应 ==========

class ApiResponse(BaseModel):
    """通用 API 响应"""
    code: int = 200
    message: str = "success"
    data: Optional[dict] = None
