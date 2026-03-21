"""
持仓数据模型
"""
from sqlalchemy import Column, String, Integer, Float, Boolean, Date
from app.core.database import Base


class Holding(Base):
    """持仓模型"""
    __tablename__ = "holdings"

    id = Column(String, primary_key=True)
    ts_code = Column(String, nullable=False, index=True)  # 股票代码
    stock_name = Column(String)  # 股票名称
    holding_qty = Column(Integer, nullable=False)  # 持仓数量
    cost_price = Column(Float, nullable=False)  # 成本价
    market_price = Column(Float, default=0)  # 现价
    pnl_pct = Column(Float, default=0)  # 盈亏比例
    holding_market_value = Column(Float, default=0)  # 持仓市值
    buy_date = Column(String, nullable=False)  # 买入日期
    can_sell_today = Column(Boolean, default=True)  # 今日是否可卖
    holding_reason = Column(String)  # 买入理由

    def to_dict(self):
        return {
            "id": self.id,
            "ts_code": self.ts_code,
            "stock_name": self.stock_name,
            "holding_qty": self.holding_qty,
            "cost_price": self.cost_price,
            "market_price": self.market_price,
            "pnl_pct": self.pnl_pct,
            "holding_market_value": self.holding_market_value,
            "buy_date": self.buy_date,
            "can_sell_today": self.can_sell_today,
            "holding_reason": self.holding_reason
        }
