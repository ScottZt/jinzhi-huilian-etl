"""官方插件 · 未来收益标签（机器学习打标）。

节点：
  - future_return_label    根据收盘价计算未来 N 日收益率，并生成分类/回归标签
"""
import numpy as np
import pandas as pd
from app.core.workflow_engine import BaseNode


class FutureReturnLabelNode(BaseNode):
    node_type = "future_return_label"
    display_name = "未来收益标签"
    category = "官方插件"
    params_schema = {
        "price_column":    {"type": "string", "label": "价格列", "default": "close"},
        "symbol_column":   {"type": "string", "label": "股票代码列（可选）"},
        "horizon":         {"type": "number", "label": "未来 N 日", "default": 5},
        "label_type":      {"type": "select", "label": "标签类型",
                             "options": ["classification", "regression", "both"], "default": "classification"},
        "threshold_up":    {"type": "number", "label": "上涨阈值（%）", "default": 1.0},
        "threshold_down":  {"type": "number", "label": "下跌阈值（%）", "default": -1.0},
        "out_label":       {"type": "string", "label": "输出分类列名", "default": "label"},
        "out_return":      {"type": "string", "label": "输出收益率列名", "default": "future_return"},
    }

    def process(self, df: pd.DataFrame, params: dict, context=None) -> pd.DataFrame:
        if df.empty:
            return df
        price_col = params.get("price_column", "close")
        sym_col = (params.get("symbol_column") or "").strip()
        horizon = int(params.get("horizon", 5))
        label_type = params.get("label_type", "classification")
        up = float(params.get("threshold_up", 1.0)) / 100.0
        down = float(params.get("threshold_down", -1.0)) / 100.0
        out_label = params.get("out_label", "label") or "label"
        out_ret = params.get("out_return", "future_return") or "future_return"

        if price_col not in df.columns or horizon <= 0:
            return df

        work = df.copy()

        def _calc(sub: pd.DataFrame) -> pd.DataFrame:
            future = sub[price_col].shift(-horizon)
            ret = (future - sub[price_col]) / sub[price_col]
            sub = sub.copy()
            if label_type in ("regression", "both"):
                sub[out_ret] = ret
            if label_type in ("classification", "both"):
                labels = pd.Series("flat", index=sub.index)
                labels[ret >= up] = "up"
                labels[ret <= down] = "down"
                labels[ret.isna()] = np.nan
                sub[out_label] = labels
            return sub

        if sym_col and sym_col in work.columns:
            work = work.groupby(sym_col, group_keys=False).apply(_calc)
        else:
            work = _calc(work)
        return work
