"""
LLM 客户端

仅作为解释增强层使用，不参与核心交易规则裁决。
"""
import json
import time
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from app.core.config import settings
from app.models.schemas import LlmCallStatus
from app.services.llm_call_log_service import llm_call_log_service
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
        request_label: str = "",
        timeout_seconds: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """请求模型并解析 JSON 响应。"""
        data, _status = await self.chat_json_with_status(
            system_prompt,
            user_payload,
            temperature=temperature,
            request_label=request_label,
            timeout_seconds=timeout_seconds,
        )
        return data

    async def chat_json_with_status(
        self,
        system_prompt: str,
        user_payload: Dict[str, Any],
        *,
        scene: str = "",
        trade_date: str = "",
        temperature: Optional[float] = None,
        request_label: str = "",
        timeout_seconds: Optional[float] = None,
    ) -> tuple[Optional[Dict[str, Any]], LlmCallStatus]:
        """请求模型并返回 JSON 结果与状态。"""
        runtime = await self.get_runtime_config()
        request_body = json.dumps(user_payload, ensure_ascii=False)
        provider = str(runtime.get("provider") or "")
        model = str(runtime.get("model") or "")
        request_chars = len(system_prompt) + len(request_body)
        started = time.perf_counter()

        def _with_label(message: str) -> str:
            if not request_label:
                return message
            return f"{message} [{request_label}]"

        async def _record(
            status: LlmCallStatus,
            response_chars: int = 0,
        ) -> None:
            if not scene:
                return
            await llm_call_log_service.record_call(
                scene=scene,
                trade_date=trade_date,
                provider=provider,
                model=model,
                status=status,
                request_chars=request_chars,
                response_chars=response_chars,
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        if not (
            runtime.get("enabled")
            and str(runtime.get("api_key") or "").strip()
            and str(runtime.get("model") or "").strip()
            and str(runtime.get("base_url") or "").strip()
        ):
            status = LlmCallStatus(
                enabled=False,
                success=False,
                status="disabled",
                message=_with_label(
                    "LLM 未启用或缺少 API Key / 模型 / Base URL 配置"
                ),
            )
            await _record(status)
            return None, status

        url = f"{str(runtime.get('base_url')).rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {runtime.get('api_key')}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": runtime.get("model"),
            "temperature": (
                runtime.get("temperature")
                if temperature is None
                else temperature
            ),
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": request_body,
                },
            ],
        }

        try:
            if timeout_seconds is not None:
                timeout = float(timeout_seconds)
            else:
                timeout = float(
                    runtime.get("timeout_seconds")
                    or settings.llm_timeout_seconds
                )
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = (
                exc.response.text[:240]
                if exc.response is not None
                else str(exc)
            )
            logger.warning(f"LLM HTTP 请求失败: {detail}")
            status = LlmCallStatus(
                enabled=True,
                success=False,
                status="http_error",
                message=_with_label(f"模型接口返回错误：{detail}"),
            )
            await _record(status, response_chars=len(detail))
            return None, status
        except httpx.TimeoutException:
            logger.warning("LLM 请求超时")
            status = LlmCallStatus(
                enabled=True,
                success=False,
                status="timeout",
                message=_with_label("模型请求超时"),
            )
            await _record(status)
            return None, status
        except Exception as exc:
            logger.warning(f"LLM 请求失败: {exc}")
            status = LlmCallStatus(
                enabled=True,
                success=False,
                status="request_error",
                message=_with_label(f"模型请求失败：{exc}"),
            )
            await _record(status)
            return None, status

        try:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            parsed = json.loads(content)
            status = LlmCallStatus(
                enabled=True,
                success=True,
                status="success",
                message=_with_label("LLM 解释增强已生效"),
            )
            await _record(status, response_chars=len(content))
            return parsed, status
        except Exception as exc:
            logger.warning(f"LLM 响应解析失败: {exc}")
            status = LlmCallStatus(
                enabled=True,
                success=False,
                status="parse_error",
                message=_with_label(f"模型响应解析失败：{exc}"),
            )
            await _record(status)
            return None, status


llm_client = LlmClient()
