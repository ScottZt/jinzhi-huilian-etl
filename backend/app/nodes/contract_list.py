"""合约列表节点 — 从缓存或天勤同步获取合约列表，输出 DataFrame 供下游消费。

输出列：symbol, product, exchange, name, type, is_main, main_symbol
可与 source_fetch 节点串联：合约列表 → 数据拉取。
"""

import pandas as pd

from app.core.workflow_engine import BaseNode
from app.core import contract_list_manager


class ContractListNode(BaseNode):
    node_type = "contract_list"
    display_name = "合约列表"
    category = "数据接入"
    params_schema = {
        "market_type": {
            "type": "select",
            "label": "合约类型",
            "options": ["all", "futures", "main_continuous"],
            "default": "all",
        },
        "product": {
            "type": "text",
            "label": "品种前缀（逗号分隔，留空=全部）",
            "default": "",
            "placeholder": "IF,rb,I",
        },
        "exchange": {
            "type": "select",
            "label": "交易所过滤",
            "options": ["", "CFFEX", "SHFE", "DCE", "CZCE", "INE", "GFEX"],
            "default": "",
        },
        "search": {
            "type": "text",
            "label": "搜索关键词",
            "default": "",
            "placeholder": "螺纹/IF/沪深",
        },
        "limit": {
            "type": "number",
            "label": "最大返回数量",
            "default": 500,
        },
        "auto_sync": {
            "type": "checkbox",
            "label": "自动同步（从TqSdk更新）",
            "default": False,
        },
        "credential_id": {
            "type": "text",
            "label": "天勤凭证ID（同步时使用）",
            "default": "",
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        market_type = str(params.get("market_type", "all")).strip()
        product_filter = str(params.get("product", "")).strip()
        exchange_filter = str(params.get("exchange", "")).strip()
        search_query = str(params.get("search", "")).strip()
        limit = int(params.get("limit", 500) or 500)
        auto_sync = params.get("auto_sync", False)

        # 自动同步
        if auto_sync:
            cred_id = str(params.get("credential_id", "")).strip()
            user, password = self._resolve_credentials(cred_id)
            if user and password:
                contract_list_manager.sync_contracts(user, password)

        # 获取合约列表
        if search_query:
            contracts = contract_list_manager.search_contracts(
                search_query, limit=limit, market_type="" if market_type == "all" else market_type
            )
        elif product_filter:
            all_contracts = []
            products = [p.strip().upper() for p in product_filter.split(",") if p.strip()]
            for product in products:
                all_contracts.extend(contract_list_manager.get_by_product(product))
            contracts = all_contracts[:limit]
        else:
            data = contract_list_manager.get_contracts()
            contracts = data.get("contracts", [])[:limit]

        if not contracts:
            return pd.DataFrame(columns=["symbol", "product", "exchange", "name", "type", "is_main", "main_symbol"])

        result = pd.DataFrame(contracts)

        # 过滤
        if market_type and market_type != "all" and "type" in result.columns:
            result = result[result["type"] == market_type]

        if exchange_filter and "exchange" in result.columns:
            result = result[result["exchange"].str.upper() == exchange_filter.upper()]

        # 确保必要列存在
        for col in ["symbol", "product", "exchange", "name", "type", "is_main", "main_symbol"]:
            if col not in result.columns:
                result[col] = ""

        return result[["symbol", "product", "exchange", "name", "type", "is_main", "main_symbol"]].reset_index(drop=True)

    def _resolve_credentials(self, cred_id: str) -> tuple[str, str]:
        """从凭证系统解析天勤账号。"""
        if not cred_id:
            return "", ""
        try:
            from app.persistence import sqlite_repo
            from app.core.credential_manager import decrypt_credential

            cred = sqlite_repo.get_credential(cred_id)
            if not cred:
                return "", ""
            raw_cfg = cred.get("config", {})
            if isinstance(raw_cfg, dict) and "_encrypted" in raw_cfg:
                cfg = decrypt_credential(raw_cfg["_encrypted"])
            else:
                cfg = raw_cfg
            return cfg.get("username", ""), cfg.get("password", "")
        except Exception:
            return "", ""
