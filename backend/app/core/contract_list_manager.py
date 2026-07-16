"""合约列表管理器 — 从天勤同步在市合约、缓存、搜索。

核心功能：
- sync(): 连接天勤 API，遍历全品种获取在市合约列表 + 主力连续合约
- get(): 读取缓存的合约列表
- search(): 模糊搜索（代码/名称/品种/交易所）
- get_main_contracts(): 获取各品种当前主力合约

缓存位置：shared/contracts.json
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.markets import (
    _PRODUCT_SPECS,
    _TQ_VARIETY_CASE,
    get_all_prefixes,
    get_tq_variety_case,
)

logger = logging.getLogger("ContractListManager")

# 缓存文件放在 shared 目录（与数据库同级）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED_DIR = os.path.join(_PROJECT_ROOT, "..", "shared")
_CONTRACTS_FILE = os.path.join(_SHARED_DIR, "contracts.json")

_lock = threading.Lock()
_cached_contracts: List[Dict[str, Any]] = []
_last_sync_time: Optional[str] = None


def _load_cached() -> List[Dict[str, Any]]:
    """从文件加载缓存。"""
    global _cached_contracts, _last_sync_time
    if not os.path.exists(_CONTRACTS_FILE):
        return []
    try:
        with open(_CONTRACTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cached_contracts = data.get("contracts", [])
        _last_sync_time = data.get("synced_at", "")
        return _cached_contracts
    except Exception as e:
        logger.error("加载合约缓存失败: %s", e)
        return []


def _save_cached(contracts: List[Dict[str, Any]]):
    """保存合约列表到文件。"""
    global _cached_contracts, _last_sync_time
    _cached_contracts = contracts
    _last_sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(os.path.dirname(_CONTRACTS_FILE), exist_ok=True)
        data = {
            "contracts": contracts,
            "synced_at": _last_sync_time,
            "count": len(contracts),
        }
        with open(_CONTRACTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("合约列表已保存: %d 条", len(contracts))
    except Exception as e:
        logger.error("保存合约缓存失败: %s", e)


def get_contracts() -> Dict[str, Any]:
    """获取缓存的合约列表。"""
    with _lock:
        contracts = _load_cached()
    return {
        "contracts": contracts,
        "synced_at": _last_sync_time,
        "count": len(contracts),
    }


def search_contracts(query: str, limit: int = 50, market_type: str = "") -> List[Dict[str, Any]]:
    """
    模糊搜索合约列表。

    支持匹配：合约代码、品种名称、品种前缀、交易所。
    market_type 过滤：futures / main_continuous / 空=全部。
    """
    with _lock:
        contracts = _load_cached()

    if not query and not market_type:
        return contracts[:limit]

    query_lower = query.lower().strip()
    results = []

    for c in contracts:
        if market_type and c.get("type") != market_type:
            continue
        if not query_lower:
            results.append(c)
            continue

        symbol = str(c.get("symbol", "")).lower()
        name = str(c.get("name", "")).lower()
        product = str(c.get("product", "")).lower()
        exchange = str(c.get("exchange", "")).lower()

        if query_lower in symbol or query_lower in name or query_lower in product or query_lower in exchange:
            results.append(c)

    return results[:limit]


def get_main_contracts() -> List[Dict[str, Any]]:
    """获取各品种当前主力合约（仅 main_continuous 类型）。"""
    with _lock:
        contracts = _load_cached()
    return [c for c in contracts if c.get("type") == "main_continuous"]


def get_by_product(product: str) -> List[Dict[str, Any]]:
    """按品种前缀筛选合约。"""
    product_upper = product.upper()
    with _lock:
        contracts = _load_cached()
    return [c for c in contracts if c.get("product", "").upper() == product_upper]


def sync_contracts(tqsdk_user: str = "", tqsdk_password: str = "") -> Dict[str, Any]:
    """
    从天勤同步在市合约列表。

    流程：
    1. 连接 TqSdk API
    2. 遍历全品种，query_quotes 获取在市合约
    3. 查询各品种主力连续合约（KQ.m@）
    4. 获取主力对应的具体合约代码（underlying_symbol）
    5. 排序 + 缓存
    """
    if not tqsdk_user or not tqsdk_password:
        return {"status": "error", "msg": "天勤账号未配置"}

    try:
        from tqsdk import TqApi, TqAuth
    except ImportError:
        return {"status": "error", "msg": "tqsdk 未安装，请执行: pip install tqsdk"}

    # 屏蔽天勤 SDK 的冗余日志（模拟账户初始化信息等）
    import logging
    logging.getLogger("tqsdk").setLevel(logging.WARNING)

    all_contracts: List[Dict[str, Any]] = []
    seen_symbols: set = set()
    products_main: Dict[str, str] = {}

    # 线程超时保护
    api_holder = [None]
    error_holder = [None]

    def _connect():
        try:
            api_holder[0] = TqApi(auth=TqAuth(tqsdk_user, tqsdk_password))
        except Exception as e:
            error_holder[0] = e

    thread = threading.Thread(target=_connect, daemon=True)
    thread.start()
    thread.join(timeout=15)

    if thread.is_alive():
        return {"status": "error", "msg": "天勤连接超时（15秒）"}
    if error_holder[0] is not None:
        return {"status": "error", "msg": f"天勤连接失败: {error_holder[0]}"}

    api = api_holder[0]
    if api is None:
        return {"status": "error", "msg": "天勤 API 创建失败"}

    try:
        tq_case = get_tq_variety_case()

        for prefix in get_all_prefixes():
            spec = _PRODUCT_SPECS.get(prefix, {})
            exchange = spec.get("exchange", "")

            try:
                # 获取在市具体合约
                if exchange:
                    quotes = api.query_quotes(
                        ins_class="FUTURE",
                        product_id=prefix.upper(),
                        exchange_id=exchange,
                        expired=False,
                    )
                else:
                    quotes = api.query_quotes(
                        ins_class="FUTURE",
                        product_id=prefix.upper(),
                        expired=False,
                    )

                if quotes:
                    for symbol in quotes:
                        if symbol not in seen_symbols:
                            seen_symbols.add(symbol)
                            sym_exchange = symbol.split(".")[0] if "." in symbol else exchange
                            all_contracts.append({
                                "symbol": symbol,
                                "product": prefix.upper(),
                                "exchange": sym_exchange,
                                "name": spec.get("name", prefix),
                                "type": "futures",
                            })

                # 主力连续合约
                tq_variety = tq_case.get(prefix.upper(), prefix.lower())
                kq_symbol = f"KQ.m@{exchange}.{tq_variety}" if exchange else ""
                if kq_symbol and kq_symbol not in seen_symbols:
                    seen_symbols.add(kq_symbol)
                    all_contracts.append({
                        "symbol": kq_symbol,
                        "product": prefix.upper(),
                        "exchange": exchange,
                        "name": spec.get("name", prefix),
                        "type": "main_continuous",
                    })
                    products_main[prefix.upper()] = (exchange, kq_symbol)

            except Exception as e:
                logger.debug("获取 %s 合约失败: %s", prefix, e)
                continue

        # 批量查各品种当前主力对应的具体合约
        main_symbol_map: Dict[str, str] = {}
        for product, (exch, kq_sym) in products_main.items():
            try:
                quote = api.get_quote(kq_sym)
                underlying = str(getattr(quote, "underlying_symbol", "") or "")
                if underlying:
                    main_symbol_map[product] = underlying
            except Exception:
                pass

    finally:
        try:
            api.close()
        except Exception:
            pass

    # 补充主力标记
    for c in all_contracts:
        product = c.get("product", "")
        main_sym = main_symbol_map.get(product, "")
        if c.get("type") == "main_continuous":
            c["main_symbol"] = main_sym
            c["is_main"] = False
        else:
            c["is_main"] = bool(main_sym and c.get("symbol") == main_sym)

    # 排序：按品种聚合，主连在前，其余按 symbol 升序
    def sort_key(c):
        return (
            c.get("product", ""),
            0 if c.get("type") == "main_continuous" else 1,
            c.get("symbol", ""),
        )

    all_contracts.sort(key=sort_key)

    with _lock:
        _save_cached(all_contracts)

    return {
        "status": "success",
        "count": len(all_contracts),
        "synced_at": _last_sync_time,
        "contracts": all_contracts[:50],
    }


# 启动时加载缓存
_load_cached()
