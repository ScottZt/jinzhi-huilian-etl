"""预制ETL工作流。

两种模式：
  纯 Transform (4个): 被 Pipeline 引用，Pipeline 管理 Source/Target
  完整闭环 (2个): Source+Transform+Target，Pipeline 只做调度

分层职责：
  Pipeline(数据流): Source → 目标库连接 → 写入策略 → 调度
  Workflow(ETL):    清洗 → 计算 → 指标 → 过滤 → 聚合
"""
from typing import Any, Dict, List


def _build_kline_sample(rows: int = 60) -> List[Dict[str, Any]]:
    """构造 1 分钟 K 线样例数据。"""
    import random
    rows_out: List[Dict[str, Any]] = []
    base_price = 10.0
    for i in range(rows):
        minute = f"{30 + i:02d}"
        dt = f"2026-01-05 09:{minute}" if i < 30 else f"2026-01-05 10:{i - 30:02d}"
        close = round(base_price + (i * 0.03) + random.uniform(-0.05, 0.05), 2)
        rows_out.append(
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
    return rows_out


def _build_trade_sample() -> List[Dict[str, Any]]:
    """构造成交明细样例数据。"""
    return [
        {"symbol": "IF2406", "price": 4123.2, "qty": 2, "side": "BUY"},
        {"symbol": "IF2406", "price": 4123.6, "qty": 1, "side": "SELL"},
        {"symbol": "IC2406", "price": 5890.0, "qty": 3, "side": "BUY"},
        {"symbol": "IC2406", "price": 5888.2, "qty": 1, "side": "BUY"},
        {"symbol": "IH2406", "price": None, "qty": 2, "side": "SELL"},
    ]


def _build_tick_sample() -> List[Dict[str, Any]]:
    """构造 Tick 样例数据。"""
    return [
        {"code": "600000.SH", "trade_date": "2026-01-05", "price": 10.1, "vol": 120},
        {"code": "600000.SH", "trade_date": "2026-01-05", "price": 10.2, "vol": 80},
        {"code": "600000.SH", "trade_date": "2026-01-06", "price": 10.4, "vol": 100},
        {"code": "000001.SZ", "trade_date": "2026-01-05", "price": 12.3, "vol": 90},
        {"code": "000001.SZ", "trade_date": "2026-01-06", "price": 12.6, "vol": 110},
        {"code": "000001.SZ", "trade_date": "2026-01-06", "price": 12.7, "vol": 60},
    ]


def get_workflow_presets() -> List[Dict[str, Any]]:
    """返回内置ETL工作流。"""
    return [
        # ========== 纯 Transform 模式 (被 Pipeline 引用) ==========
        {
            "key": "kline_resample_indicators",
            "name": "分钟K线重采样 + MA + MACD",
            "description": "纯Transform: 原始1min → 重采样30min → MA(5,10) → MACD → 过滤空值",
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
            "sample_data": _build_kline_sample(rows=120),
        },
        {
            "key": "trade_cleaning_enrichment",
            "name": "成交明细清洗 + 金额计算",
            "description": "纯Transform: 列重命名 → 计算金额 → 过滤空值 → 条件筛选",
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
                        "name": "计算金额",
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
            "key": "full_indicators_pipeline",
            "name": "全指标流水线 (MA+EMA+MACD+RSI+BOLL)",
            "description": "纯Transform: MA → EMA → MACD → RSI → BOLL → 综合过滤",
            "workflow_json": {
                "nodes": [
                    {"id": "n1", "name": "MA均线", "type": "ma",
                     "parameters": {"windows": "5,10,20", "source_column": "close", "use_ema": False}},
                    {"id": "n2", "name": "EMA均线", "type": "ma",
                     "parameters": {"windows": "12,26", "source_column": "close", "use_ema": True}},
                    {"id": "n3", "name": "MACD", "type": "macd",
                     "parameters": {"fast": 12, "slow": 26, "signal": 9, "source_column": "close"}},
                    {"id": "n4", "name": "RSI", "type": "rsi",
                     "parameters": {"window": 14, "source_column": "close"}},
                    {"id": "n5", "name": "布林带", "type": "boll",
                     "parameters": {"window": 20, "std_mult": 2, "source_column": "close"}},
                    {"id": "n6", "name": "综合过滤", "type": "filter",
                     "parameters": {
                         "mode": "keep",
                         "conditions": [
                             {"column": "rsi", "operator": "is_not_null", "value": ""},
                             {"column": "macd", "operator": "is_not_null", "value": ""},
                             {"column": "boll_mid", "operator": "is_not_null", "value": ""},
                         ],
                     }},
                ],
                "connections": {
                    "n1": ["n2"], "n2": ["n3"], "n3": ["n4"],
                    "n4": ["n5"], "n5": ["n6"],
                },
            },
            "sample_data": _build_kline_sample(rows=120),
        },
        {
            "key": "signal_expression_python",
            "name": "信号计算 + 条件分支 + 自定义脚本",
            "description": "纯Transform: 计算涨跌幅 → 筛选上涨 → 自定义Python信号标记",
            "workflow_json": {
                "nodes": [
                    {"id": "n1", "name": "涨跌幅", "type": "expression",
                     "parameters": {"target_column": "pct_change",
                                    "expression": "(df['close'] - df['open']) / df['open'] * 100"}},
                    {"id": "n2", "name": "筛选上涨", "type": "condition",
                     "parameters": {"condition": "df['pct_change'] > 0", "branch": "true"}},
                    {"id": "n3", "name": "信号标记", "type": "custom_python",
                     "parameters": {"code": "def process(df):\n    df['signal'] = 0\n    df.loc[df['pct_change'] > 2, 'signal'] = 1\n    df.loc[df['pct_change'] < -2, 'signal'] = -1\n    return df"}},
                ],
                "connections": {"n1": ["n2"], "n2": ["n3"]},
            },
            "sample_data": _build_kline_sample(),
        },

        # ========== 完整闭环模式 (独立运行) ==========
        {
            "key": "binance_kline_to_duckdb",
            "name": "Binance K线 → 指标计算 → DuckDB (完整闭环)",
            "description": "完整闭环: Binance拉取 → 重采样 → MA → MACD → 写入DuckDB，Pipeline只调度",
            "workflow_json": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "拉取Binance 1min",
                        "type": "source_fetch",
                        "parameters": {
                            "source_type": "binance",
                            "source_config": "{}",
                            "codes": "BTCUSDT,ETHUSDT",
                            "interval": "1min",
                            "time_mode": "lookback",
                            "lookback_days": 3,
                            "parallel": True,
                            "max_workers": 2,
                            "session_only": False,
                        },
                    },
                    {
                        "id": "n2",
                        "name": "重采样30min",
                        "type": "resample",
                        "parameters": {"rule": "30min", "time_column": "dt", "group_column": "code"},
                    },
                    {
                        "id": "n3",
                        "name": "计算MA",
                        "type": "ma",
                        "parameters": {"windows": "5,10", "source_column": "close", "use_ema": False},
                    },
                    {
                        "id": "n4",
                        "name": "计算MACD",
                        "type": "macd",
                        "parameters": {"fast": 12, "slow": 26, "signal": 9, "source_column": "close"},
                    },
                    {
                        "id": "n5",
                        "name": "过滤空值",
                        "type": "filter",
                        "parameters": {
                            "mode": "keep",
                            "conditions": [{"column": "close", "operator": "is_not_null", "value": ""}],
                        },
                    },
                    {
                        "id": "n6",
                        "name": "写入DuckDB",
                        "type": "target_write",
                        "parameters": {
                            "target_type": "duckdb",
                            "target_config": '{"db_path": "D:/data/etl_demo.db"}',
                            "target_table": "crypto_30min_indicators",
                            "batch_size": 5000,
                            "on_duplicate": "ignore",
                            "columns": "",
                        },
                    },
                ],
                "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"], "n4": ["n5"], "n5": ["n6"]},
            },
            "sample_data": _build_kline_sample(rows=120),
        },
        {
            "key": "yahoo_daily_to_duckdb",
            "name": "Yahoo Finance 日线 → 全指标 → DuckDB (完整闭环)",
            "description": "完整闭环: Yahoo拉取 → MA+EMA+MACD+RSI+BOLL → 综合过滤 → 写入DuckDB",
            "workflow_json": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "拉取Yahoo AAPL",
                        "type": "source_fetch",
                        "parameters": {
                            "source_type": "yfinance",
                            "source_config": "{}",
                            "codes": "AAPL",
                            "interval": "D",
                            "time_mode": "lookback",
                            "lookback_days": 365,
                            "parallel": False,
                            "session_only": False,
                        },
                    },
                    {"id": "n2", "name": "MA均线", "type": "ma",
                     "parameters": {"windows": "5,10,20", "source_column": "close", "use_ema": False}},
                    {"id": "n3", "name": "EMA均线", "type": "ma",
                     "parameters": {"windows": "12,26", "source_column": "close", "use_ema": True}},
                    {"id": "n4", "name": "MACD", "type": "macd",
                     "parameters": {"fast": 12, "slow": 26, "signal": 9, "source_column": "close"}},
                    {"id": "n5", "name": "RSI", "type": "rsi",
                     "parameters": {"window": 14, "source_column": "close"}},
                    {"id": "n6", "name": "布林带", "type": "boll",
                     "parameters": {"window": 20, "std_mult": 2, "source_column": "close"}},
                    {"id": "n7", "name": "综合过滤", "type": "filter",
                     "parameters": {
                         "mode": "keep",
                         "conditions": [
                             {"column": "rsi", "operator": "is_not_null", "value": ""},
                             {"column": "macd", "operator": "is_not_null", "value": ""},
                         ],
                     }},
                    {
                        "id": "n8",
                        "name": "写入DuckDB",
                        "type": "target_write",
                        "parameters": {
                            "target_type": "duckdb",
                            "target_config": '{"db_path": "D:/data/etl_demo.db"}',
                            "target_table": "aapl_full_indicators",
                            "batch_size": 5000,
                            "on_duplicate": "ignore",
                            "columns": "",
                        },
                    },
                ],
                "connections": {
                    "n1": ["n2"], "n2": ["n3"], "n3": ["n4"],
                    "n4": ["n5"], "n5": ["n6"], "n6": ["n7"], "n7": ["n8"],
                },
            },
            "sample_data": _build_kline_sample(rows=120),
        },
    ]
