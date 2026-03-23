"""
LLM 客户端

仅作为解释增强层使用，不参与核心交易规则裁决。
"""
import json
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from app.core.config import settings
from app.models.schemas import LlmCallStatus
from app.services.account_config_service import get_llm_runtime_config


class LlmClient:
    """OpenAI 兼容接口客户端。"""

    def is_enabled(self) -> bool:
        return bool(
            settings.llm_enabled
            and settings.llm_api_key.strip()
            and settings.llm_model.strip()
            and settings.llm_base_url.strip()
        )

    async def get_runtime_config(self) -> Dict[str, Any]:
        """读取运行时配置，优先数据库。"""
        return await get_llm_runtime_config()

    async def chat_json(
        self,
        system_prompt: str,
        user_payload: Dict[str, Any],
        *,
        temperature: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """请求模型并解析 JSON 响应。"""
        data, _status = await self.chat_json_with_status(
            system_prompt,
            user_payload,
            temperature=temperature,
        )
        return data

    async def chat_json_with_status(
        self,
        system_prompt: str,
        user_payload: Dict[str, Any],
        *,
        temperature: Optional[float] = None,
    ) -> tuple[Optional[Dict[str, Any]], LlmCallStatus]:
        """请求模型并返回 JSON 结果与状态。"""
        runtime = await self.get_runtime_config()
        if not (
            runtime.get("enabled")
            and str(runtime.get("api_key") or "").strip()
            and str(runtime.get("model") or "").strip()
            and str(runtime.get("base_url") or "").strip()
        ):
            return None, LlmCallStatus(
                enabled=False,
                success=False,
                status="disabled",
                message="LLM 未启用或缺少 API Key / 模型 / Base URL 配置",
            )

        url = f"{str(runtime.get('base_url')).rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {runtime.get('api_key')}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": runtime.get("model"),
            "temperature": runtime.get("temperature") if temperature is None else temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=float(runtime.get("timeout_seconds") or settings.llm_timeout_seconds)) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:240] if exc.response is not None else str(exc)
            logger.warning(f"LLM HTTP 请求失败: {detail}")
            return None, LlmCallStatus(
                enabled=True,
                success=False,
                status="http_error",
                message=f"模型接口返回错误：{detail}",
            )
        except httpx.TimeoutException:
            logger.warning("LLM 请求超时")
            return None, LlmCallStatus(
                enabled=True,
                success=False,
                status="timeout",
                message="模型请求超时",
            )
        except Exception as exc:
            logger.warning(f"LLM 请求失败: {exc}")
            return None, LlmCallStatus(
                enabled=True,
                success=False,
                status="request_error",
                message=f"模型请求失败：{exc}",
            )

        try:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            return json.loads(content), LlmCallStatus(
                enabled=True,
                success=True,
                status="success",
                message="LLM 解释增强已生效",
            )
        except Exception as exc:
            logger.warning(f"LLM 响应解析失败: {exc}")
            return None, LlmCallStatus(
                enabled=True,
                success=False,
                status="parse_error",
                message=f"模型响应解析失败：{exc}",
            )


llm_client = LlmClient()
