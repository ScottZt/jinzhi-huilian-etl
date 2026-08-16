"""官方插件 · 量价背离检测。

节点：
  - divergence_detect    检测价格与指标之间的顶背离 / 底背离
    支持指标：macd / rsi / volume / 自定义列
"""
import numpy as np
import pandas as pd
from app.core.workflow_engine import BaseNode


class DivergenceDetectNode(BaseNode):
    node_type = "divergence_detect"
    display_name = "量价背离检测"
    category = "官方插件"
    params_schema = {
        "price_column":   {"type": "string", "label": "价格列", "default": "close"},
        "indicator":      {"type": "select", "label": "指标类型",
                           "options": ["macd", "rsi", "volume", "custom"], "default": "macd"},
        "custom_column":  {"type": "string", "label": "自定义指标列（indicator=custom 时）"},
        "symbol_column":  {"type": "string", "label": "股票代码列（可选）"},
        "lookback":       {"type": "number", "label": "局部极值窗口", "default": 10},
        "out_col":        {"type": "string", "label": "输出背离类型列", "default": "divergence"},
    }

    def process(self, df: pd.DataFrame, params: dict, context=None) -> pd.DataFrame:
        if df.empty:
            return df
        price_col = params.get("price_column", "close")
        indicator = params.get("indicator", "macd")
        custom_col = (params.get("custom_column") or "").strip()
        sym_col = (params.get("symbol_column") or "").strip()
        lookback = max(3, int(params.get("lookback", 10)))
        out_col = params.get("out_col", "divergence") or "divergence"

        # 确定指标列
        if indicator == "macd":
            ind_col = "_div_macd"
            df = _ensure_macd(df, ind_col)
        elif indicator == "rsi":
            ind_col = "_div_rsi"
            df = _ensure_rsi(df, ind_col)
        elif indicator == "volume":
            ind_col = "volume"
            if ind_col not in df.columns:
                return df
        elif indicator == "custom" and custom_col in df.columns:
            ind_col = custom_col
        else:
            return df

        work = df.copy()
        work[out_col] = ""

        def _detect(sub: pd.DataFrame) -> pd.DataFrame:
            price = sub[price_col].astype(float)
            ind = sub[ind_col].astype(float)
            # 局部极值
            p_high = price.rolling(lookback, center=True, min_periods=1).max()
            p_low = price.rolling(lookback, center=True, min_periods=1).min()
            i_at_phigh = ind.rolling(lookback, center=True, min_periods=1).max()
            i_at_plow = ind.rolling(lookback, center=True, min_periods=1).min()
            # 顶背离：价格创新高，指标未创新高
            top = (price >= p_high * 0.999) & (ind < i_at_phigh * 0.999)
            # 底背离：价格创新低，指标未创新低
            bot = (price <= p_low * 1.001) & (ind > i_at_plow * 1.001)
            labels = pd.Series("", index=sub.index)
            labels[top & ~bot] = "top_divergence"
            labels[bot & ~top] = "bottom_divergence"
            labels[top & bot] = "ambiguous"
            sub = sub.copy()
            sub[out_col] = labels
            return sub

        if sym_col and sym_col in work.columns:
            work = work.groupby(sym_col, group_keys=False).apply(_detect)
        else:
            work = _detect(work)

        # 清理临时列
        if ind_col.startswith("_div_"):
            work = work.drop(columns=[ind_col], errors="ignore")
        return work


def _ensure_macd(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        return df
    work = df.copy()
    if "close" not in work.columns:
        work[col] = np.nan
        return work
    close = work["close"].astype(float)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    work[col] = ema12 - ema26  # MACD 柱（DIF-DEA 简化为 DIF）
    return work


def _ensure_rsi(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        return df
    work = df.copy()
    if "close" not in work.columns:
        work[col] = np.nan
        return work
    close = work["close"].astype(float)
    delta = close.diff()
    up = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    down = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs = up / down.replace(0, np.nan)
    work[col] = 100 - (100 / (1 + rs))
    return work
