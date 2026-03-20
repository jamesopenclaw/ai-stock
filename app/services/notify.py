"""
企业微信机器人通知服务
"""
import httpx
from typing import Optional, Dict, List
from loguru import logger

from app.core.config import settings


class WeChatNotifier:
    """企业微信机器人通知"""

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or settings.wecom_webhook_url
        self.enabled = bool(self.webhook_url)

    async def send_text(self, content: str, mentioned_list: List[str] = None) -> bool:
        """
        发送文本消息

        Args:
            content: 消息内容
            mentioned_list: @成员的手机号列表

        Returns:
            是否发送成功
        """
        if not self.enabled:
            logger.warning("企业微信 webhook 未配置，跳过推送")
            return False

        try:
            payload = {
                "msgtype": "text",
                "text": {
                    "content": content,
                    "mentioned_list": mentioned_list or []
                }
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json=payload, timeout=10)
                result = resp.json()

                if result.get("errcode") == 0:
                    logger.info("企业微信消息推送成功")
                    return True
                else:
                    logger.error(f"企业微信消息推送失败: {result}")
                    return False

        except Exception as e:
            logger.error(f"企业微信消息推送异常: {e}")
            return False

    async def send_markdown(self, content: str) -> bool:
        """
        发送 Markdown 消息

        Args:
            content: Markdown 格式的消息内容

        Returns:
            是否发送成功
        """
        if not self.enabled:
            logger.warning("企业微信 webhook 未配置，跳过推送")
            return False

        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": content
                }
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json=payload, timeout=10)
                result = resp.json()

                if result.get("errcode") == 0:
                    logger.info("企业微信 Markdown 消息推送成功")
                    return True
                else:
                    logger.error(f"企业微信 Markdown 消息推送失败: {result}")
                    return False

        except Exception as e:
            logger.error(f"企业微信 Markdown 消息推送异常: {e}")
            return False


class NotifyService:
    """通知服务 - 整合各种推送渠道"""

    def __init__(self):
        self.wecom = WeChatNotifier()

    async def notify_market_env(self, market_env: Dict) -> bool:
        """
        推送市场环境

        Args:
            market_env: 市场环境数据

        Returns:
            是否推送成功
        """
        env_tag = market_env.get("market_env_tag", "未知")
        breakout = "允许" if market_env.get("breakout_allowed") else "禁止"
        risk_level = market_env.get("risk_level", "未知")
        comment = market_env.get("market_comment", "")

        content = f"""## 📊 市场环境播报

> **环境标签**: {env_tag}
> **突破操作**: {breakout}
> **风险等级**: {risk_level}

**市场简评**: {comment}
"""

        return await self.wecom.send_markdown(content)

    async def notify_sector_scan(self, sector_data: Dict) -> bool:
        """
        推送板块扫描结果

        Args:
            sector_data: 板块扫描数据
        """
        mainline = sector_data.get("mainline_sectors", [])
        mainline_names = [s["sector_name"] for s in mainline[:5]] if mainline else "无"

        content = f"""## 🔥 板块扫描结果

**主线板块**: {", ".join(mainline_names) if isinstance(mainline_names, list) else mainline_names}

"""

        return await self.wecom.send_markdown(content)

    async def notify_stock_pools(self, pools_data: Dict) -> bool:
        """
        推送三池分类结果

        Args:
            pools_data: 三池数据
        """
        market_pool = pools_data.get("market_watch_pool", [])
        account_pool = pools_data.get("account_executable_pool", [])
        holding_pool = pools_data.get("holding_process_pool", [])

        market_count = len(market_pool)
        account_count = len(account_pool)
        holding_count = len(holding_pool)

        # 获取账户可参与池的前3只
        top_stocks = []
        if account_pool:
            for s in account_pool[:3]:
                top_stocks.append(f"{s.get('stock_name', '')}({s.get('ts_code', '')})")

        content = f"""## 🏊 三池分类结果

- **市场观察池**: {market_count} 只
- **账户可参与池**: {account_count} 只
- **持仓处理池**: {holding_count} 只

**今日重点关注**:
{chr(10).join([f"- {s}" for s in top_stocks]) if top_stocks else "无"}
"""

        return await self.wecom.send_markdown(content)

    async def notify_buy_points(self, buy_data: Dict) -> bool:
        """
        推送买点分析结果

        Args:
            buy_data: 买点分析数据
        """
        available = buy_data.get("available_buy_points", [])
        observe = buy_data.get("observe_buy_points", [])

        content = f"""## 💰 买点分析结果

**可买候选** ({len(available)}只):
"""

        for bp in available[:5]:
            content += f"- {bp.get('stock_name', '')} ({bp.get('ts_code', '')}) - {bp.get('buy_point_type', '')}\n"

        if observe:
            content += f"\n**观察候选** ({len(observe)}只):\n"
            for bp in observe[:3]:
                content += f"- {bp.get('stock_name', '')} ({bp.get('ts_code', '')})\n"

        return await self.wecom.send_markdown(content)

    async def notify_sell_points(self, sell_data: Dict) -> bool:
        """
        推送卖点分析结果

        Args:
            sell_data: 卖点分析数据
        """
        sell = sell_data.get("sell_positions", [])
        reduce_pos = sell_data.get("reduce_positions", [])
        hold = sell_data.get("hold_positions", [])

        content = f"""## 📉 卖点分析结果

**建议卖出** ({len(sell)}只):
"""
        for sp in sell[:3]:
            content += f"- {sp.get('stock_name', '')}: {sp.get('sell_reason', '')}\n"

        if reduce_pos:
            content += f"\n**建议减仓** ({len(reduce_pos)}只):\n"
            for sp in reduce_pos[:2]:
                content += f"- {sp.get('stock_name', '')}\n"

        return await self.wecom.send_markdown(content)

    async def notify_summary(self, summary_data: Dict) -> bool:
        """
        推送执行摘要

        Args:
            summary_data: 执行摘要数据
        """
        today_action = summary_data.get("today_action", "待定")
        focus = summary_data.get("focus", "无")
        avoid = summary_data.get("avoid", "无")
        market_env = summary_data.get("market_env_tag", "未知")

        content = f"""## 🎯 今日执行摘要

> **市场环境**: {market_env}
> **操作建议**: {today_action}

**重点关注**: {focus}

**规避方向**: {avoid}
"""

        return await self.wecom.send_markdown(content)

    async def notify_daily_report(self, report_data: Dict) -> bool:
        """
        推送每日报告（完整版）

        Args:
            report_data: 完整分析数据
        """
        market_env = report_data.get("market_env", {})
        sector_scan = report_data.get("sector_scan", {})
        stock_pools = report_data.get("stock_pools", {})
        summary = report_data.get("summary", {})

        env_tag = market_env.get("market_env_tag", "未知")
        today_action = summary.get("today_action", "待定")
        focus = summary.get("focus", "无")

        # 板块
        mainline = sector_scan.get("mainline_count", 0)

        # 三池
        market_count = stock_pools.get("market_watch_count", 0)
        account_count = stock_pools.get("account_executable_count", 0)

        content = f"""## 📈 轻舟版交易系统 - 每日报告

### 市场环境
- 环境: **{env_tag}**
- 建议: **{today_action}**

### 板块扫描
- 主线板块: **{mainline}** 个

### 三池分类
- 市场观察池: **{market_count}** 只
- 账户可参与池: **{account_count}** 只

### 今日重点
{focus}
"""

        return await self.wecom.send_markdown(content)


# 全局通知服务实例
notify_service = NotifyService()
