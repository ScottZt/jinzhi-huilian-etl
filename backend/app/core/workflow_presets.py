"""预制工作流与样例数据。"""
from typing import Any, Dict, List


def _build_kline_sample() -> List[Dict[str, Any]]:
    """构造 1 分钟 K 线样例数据，用于重采样和指标计算。"""
    rows: List[Dict[str, Any]] = []
    base_price = 10.0
    for i in range(60):
        minute = f"{30 + i:02d}"
        dt = f"2026-01-05 09:{minute}" if i < 30 else f"2026-01-05 10:{i - 30:02d}"
        close = round(base_price + (i * 0.03), 2)
        rows.append(
            {
                "code": "000001.SZ",
                "dt": dt,
                "open": round(close - 0.05, 2),
                "high": round(close + 0.08, 2),
                "low": round(close - 0.1, 2),
                "close": close,
                "vol": 1000 + i * 5,
                "amount": round((1000 + i * 5) * close, 2),
            }
        )
    return rows


def _build_trade_sample() -> List[Dict[str, Any]]:
    """构造成交明细样例数据，用于清洗、计算和过滤。"""
    return [
        {"symbol": "IF2406", "price": 4123.2, "qty": 2, "side": "BUY"},
        {"symbol": "IF2406", "price": 4123.6, "qty": 1, "side": "SELL"},
        {"symbol": "IC2406", "price": 5890.0, "qty": 3, "side": "BUY"},
        {"symbol": "IC2406", "price": 5888.2, "qty": 1, "side": "BUY"},
        {"symbol": "IH2406", "price": None, "qty": 2, "side": "SELL"},
    ]


def _build_tick_sample() -> List[Dict[str, Any]]:
    """构造 Tick 样例数据，用于排序、分组聚合。"""
    return [
        {"code": "600000.SH", "trade_date": "2026-01-05", "price": 10.1, "vol": 120},
        {"code": "600000.SH", "trade_date": "2026-01-05", "price": 10.2, "vol": 80},
        {"code": "600000.SH", "trade_date": "2026-01-06", "price": 10.4, "vol": 100},
        {"code": "000001.SZ", "trade_date": "2026-01-05", "price": 12.3, "vol": 90},
        {"code": "000001.SZ", "trade_date": "2026-01-06", "price": 12.6, "vol": 110},
        {"code": "000001.SZ", "trade_date": "2026-01-06", "price": 12.7, "vol": 60},
    ]


def get_workflow_presets() -> List[Dict[str, Any]]:
    """返回内置预制工作流。"""
    return [
        {
            "key": "kline_resample_indicators",
            "name": "预制：分钟K线重采样 + MA + MACD",
            "description": "1分钟K线 -> 30分钟 -> MA(5,10) -> MACD -> 过滤 close 非空",
            "workflow_json": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "重采样30min",
                        "type": "resample",
                        "parameters": {"rule": "30min", "time_column": "dt", "group_column": "code"},
                    },
                    {
                        "id": "n2",
                        "name": "计算MA",
                        "type": "ma",
                        "parameters": {"windows": "5,10", "source_column": "close", "use_ema": False},
                    },
                    {
                        "id": "n3",
                        "name": "计算MACD",
                        "type": "macd",
                        "parameters": {"fast": 12, "slow": 26, "signal": 9, "source_column": "close"},
                    },
                    {
                        "id": "n4",
                        "name": "过滤空值",
                        "type": "filter",
                        "parameters": {
                            "mode": "keep",
                            "conditions": [{"column": "close", "operator": "is_not_null", "value": ""}],
                        },
                    },
                ],
                "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"]},
            },
            "sample_data": _build_kline_sample(),
        },
        {
            "key": "trade_cleaning_enrichment",
            "name": "预制：成交明细清洗 + 金额计算 + 条件分支",
            "description": "重命名字段 -> 计算 amount -> 过滤空价格 -> 保留 BUY 方向",
            "workflow_json": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "字段重命名",
                        "type": "column_rename",
                        "parameters": {"renames": "symbol=code,price=close,qty=volume"},
                    },
                    {
                        "id": "n2",
                        "name": "金额计算",
                        "type": "expression",
                        "parameters": {"target_column": "amount", "expression": "close * volume"},
                    },
                    {
                        "id": "n3",
                        "name": "过滤空价格",
                        "type": "filter",
                        "parameters": {
                            "mode": "keep",
                            "conditions": [{"column": "close", "operator": "is_not_null", "value": ""}],
                        },
                    },
                    {
                        "id": "n4",
                        "name": "保留买单",
                        "type": "condition",
                        "parameters": {"condition": "side == 'BUY'", "branch": "true"},
                    },
                ],
                "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"]},
            },
            "sample_data": _build_trade_sample(),
        },
        {
            "key": "tick_sort_group",
            "name": "预制：Tick排序 + 分组汇总",
            "description": "按股票/日期排序，再按股票和日期聚合 volume 与 price",
            "workflow_json": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "排序",
                        "type": "sort",
                        "parameters": {"by": "code,trade_date", "ascending": True},
                    },
                    {
                        "id": "n2",
                        "name": "分组聚合",
                        "type": "group_by",
                        "parameters": {"group_by": "code,trade_date", "aggregations": "vol=sum,price=last"},
                    },
                ],
                "connections": {"n1": ["n2"]},
            },
            "sample_data": _build_tick_sample(),
        },
    ]
