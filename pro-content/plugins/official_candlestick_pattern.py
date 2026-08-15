"""官方精选插件：K 线形态识别。

识别 10 种经典单/双 K 线形态，输出每种形态的信号列（1=出现，0=未出现）。
适用场景：技术分析策略信号、量化选股、短线交易。

形态清单：
  doji         十字星（犹豫）
  hammer       锤头（底部反转）
  shooting_star 射击之星（顶部反转）
  bullish_engulfing 阳包阴（看涨）
  bearish_engulfing 阴包阳（看跌）
  morning_star 晨星（底部反转，需 3 根 K 线）
  evening_star 暮星（顶部反转，需 3 根 K 线）
  marubozu     光头光脚（强趋势）
  spinning_top 纺锤线（震荡）
  three_white_soldiers 红三兵（强势看涨）
"""
import pandas as pd
import numpy as np
from app.core.workflow_engine import BaseNode


class CandlestickPatternNode(BaseNode):
    node_type = "candlestick_pattern"
    display_name = "K线形态识别"
    category = "指标计算"
    params_schema = {
        "open_column": "开盘价列（默认 'open'）",
        "high_column": "最高价列（默认 'high'）",
        "low_column": "最低价列（默认 'low'）",
        "close_column": "收盘价列（默认 'close'）",
        "body_ratio_threshold": "实体/振幅阈值（默认 0.1，用于十字星/纺锤线）",
        "patterns": "要识别的形态，逗号分隔（默认全部）。留空=全部识别",
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        o = params.get("open_column", "open")
        h = params.get("high_column", "high")
        l = params.get("low_column", "low")
        c = params.get("close_column", "close")
        body_thr = float(params.get("body_ratio_threshold", 0.1))
        patterns_wanted = [p.strip() for p in params.get("patterns", "").split(",") if p.strip()]

        for col in [o, h, l, c]:
            if col not in df.columns:
                return df

        work = df.copy()
        open_ = work[o].astype(float)
        high = work[h].astype(float)
        low = work[l].astype(float)
        close = work[c].astype(float)

        body = (close - open_).abs()
        full_range = (high - low).replace(0, np.nan)
        body_ratio = body / full_range
        upper_shadow = high - work[[c, o]].max(axis=1)
        lower_shadow = work[[c, o]].min(axis=1) - low
        is_up = close > open_

        def add(name, mask):
            if not patterns_wanted or name in patterns_wanted:
                work[f"pat_{name}"] = mask.fillna(False).astype(int)

        # 1. 十字星：实体很小，上下影线都较长
        add("doji", (body_ratio < body_thr) & (upper_shadow > body * 2) & (lower_shadow > body * 2))

        # 2. 锤头：下影线 >= 实体 2 倍，上影线很短，出现在下跌后
        down_trend = close < close.shift(3)
        add("hammer", (lower_shadow >= body * 2) & (upper_shadow < body * 0.5) & down_trend)

        # 3. 射击之星：上影线 >= 实体 2 倍，下影线很短，出现在上涨后
        up_trend = close > close.shift(3)
        add("shooting_star", (upper_shadow >= body * 2) & (lower_shadow < body * 0.5) & up_trend)

        # 4. 阳包阴：当前阳线实体完全包住前一根阴线实体
        prev_up = is_up.shift(1).fillna(False).astype(bool)
        add("bullish_engulfing",
            is_up & (~prev_up) & (open_ <= close.shift(1)) & (close >= open_.shift(1)))

        # 5. 阴包阳：当前阴线实体完全包住前一根阳线实体
        add("bearish_engulfing",
            (~is_up) & prev_up & (open_ >= close.shift(1)) & (close <= open_.shift(1)))

        # 6. 晨星（3 根 K 线）：大阴 → 小实体跳空低开 → 大阳
        body_prev2 = body.shift(2)
        body_prev1 = body.shift(1)
        is_up_prev2 = is_up.shift(2).fillna(False).astype(bool)
        add("morning_star",
            (~is_up_prev2) & (body_prev2 > body_prev2.shift(1) * 3) &
            (body_prev1 < body_prev2 * 0.3) &
            (is_up) & (close > open_.shift(2)))

        # 7. 暮星（3 根 K 线）：大阳 → 小实体跳空高开 → 大阴
        add("evening_star",
            (is_up_prev2) & (body_prev2 > body_prev2.shift(1) * 3) &
            (body_prev1 < body_prev2 * 0.3) &
            (~is_up) & (close < open_.shift(2)))

        # 8. 光头光脚（marubozu）：实体占满振幅
        add("marubozu", body_ratio > 0.9)

        # 9. 纺锤线：小实体 + 上下影线都长
        add("spinning_top",
            (body_ratio < 0.3) & (upper_shadow > body) & (lower_shadow > body))

        # 10. 红三兵：连续 3 根上涨，每根创新高
        up1 = is_up & (close > close.shift(1))
        up2 = is_up.shift(1) & (close.shift(1) > close.shift(2))
        up3 = is_up.shift(2) & (close.shift(2) > close.shift(3))
        add("three_white_soldiers", up1 & up2 & up3)

        return work
