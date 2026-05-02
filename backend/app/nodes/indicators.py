"""技术指标节点 — MA、EMA、MACD、RSI、布林带（通用数值列）。"""
import numpy as np
import pandas as pd
from app.core.workflow_engine import BaseNode


class MANode(BaseNode):
    node_type = "ma"
    display_name = "移动平均 (MA/EMA)"
    category = "指标计算"
    params_schema = {
        "windows": {"type": "text", "label": "窗口（逗号分隔）", "default": "5,10,20"},
        "source_column": {"type": "text", "label": "源字段", "default": "close"},
        "use_ema": {"type": "checkbox", "label": "使用 EMA", "default": False},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        col = params.get("source_column", "close")
        if col not in df.columns:
            return df
        windows_str = str(params.get("windows", "5,10"))
        windows = [int(x.strip()) for x in windows_str.split(',') if x.strip().isdigit()]
        use_ema = bool(params.get("use_ema", False))
        work = df.copy()
        for w in windows:
            name = f"ema_{w}" if use_ema else f"ma_{w}"
            if use_ema:
                work[name] = work[col].ewm(span=w, adjust=False).mean()
            else:
                work[name] = work[col].rolling(window=w).mean()
        return work


class MACDNode(BaseNode):
    node_type = "macd"
    display_name = "MACD 指标"
    category = "指标计算"
    params_schema = {
        "fast": {"type": "number", "label": "快线", "default": 12},
        "slow": {"type": "number", "label": "慢线", "default": 26},
        "signal": {"type": "number", "label": "信号线", "default": 9},
        "source_column": {"type": "text", "label": "源字段", "default": "close"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        col = params.get("source_column", "close")
        if col not in df.columns:
            return df
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        work = df.copy()
        s = work[col]
        exp1 = s.ewm(span=fast, adjust=False).mean()
        exp2 = s.ewm(span=slow, adjust=False).mean()
        work['dif'] = exp1 - exp2
        work['dea'] = work['dif'].ewm(span=signal, adjust=False).mean()
        work['macd'] = (work['dif'] - work['dea']) * 2
        return work


class RSINode(BaseNode):
    node_type = "rsi"
    display_name = "RSI 相对强弱"
    category = "指标计算"
    params_schema = {
        "window": {"type": "number", "label": "窗口", "default": 14},
        "source_column": {"type": "text", "label": "源字段", "default": "close"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        col = params.get("source_column", "close")
        if col not in df.columns:
            return df
        w = int(params.get("window", 14))
        work = df.copy()
        delta = work[col].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=w).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=w).mean()
        rs = gain / loss.replace(0, np.nan)
        work['rsi'] = 100 - (100 / (1 + rs))
        return work


class BollNode(BaseNode):
    node_type = "boll"
    display_name = "布林带 (BOLL)"
    category = "指标计算"
    params_schema = {
        "window": {"type": "number", "label": "窗口", "default": 20},
        "std_mult": {"type": "number", "label": "标准差倍数", "default": 2},
        "source_column": {"type": "text", "label": "源字段", "default": "close"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        col = params.get("source_column", "close")
        if col not in df.columns:
            return df
        w = int(params.get("window", 20))
        mult = float(params.get("std_mult", 2))
        work = df.copy()
        work['boll_mid'] = work[col].rolling(window=w).mean()
        std = work[col].rolling(window=w).std()
        work['boll_upper'] = work['boll_mid'] + mult * std
        work['boll_lower'] = work['boll_mid'] - mult * std
        return work
