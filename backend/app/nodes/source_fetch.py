"""数据源拉取节点 — 支持按时间范围 + 股票代码拉取，可并行处理。"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List

import pandas as pd

from app.core.workflow_engine import BaseNode


def _fetch_one_code(adapter, cfg: dict, code: str, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
    """拉取单只股票 K 线数据。"""
    try:
        df = adapter.fetch_kline(cfg, [code], start, end, interval)
        if not df.empty:
            if "datetime" in df.columns and "dt" not in df.columns:
                df = df.rename(columns={"datetime": "dt"})
            if "vol" in df.columns and "volume" not in df.columns:
                df = df.rename(columns={"vol": "volume"})
        return df
    except Exception:
        return pd.DataFrame()


def _get_adapter(source_type: str, cfg: dict):
    """根据数据源类型获取适配器实例。"""
    if source_type == "tdx":
        from app.adapters.source_adapters.tdx_adapter import TdxAdapter
        return TdxAdapter()
    elif source_type == "mootdx":
        from app.adapters.source_adapters.mootdx_adapter import MootdxAdapter
        return MootdxAdapter()
    elif source_type == "akshare":
        from app.adapters.source_adapters.akshare_adapter import HttpAdapter
        return HttpAdapter()
    elif source_type == "tushare":
        from app.adapters.source_adapters.tushare_adapter import HttpAdapter
        return HttpAdapter()
    elif source_type == "binance":
        from app.adapters.source_adapters.binance_adapter import BinanceAdapter
        return BinanceAdapter()
    elif source_type == "yfinance":
        from app.adapters.source_adapters.yfinance_adapter import YfinanceAdapter
        return YfinanceAdapter()
    else:
        raise ValueError(f"不支持的数据源类型: {source_type}")


class SourceFetchNode(BaseNode):
    node_type = "source_fetch"
    display_name = "数据源拉取"
    category = "数据接入"
    params_schema = {
        "source_type": {
            "type": "select",
            "label": "数据源类型",
            "options": ["tdx", "mootdx", "akshare", "tushare", "binance", "yfinance"],
            "default": "tdx",
        },
        "source_config": {
            "type": "text",
            "label": "数据源配置(JSON)",
            "default": '{"data_dir": "D:/new_tdx64/vipdoc"}',
        },
        "codes": {
            "type": "text",
            "label": "交易对/股票代码(逗号分隔)",
            "default": "BTCUSDT,ETHUSDT",
        },
        "interval": {
            "type": "select",
            "label": "K线周期",
            "options": ["1min", "5min", "15min", "30min", "60min", "D"],
            "default": "1min",
        },
        "time_mode": {
            "type": "select",
            "label": "时间模式",
            "options": ["lookback", "custom", "since_last"],
            "default": "lookback",
        },
        "start_date": {
            "type": "text",
            "label": "开始日期(YYYY-MM-DD)",
            "default": "",
        },
        "end_date": {
            "type": "text",
            "label": "结束日期(YYYY-MM-DD)",
            "default": "",
        },
        "lookback_days": {
            "type": "number",
            "label": "回看天数",
            "default": 30,
        },
        "parallel": {
            "type": "checkbox",
            "label": "并行拉取(按股票)",
            "default": False,
        },
        "max_workers": {
            "type": "number",
            "label": "最大并发数",
            "default": 4,
        },
        "session_only": {
            "type": "checkbox",
            "label": "仅交易时段",
            "default": True,
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        source_type = params.get("source_type", "tdx")
        source_config_str = params.get("source_config", "{}")
        import json

        try:
            cfg = json.loads(source_config_str)
        except Exception:
            cfg = {}

        codes_str = params.get("codes", "000001")
        codes = [c.strip() for c in codes_str.split(",") if c.strip()]
        if not codes:
            return pd.DataFrame()

        interval = params.get("interval", "1min")
        session_only = params.get("session_only", True)

        # 解析时间范围
        time_mode = params.get("time_mode", "lookback")
        if time_mode == "custom":
            start_str = params.get("start_date", "")
            end_str = params.get("end_date", "")
            if start_str and end_str:
                start_time = pd.to_datetime(start_str)
                end_time = pd.to_datetime(end_str)
            else:
                return pd.DataFrame()
        elif time_mode == "since_last":
            # 从上游 DataFrame 取最新时间作为起点
            if not df.empty and "dt" in df.columns:
                start_time = pd.to_datetime(df["dt"].max())
                end_time = datetime.now()
            else:
                start_time = datetime.now() - timedelta(days=1)
                end_time = datetime.now()
        else:
            lookback = int(params.get("lookback_days", 30))
            end_time = datetime.now()
            start_time = end_time - timedelta(days=lookback)

        adapter = _get_adapter(source_type, cfg)

        # 交易时段过滤（分钟线）
        def filter_session(d: pd.DataFrame) -> pd.DataFrame:
            if d.empty or "dt" not in d.columns:
                return d
            work = d.copy()
            work["dt"] = pd.to_datetime(work["dt"], errors="coerce")
            work = work.dropna(subset=["dt"])
            minutes = work["dt"].dt.hour * 60 + work["dt"].dt.minute
            mask = ((minutes >= 570) & (minutes <= 690)) | ((minutes >= 780) & (minutes <= 900))
            return work.loc[mask].reset_index(drop=True)

        parallel = params.get("parallel", False)
        max_workers = int(params.get("max_workers", 4))

        if parallel and len(codes) > 1:
            # 并发拉取：每只股票一个线程
            all_frames: List[pd.DataFrame] = []
            with ThreadPoolExecutor(max_workers=min(max_workers, len(codes))) as pool:
                futures = {
                    pool.submit(_fetch_one_code, adapter, cfg, code, start_time, end_time, interval): code
                    for code in codes
                }
                for future in as_completed(futures):
                    code_df = future.result()
                    if not code_df.empty:
                        if session_only and interval == "1min":
                            code_df = filter_session(code_df)
                        all_frames.append(code_df)
            if not all_frames:
                return pd.DataFrame()
            result = pd.concat(all_frames, ignore_index=True)
        else:
            # 串行拉取
            result = adapter.fetch_kline(cfg, codes, start_time, end_time, interval)
            if session_only and interval == "1min":
                result = filter_session(result)

        if result.empty:
            return result

        result["dt"] = pd.to_datetime(result["dt"], errors="coerce")
        result = result.sort_values(["code", "dt"]).reset_index(drop=True)
        return result
