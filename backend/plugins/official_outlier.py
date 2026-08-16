"""官方插件 · 异常值处理（乌龙指 / 脏数据清洗）。

节点：
  - outlier_detect    检测异常值（zscore / iqr / multiplier），输出标记列
  - outlier_treat     处理异常值（clip / fill_median / fill_zero / drop / flag）
"""
import numpy as np
import pandas as pd
from app.core.workflow_engine import BaseNode


class OutlierDetectNode(BaseNode):
    node_type = "outlier_detect"
    display_name = "异常值检测"
    category = "官方插件"
    params_schema = {
        "column":       {"type": "string", "label": "检测列（如 close）"},
        "method":       {"type": "select", "label": "方法", "options": ["zscore", "iqr", "multiplier"], "default": "zscore"},
        "threshold":    {"type": "number", "label": "阈值", "default": 3.0,
                         "help": "zscore: 标准差倍数(默认3)；iqr: IQR倍数(默认1.5)；multiplier: 中位数倍数(默认5)"},
        "group_column": {"type": "string", "label": "分组列（可选，如 symbol）"},
        "output_col":   {"type": "string", "label": "输出标记列名", "default": "is_outlier"},
    }

    def process(self, df: pd.DataFrame, params: dict, context=None) -> pd.DataFrame:
        if df.empty:
            return df
        col = params.get("column", "").strip()
        if not col or col not in df.columns:
            return df
        method = params.get("method", "zscore")
        thr = float(params.get("threshold", 3.0))
        out_col = params.get("output_col", "is_outlier") or "is_outlier"
        group_col = (params.get("group_column") or "").strip()

        work = df.copy()
        work[out_col] = False

        def _detect(series: pd.Series) -> pd.Series:
            s = series.replace([np.inf, -np.inf], np.nan)
            if method == "zscore":
                mean, std = s.mean(), s.std()
                if std == 0 or np.isnan(std):
                    return pd.Series(False, index=series.index)
                return ((s - mean).abs() / std) > thr
            if method == "iqr":
                q1, q3 = s.quantile(0.25), s.quantile(0.75)
                iqr = q3 - q1
                if iqr == 0 or np.isnan(iqr):
                    return pd.Series(False, index=series.index)
                return (s < (q1 - thr * iqr)) | (s > (q3 + thr * iqr))
            # multiplier
            med = s.median()
            if med == 0 or np.isnan(med):
                return pd.Series(False, index=series.index)
            return (s.abs() / abs(med)) > thr

        if group_col and group_col in work.columns:
            work[out_col] = work.groupby(group_col, group_keys=False)[col].apply(_detect)
        else:
            work[out_col] = _detect(work[col])
        return work


class OutlierTreatNode(BaseNode):
    node_type = "outlier_treat"
    display_name = "异常值处理"
    category = "官方插件"
    params_schema = {
        "column":      {"type": "string", "label": "处理列"},
        "mask_column": {"type": "string", "label": "异常标记列（来自 outlier_detect）", "default": "is_outlier"},
        "action":      {"type": "select", "label": "处理方式",
                        "options": ["clip", "fill_median", "fill_zero", "drop", "flag_only"],
                        "default": "clip"},
        "clip_low":    {"type": "number", "label": "clip 下界（留空按 5% 分位）"},
        "clip_high":   {"type": "number", "label": "clip 上界（留空按 95% 分位）"},
    }

    def process(self, df: pd.DataFrame, params: dict, context=None) -> pd.DataFrame:
        if df.empty:
            return df
        col = params.get("column", "").strip()
        mask_col = params.get("mask_column", "is_outlier")
        action = params.get("action", "clip")
        if not col or col not in df.columns:
            return df
        work = df.copy()
        mask = work[mask_col].astype(bool) if mask_col in work.columns else pd.Series(False, index=work.index)

        if action == "drop":
            return work[~mask].reset_index(drop=True)
        if action == "flag_only":
            # 仅保留标记列，不做处理
            return work
        if action == "fill_zero":
            work.loc[mask, col] = 0
            return work
        if action == "fill_median":
            med = work.loc[~mask, col].median()
            work.loc[mask, col] = med if not np.isnan(med) else 0
            return work
        # clip
        low = params.get("clip_low")
        high = params.get("clip_high")
        s = work.loc[~mask, col]
        low_v = float(low) if low not in (None, "", "null") else float(s.quantile(0.05)) if not s.empty else 0
        high_v = float(high) if high not in (None, "", "null") else float(s.quantile(0.95)) if not s.empty else 0
        work.loc[mask, col] = work.loc[mask, col].clip(lower=low_v, upper=high_v)
        return work
