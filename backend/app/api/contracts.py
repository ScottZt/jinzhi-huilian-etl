"""合约列表 API — 查询/搜索/同步/品种规格。"""
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.core import contract_list_manager
from app.markets import get_all_prefixes, get_all_specs, get_exchanges, resolve, get_product_name
from app.persistence import sqlite_repo
from app.core.credential_manager import decrypt_credential

router = APIRouter()


class SyncRequest(BaseModel):
    credential_id: Optional[str] = None
    tqsdk_user: Optional[str] = None
    tqsdk_password: Optional[str] = None


def _resolve_credentials(req: SyncRequest) -> tuple[str, str]:
    """从请求或凭证系统解析天勤账号。"""
    user = (req.tqsdk_user or "").strip()
    password = (req.tqsdk_password or "").strip()
    if user and password:
        return user, password

    if req.credential_id:
        cred = sqlite_repo.get_credential(req.credential_id)
        if cred:
            raw_cfg = cred.get("config", {})
            if isinstance(raw_cfg, dict) and "_encrypted" in raw_cfg:
                cfg = decrypt_credential(raw_cfg["_encrypted"])
            else:
                cfg = raw_cfg
            return cfg.get("username", ""), cfg.get("password", "")

    return "", ""


@router.get("/")
async def list_contracts(q: str = "", limit: int = 100, market_type: str = ""):
    """获取合约列表（支持模糊搜索和类型过滤）。"""
    contracts = contract_list_manager.search_contracts(q, limit=limit, market_type=market_type)
    return {
        "status": "success",
        "contracts": contracts,
        "count": len(contracts),
        "synced_at": contract_list_manager._last_sync_time or "",
    }


@router.get("/main")
async def get_main_contracts():
    """获取各品种主力合约列表。"""
    contracts = contract_list_manager.get_main_contracts()
    return {"status": "success", "contracts": contracts, "count": len(contracts)}


@router.get("/product/{product}")
async def get_by_product(product: str):
    """按品种前缀查询合约列表。"""
    contracts = contract_list_manager.get_by_product(product)
    return {"status": "success", "contracts": contracts, "count": len(contracts)}


@router.post("/sync")
async def sync_contracts(req: SyncRequest = None):
    """从天勤同步在市合约列表。"""
    if req is None:
        req = SyncRequest()
    user, password = _resolve_credentials(req)
    if not user or not password:
        return {"status": "error", "msg": "请提供天勤账号（通过凭证或手动填写）"}
    result = await asyncio.to_thread(contract_list_manager.sync_contracts, user, password)
    return result


@router.get("/products")
async def list_products():
    """获取全品种规格表（含交易所、名称、合约乘数等）。"""
    specs = get_all_specs()
    result = []
    for prefix, spec in specs.items():
        result.append({
            "prefix": prefix,
            "exchange": spec.get("exchange", ""),
            "name": spec.get("name", ""),
            "multiplier": spec.get("multiplier", 1),
            "margin_rate": spec.get("margin_rate", 0),
            "tick_size": spec.get("tick_size", 0.01),
        })
    return {"products": result, "count": len(result)}


@router.get("/exchanges")
async def list_exchanges():
    """获取已注册的交易所列表。"""
    return {"exchanges": get_exchanges()}


@router.get("/spec/{symbol}")
async def get_spec(symbol: str):
    """查询合约的品种规格。"""
    spec = resolve(symbol)
    return {
        "symbol": symbol,
        "prefix": spec.symbol_prefix,
        "exchange": spec.exchange,
        "name": spec.name,
        "multiplier": spec.multiplier,
        "margin_rate": spec.margin_rate,
        "tick_size": spec.tick_size,
    }
