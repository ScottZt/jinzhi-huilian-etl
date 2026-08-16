"""因子表达式算子库 — 为 DSL 提供时序函数与数学函数。

每个算子是一个纯函数，签名统一：
  - 时序算子: op_xxx(series: pd.Series, *args) -> pd.Series
  - 特殊算子: 如 ATR 接收 DataFrame, CORR 接收两个 Series

算子通过 OPS_REGISTRY 注册，parser 从此字典查函数。
新增算子只需：1) 写 op 函数；2) 加入 OPS_REGISTRY。
"""
from typing import Callable
import numpy as np
import pandas as pd


# ============================================================
# 时序算子
# ============================================================

def op_ma(s: pd.Series, n) -> pd.Series:
    """简单移动平均。"""
    return s.rolling(window=int(n), min_periods=1).mean()


def op_ema(s: pd.Series, n) -> pd.Series:
    """指数移动平均。"""
    return s.ewm(span=int(n), adjust=False).mean()


def op_std(s: pd.Series, n) -> pd.Series:
    """滚动标准差。"""
    return s.rolling(window=int(n), min_periods=1).std()


def op_var(s: pd.Series, n) -> pd.Series:
    """滚动方差。"""
    return s.rolling(window=int(n), min_periods=1).var()


def op_sum(s: pd.Series, n) -> pd.Series:
    """滚动求和。"""
    return s.rolling(window=int(n), min_periods=1).sum()


def op_min(s: pd.Series, n) -> pd.Series:
    """滚动最小值。"""
    return s.rolling(window=int(n), min_periods=1).min()


def op_max(s: pd.Series, n) -> pd.Series:
    """滚动最大值。"""
    return s.rolling(window=int(n), min_periods=1).max()


def op_ref(s: pd.Series, n) -> pd.Series:
    """历史引用 (lag)。正数向历史看，负数向未来看。"""
    return s.shift(int(n))


def op_rsi(s: pd.Series, n) -> pd.Series:
    """RSI 相对强弱。"""
    delta = s.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=int(n), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=int(n), min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def op_atr(df: pd.DataFrame, n) -> pd.Series:
    """ATR 真实波幅。需要 DataFrame 含 high/low/close。"""
    if not isinstance(df, pd.DataFrame):
        raise ValueError("ATR 需要 high/low/close 三个字段，请检查表达式")
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=int(n), min_periods=1).mean()


def op_slope(s: pd.Series, n) -> pd.Series:
    """滚动线性回归斜率。"""
    n = int(n)

    def _slope(arr):
        if len(arr) < 2:
            return np.nan
        x = np.arange(len(arr), dtype=float)
        xm = x.mean()
        ym = arr.mean()
        denom = ((x - xm) ** 2).sum()
        if denom == 0:
            return 0.0
        return ((x - xm) * (arr - ym)).sum() / denom

    return s.rolling(window=n, min_periods=max(2, n // 2)).apply(_slope, raw=True)


def op_corr(s1: pd.Series, s2: pd.Series, n) -> pd.Series:
    """滚动相关系数。"""
    return s1.rolling(window=int(n), min_periods=1).corr(s2)


def op_count(cond: pd.Series, n) -> pd.Series:
    """滚动条件计数。cond 为布尔 Series。"""
    return cond.astype(float).rolling(window=int(n), min_periods=1).sum()


def op_if(cond, a, b):
    """元素条件：IF(cond, a, b)。a/b 可以是 Series 或标量。"""
    if isinstance(a, (int, float)):
        a = pd.Series(a, index=cond.index)
    if isinstance(b, (int, float)):
        b = pd.Series(b, index=cond.index)
    return pd.Series(np.where(cond.fillna(False), a, b), index=cond.index)


# ============================================================
# 数学函数（一元 / 二元）
# ============================================================

def op_abs(s): return s.abs()
def op_sign(s): return np.sign(s)
def op_log(s): return np.log(s.replace(0, np.nan))
def op_sqrt(s): return np.sqrt(s)
def op_ceil(s): return np.ceil(s)
def op_floor(s): return np.floor(s)
def op_round(s, n=0): return s.round(int(n))
def op_pow(s, n): return s ** n


# ============================================================
# 算子注册表
# ============================================================

OPS_REGISTRY: dict = {
    # 时序算子
    "MA": op_ma,
    "EMA": op_ema,
    "STD": op_std,
    "VAR": op_var,
    "SUM": op_sum,
    "MIN": op_min,
    "MAX": op_max,
    "REF": op_ref,
    "RSI": op_rsi,
    "ATR": op_atr,
    "SLOPE": op_slope,
    "CORR": op_corr,
    "COUNT": op_count,
    "IF": op_if,
    # 数学函数
    "ABS": op_abs,
    "SIGN": op_sign,
    "LOG": op_log,
    "SQRT": op_sqrt,
    "CEIL": op_ceil,
    "FLOOR": op_floor,
    "ROUND": op_round,
    "POW": op_pow,
}


def list_ops() -> list:
    """返回所有可用算子名称（供前端/文档使用）。"""
    return sorted(OPS_REGISTRY.keys())
