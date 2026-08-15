"""官方精选插件：未来收益标签。

基于收盘价生成未来 N 日收益率，作为机器学习标签列。
支持二分类（涨/跌）、三分类（涨/平/跌）、回归（连续收益率）三种模式。
"""
import pandas as pd
import numpy as np
from app.core.workflow_engine import BaseNode


class LabelFutureReturnNode(BaseNode):
    node_type = "label_future_return"
    display_name = "未来收益标签"
    category = "因子库"
    params_schema = {
        "source_column": "基准价格列（默认 'close'）",
        "horizon": "预测窗口（默认 5，即未来 5 日）",
        "mode": "标签模式：regression（连续收益率）/ binary（涨=1跌=0）/ ternary（涨=1平=0跌=-1）",
        "threshold": "ternary 模式下'平'的阈值（默认 0.005，即 0.5%）",
        "label_column": "输出列名（默认 'label'）",
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        src = params.get("source_column", "close")
        horizon = int(params.get("horizon", 5))
        mode = params.get("mode", "binary")
        threshold = float(params.get("threshold", 0.005))
        label_col = params.get("label_column", "label")

        if src not in df.columns:
            return df

        work = df.copy()
        # 计算未来 horizon 期收益率
        future_price = work[src].shift(-horizon)
        ret = (future_price - work[src]) / work[src]

        if mode == "binary":
            work[label_col] = (ret > 0).astype(float)
            work.loc[ret.isna(), label_col] = np.nan
        elif mode == "ternary":
            labels = pd.Series(np.nan, index=work.index)
            labels[ret > threshold] = 1.0
            labels[ret < -threshold] = -1.0
            labels[(ret >= -threshold) & (ret <= threshold)] = 0.0
            work[label_col] = labels
        else:  # regression
            work[label_col] = ret

        # 辅助列：实际用到的未来价格（便于回溯）
        work[f"{label_col}_future_price"] = future_price
        work[f"{label_col}_return"] = ret
        return work
