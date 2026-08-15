"""官方精选插件：异常值处理。

基于 MAD（Median Absolute Deviation）或 Z-score 检测并处理异常值。
适用场景：乌龙指、除权未复权的极端价、数据源脏数据。
"""
import pandas as pd
import numpy as np
from app.core.workflow_engine import BaseNode


class OutlierHandlerNode(BaseNode):
    node_type = "outlier_handler"
    display_name = "异常值处理"
    category = "数据处理"
    params_schema = {
        "columns": "待检测列，逗号分隔（如 'open,high,low,close'）",
        "method": "检测方法：mad（默认，鲁棒） / zscore / clip",
        "threshold": "异常阈值：mad 默认 3.5，zscore 默认 3.0",
        "action": "处理方式：clip（截断到边界）/ mask（置 NaN）/ flag（仅打标）",
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        columns = [c.strip() for c in params.get("columns", "").split(",") if c.strip()]
        if not columns:
            return df
        method = params.get("method", "mad")
        threshold = float(params.get("threshold", 3.5 if method == "mad" else 3.0))
        action = params.get("action", "clip")

        work = df.copy()
        for col in columns:
            if col not in work.columns:
                continue
            series = work[col].astype(float)
            if method == "mad":
                median = series.median()
                mad = (series - median).abs().median() * 1.4826  # 归一化到标准差尺度
                if mad == 0 or np.isnan(mad):
                    continue
                z = (series - median).abs() / mad
                lower, upper = median - threshold * mad, median + threshold * mad
            elif method == "zscore":
                mean, std = series.mean(), series.std()
                if std == 0 or np.isnan(std):
                    continue
                z = (series - mean).abs() / std
                lower, upper = mean - threshold * std, mean + threshold * std
            else:  # clip：仅做截断，无需检测
                lower = series.quantile(0.005)
                upper = series.quantile(0.995)
                z = None

            # 处理
            if action == "flag":
                work[f"{col}_outlier"] = (z > threshold) if z is not None else False
            elif action == "mask":
                mask = (z > threshold) if z is not None else ((series < lower) | (series > upper))
                work.loc[mask, col] = np.nan
            else:  # clip
                work[col] = series.clip(lower, upper)
        return work
