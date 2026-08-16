"""官方插件 · K 线形态识别（10 种经典形态）。

节点：
  - kline_pattern    识别 10 种经典 K 线形态，输出 signal 列（bullish / bearish / neutral）和 pattern 列（形态名）

支持形态：
  - 单根：hammer（锤子线）、inverted_hammer（倒锤子）、doji（十字星）
  - 双根：engulfing_bull（看涨吞没）、engulfing_bear（看跌吞没）、
          dark_cloud（乌云盖顶）、piercing（刺透形态）
  - 三根：morning_star（启明星）、evening_star（黄昏星）
  - 多根：three_white_soldiers（红三兵）、three_black_crows（三只乌鸦）
"""
import numpy as np
import pandas as pd
from app.core.workflow_engine import BaseNode


class KlinePatternNode(BaseNode):
    node_type = "kline_pattern"
    display_name = "K线形态识别"
    category = "官方插件"
    params_schema = {
        "open":    {"type": "string", "label": "开盘价列", "default": "open"},
        "high":    {"type": "string", "label": "最高价列", "default": "high"},
        "low":     {"type": "string", "label": "最低价列", "default": "low"},
        "close":   {"type": "string", "label": "收盘价列", "default": "close"},
        "volume":  {"type": "string", "label": "成交量列（可选）"},
        "symbol":  {"type": "string", "label": "股票代码列（可选）"},
        "out_signal": {"type": "string", "label": "输出信号列", "default": "pattern_signal"},
        "out_name":   {"type": "string", "label": "输出形态名列", "default": "pattern_name"},
    }

    def process(self, df: pd.DataFrame, params: dict, context=None) -> pd.DataFrame:
        if df.empty:
            return df
        o_col = params.get("open", "open")
        h_col = params.get("high", "high")
        l_col = params.get("low", "low")
        c_col = params.get("close", "close")
        v_col = (params.get("volume") or "").strip()
        sym_col = (params.get("symbol") or "").strip()
        sig_col = params.get("out_signal", "pattern_signal") or "pattern_signal"
        name_col = params.get("out_name", "pattern_name") or "pattern_name"

        for c in (o_col, h_col, l_col, c_col):
            if c not in df.columns:
                return df

        work = df.copy()
        o = work[o_col].astype(float)
        h = work[h_col].astype(float)
        l = work[l_col].astype(float)
        c = work[c_col].astype(float)
        body = (c - o).abs()
        rng = (h - l).replace(0, np.nan)
        upper = h - c.combine_first(o).where(c >= o, o)  # 上影线
        lower = c.combine_first(o).where(c >= o, c) - l  # 下影线
        # 修正：用更稳妥的写法
        upper = h - np.maximum(c, o)
        lower = np.minimum(c, o) - l
        direction = np.sign(c - o)  # +1 阳 / -1 阴 / 0 平

        sig = pd.Series("neutral", index=work.index)
        name = pd.Series("", index=work.index)

        # ---------- 单根形态 ----------
        # 锤子线：小实体 + 长下影（>= 2*body）+ 几乎无上影
        hammer = (body > 0) & (lower >= 2 * body) & (upper <= body * 0.5) & (rng > 0)
        sig[hammer] = "bullish"
        name[hammer] = "hammer"
        # 倒锤子
        inv_hammer = (body > 0) & (upper >= 2 * body) & (lower <= body * 0.5) & (rng > 0)
        sig[inv_hammer] = "bullish"
        name[inv_hammer] = "inverted_hammer"
        # 十字星
        doji = (body / rng.replace(0, np.nan)) < 0.1
        sig[doji] = "neutral"
        name[doji] = "doji"

        # ---------- 双根形态（需要前一根） ----------
        if len(work) >= 2:
            body_prev = body.shift(1)
            dir_prev = direction.shift(1)
            o_prev, c_prev = o.shift(1), c.shift(1)
            # 看涨吞没：前阴 + 当前阳 + 当前 body 包住前 body
            bull_eng = (dir_prev == -1) & (direction == 1) & (o <= o_prev) & (c >= c_prev) & (body > body_prev)
            sig[bull_eng] = "bullish"
            name[bull_eng] = "engulfing_bull"
            # 看跌吞没
            bear_eng = (dir_prev == 1) & (direction == -1) & (o >= o_prev) & (c <= c_prev) & (body > body_prev)
            sig[bear_eng] = "bearish"
            name[bear_eng] = "engulfing_bear"
            # 乌云盖顶：前阳 + 当前高开 + 收盘低于前 body 中点
            mid_prev = (o_prev + c_prev) / 2
            dark = (dir_prev == 1) & (direction == -1) & (o > c_prev) & (c < mid_prev) & (c > o_prev)
            sig[dark] = "bearish"
            name[dark] = "dark_cloud"
            # 刺透形态：前阴 + 当前低开 + 收盘高于前 body 中点
            pier = (dir_prev == -1) & (direction == 1) & (o < c_prev) & (c > mid_prev) & (c < o_prev)
            sig[pier] = "bullish"
            name[pier] = "piercing"

        # ---------- 三根形态 ----------
        if len(work) >= 3:
            d0, d1, d2 = direction, direction.shift(1), direction.shift(2)
            b0, b1 = body, body.shift(1)
            # 启明星：阴 + 小实体跳空低开 + 阳
            ms = (d2 == -1) & (b1 < b0.shift(1) * 0.5) & (d0 == 1) & (c > (o.shift(2) + c.shift(2)) / 2)
            sig[ms] = "bullish"
            name[ms] = "morning_star"
            # 黄昏星：阳 + 小实体跳空高开 + 阴
            es = (d2 == 1) & (b1 < b0.shift(1) * 0.5) & (d0 == -1) & (c < (o.shift(2) + c.shift(2)) / 2)
            sig[es] = "bearish"
            name[es] = "evening_star"

        # ---------- 多根形态 ----------
        if len(work) >= 3:
            # 红三兵：连续 3 根阳线，每根收盘创新高
            three_bull = (direction == 1) & (direction.shift(1) == 1) & (direction.shift(2) == 1) \
                         & (c > c.shift(1)) & (c.shift(1) > c.shift(2))
            sig[three_bull] = "bullish"
            name[three_bull] = "three_white_soldiers"
            # 三只乌鸦：连续 3 根阴线，每根收盘创新低
            three_bear = (direction == -1) & (direction.shift(1) == -1) & (direction.shift(2) == -1) \
                         & (c < c.shift(1)) & (c.shift(1) < c.shift(2))
            sig[three_bear] = "bearish"
            name[three_bear] = "three_black_crows"

        work[sig_col] = sig
        work[name_col] = name
        return work
