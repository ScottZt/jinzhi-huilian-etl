"""官方精选插件：量价背离检测。

经典技术分析：价涨量缩（上涨乏力）/ 价跌量增（恐慌抛售）/ 底背离（底部信号）。
输出背离信号列，便于下游策略节点消费。
"""
import pandas as pd
import numpy as np
from app.core.workflow_engine import BaseNode


class VolumePriceDivergenceNode(BaseNode):
    node_type = "volume_price_divergence"
    display_name = "量价背离检测"
    category = "指标计算"
    params_schema = {
        "price_column": "价格列（默认 'close'）",
        "volume_column": "成交量列（默认 'vol'）",
        "window": "趋势判定窗口（默认 5）",
        "threshold": "背离强度阈值（默认 0.5，相对变化率）",
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        price_col = params.get("price_column", "close")
        vol_col = params.get("volume_column", "vol")
        window = int(params.get("window", 5))
        threshold = float(params.get("threshold", 0.5))

        if price_col not in df.columns or vol_col not in df.columns:
            return df

        work = df.copy()
        # 价格趋势：过去 window 期的线性回归斜率（标准化）
        price_chg = work[price_col].pct_change(window)
        vol_chg = work[vol_col].pct_change(window)

        # 背离信号编码：
        #  1 = 顶背离（价涨量缩，上涨乏力）
        # -1 = 恐慌放量（价跌量增，抛售）
        #  2 = 底背离（价跌量缩，抛压衰竭）
        #  0 = 无显著背离
        signal = pd.Series(0, index=work.index, dtype=int)
        signal[(price_chg > threshold) & (vol_chg < -threshold)] = 1    # 顶背离
        signal[(price_chg < -threshold) & (vol_chg > threshold)] = -1   # 恐慌放量
        signal[(price_chg < -threshold) & (vol_chg < -threshold)] = 2   # 底背离

        work["vp_divergence"] = signal
        work["vp_price_chg"] = price_chg   # 辅助：价格变化率
        work["vp_vol_chg"] = vol_chg       # 辅助：成交量变化率
        return work
