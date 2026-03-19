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
    sector_change_pct: float
    sector_strength_rank: int
    sector_mainline_tag: SectorMainlineTag
    sector_continuity_tag: SectorContinuityTag
    sector_tradeability_tag: SectorTradeabilityTag
    sector_continuity_days: int = Field(0, description="连续活跃天数")
    sector_comment: str = ""
    sector_news_summary: Optional[str] = None
    sector_falsification: Optional[str] = None


class SectorScanRequest(BaseModel):
    """板块扫描请求"""
    trade_date: str = Field(..., description="交易日")


class SectorScanResponse(BaseModel):
    """板块扫描响应"""
    trade_date: str
    mainline_sectors: List[SectorOutput] = Field(default_factory=list, description="主线板块")
    sub_mainline_sectors: List[SectorOutput] = Field(default_factory=list, description="次主线板块")
    follow_sectors: List[SectorOutput] = Field(default_factory=list, description="跟风板块")
    trash_sectors: List[SectorOutput] = Field(default_factory=list, description="杂毛板块")
    total_sectors: int


class LeaderSectorResponse(BaseModel):
    """主线板块响应"""
    trade_date: str
    sector: SectorOutput


# ========== 账户相关 ==========

class AccountPosition(BaseModel):
    """持仓明细"""
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


# ========== 通用响应 ==========

class ApiResponse(BaseModel):
    """通用 API 响应"""
    code: int = 200
    message: str = "success"
    data: Optional[dict] = None
