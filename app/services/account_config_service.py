"""
账户与 LLM 配置读写（PostgreSQL account_config 表）
"""
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from loguru import logger

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.account_config import AccountConfig

SINGLETON_ID = 1
_last_good_llm_runtime_config: Optional[Dict[str, Any]] = None


def _default_config() -> Dict[str, Any]:
    return {
        "total_asset": float(settings.qingzhou_total_asset),
        "llm_enabled": bool(settings.llm_enabled),
        "llm_provider": settings.llm_provider,
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "llm_timeout_seconds": float(settings.llm_timeout_seconds),
        "llm_temperature": float(settings.llm_temperature),
        "llm_max_input_items": int(settings.llm_max_input_items),
        "llm_has_api_key": bool(settings.llm_api_key.strip()),
        "updated_at": None,
    }


def _serialize_config(row: AccountConfig) -> Dict[str, Any]:
    return {
        "total_asset": float(row.total_asset),
        "llm_enabled": bool(row.llm_enabled),
        "llm_provider": row.llm_provider or "custom",
        "llm_base_url": row.llm_base_url or "",
        "llm_model": row.llm_model or "",
        "llm_timeout_seconds": float(row.llm_timeout_seconds),
        "llm_temperature": float(row.llm_temperature),
        "llm_max_input_items": int(row.llm_max_input_items),
        "llm_has_api_key": bool((row.llm_api_key or "").strip()),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _env_runtime_config() -> Dict[str, Any]:
    return {
        "enabled": bool(settings.llm_enabled),
        "provider": settings.llm_provider,
        "base_url": settings.llm_base_url,
        "api_key": settings.llm_api_key,
        "model": settings.llm_model,
        "timeout_seconds": float(settings.llm_timeout_seconds),
        "temperature": float(settings.llm_temperature),
        "max_input_items": int(settings.llm_max_input_items),
    }


def _runtime_config_from_row(row: AccountConfig) -> Dict[str, Any]:
    api_key = (row.llm_api_key or "").strip() or settings.llm_api_key
    base_url = (row.llm_base_url or "").strip() or settings.llm_base_url
    model = (row.llm_model or "").strip() or settings.llm_model
    return {
        "enabled": bool(row.llm_enabled),
        "provider": (row.llm_provider or "").strip() or settings.llm_provider,
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "timeout_seconds": float(row.llm_timeout_seconds or settings.llm_timeout_seconds),
        "temperature": float(row.llm_temperature if row.llm_temperature is not None else settings.llm_temperature),
        "max_input_items": int(row.llm_max_input_items or settings.llm_max_input_items),
    }


def _apply_config_update(
    row: AccountConfig,
    *,
    total_asset: Optional[float] = None,
    llm_enabled: Optional[bool] = None,
    llm_provider: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    clear_llm_api_key: bool = False,
    llm_model: Optional[str] = None,
    llm_timeout_seconds: Optional[float] = None,
    llm_temperature: Optional[float] = None,
    llm_max_input_items: Optional[int] = None,
) -> None:
    if total_asset is not None:
        if total_asset <= 0:
            raise ValueError("总资产必须大于 0")
        row.total_asset = float(total_asset)

    if llm_enabled is not None:
        row.llm_enabled = bool(llm_enabled)
    if llm_provider is not None:
        row.llm_provider = llm_provider.strip() or "custom"
    if llm_base_url is not None:
        row.llm_base_url = llm_base_url.strip()
    if llm_model is not None:
        row.llm_model = llm_model.strip()
    if llm_timeout_seconds is not None:
        if llm_timeout_seconds <= 0:
            raise ValueError("模型超时必须大于 0")
        row.llm_timeout_seconds = float(llm_timeout_seconds)
    if llm_temperature is not None:
        if llm_temperature < 0 or llm_temperature > 2:
            raise ValueError("模型温度需在 0 到 2 之间")
        row.llm_temperature = float(llm_temperature)
    if llm_max_input_items is not None:
        if llm_max_input_items < 1 or llm_max_input_items > 20:
            raise ValueError("单次最大输入条数需在 1 到 20 之间")
        row.llm_max_input_items = int(llm_max_input_items)

    if clear_llm_api_key:
        row.llm_api_key = ""
    elif llm_api_key is not None:
        row.llm_api_key = llm_api_key.strip()

    row.updated_at = datetime.utcnow()


async def get_total_asset() -> float:
    """读取配置中的总资产（元）；无记录时回退到 settings.qingzhou_total_asset。"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(AccountConfig).where(AccountConfig.id == SINGLETON_ID)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return float(row.total_asset)
        return float(settings.qingzhou_total_asset)


async def get_config() -> Dict[str, Any]:
    """返回当前账户与 LLM 配置。"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(AccountConfig).where(AccountConfig.id == SINGLETON_ID)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return _default_config()
        return _serialize_config(row)


async def get_llm_runtime_config() -> Dict[str, Any]:
    """返回运行时使用的 LLM 配置，优先数据库，其次 env 默认值。"""
    global _last_good_llm_runtime_config
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(AccountConfig).where(AccountConfig.id == SINGLETON_ID)
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise RuntimeError("account_config not initialized")
            runtime = _runtime_config_from_row(row)
            _last_good_llm_runtime_config = dict(runtime)
            return runtime
    except Exception as exc:
        logger.warning(f"读取 LLM 运行时配置失败，尝试回退缓存: {exc}")
        if _last_good_llm_runtime_config is not None:
            return dict(_last_good_llm_runtime_config)
        return _env_runtime_config()


async def update_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """更新账户与 LLM 配置。"""
    global _last_good_llm_runtime_config
    async with async_session_factory() as session:
        result = await session.execute(
            select(AccountConfig).where(AccountConfig.id == SINGLETON_ID)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = AccountConfig(
                id=SINGLETON_ID,
                total_asset=float(settings.qingzhou_total_asset),
                llm_enabled=bool(settings.llm_enabled),
                llm_provider=settings.llm_provider,
                llm_base_url=settings.llm_base_url,
                llm_api_key=settings.llm_api_key,
                llm_model=settings.llm_model,
                llm_timeout_seconds=float(settings.llm_timeout_seconds),
                llm_temperature=float(settings.llm_temperature),
                llm_max_input_items=int(settings.llm_max_input_items),
                updated_at=datetime.utcnow(),
            )
            session.add(row)

        _apply_config_update(
            row,
            total_asset=payload.get("total_asset"),
            llm_enabled=payload.get("llm_enabled"),
            llm_provider=payload.get("llm_provider"),
            llm_base_url=payload.get("llm_base_url"),
            llm_api_key=payload.get("llm_api_key"),
            clear_llm_api_key=bool(payload.get("clear_llm_api_key")),
            llm_model=payload.get("llm_model"),
            llm_timeout_seconds=payload.get("llm_timeout_seconds"),
            llm_temperature=payload.get("llm_temperature"),
            llm_max_input_items=payload.get("llm_max_input_items"),
        )

        await session.commit()
        await session.refresh(row)
        _last_good_llm_runtime_config = _runtime_config_from_row(row)
        return _serialize_config(row)


async def update_total_asset(total_asset: float) -> Dict[str, Any]:
    """兼容旧接口：仅更新总资产。"""
    return await update_config({"total_asset": total_asset})
