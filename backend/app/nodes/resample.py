"""重采样节点 — 按时间周期聚合数据（分钟→30min，日线→周线等）。"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class ResampleNode(BaseNode):
    node_type = "resample"
    display_name = "周期重采样"
    category = "指标计算"
    params_schema = {
        "rule": {"type": "select", "label": "目标周期", "options": ["5min", "15min", "30min", "60min", "D", "W", "M"], "default": "30min"},
        "time_column": {"type": "text", "label": "时间字段", "default": "dt"},
        "group_column": {"type": "text", "label": "分组字段（留空不分组）", "default": ""},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        rule = params.get("rule", "30min")
        time_col = params.get("time_column", "dt")
        group_col = (params.get("group_column") or "").strip()
        if time_col not in df.columns:
            return df

        # 根据DataFrame实际存在的列动态构建聚合字典
        agg = {
            'open': 'first', 'high': 'max', 'low': 'min',
            'close': 'last', 'vol': 'sum', 'amount': 'sum',
        }
        agg = {k: v for k, v in agg.items() if k in df.columns}
        if not agg:
            return df

        work = df.copy()
        work[time_col] = pd.to_datetime(work[time_col], errors='coerce')

        if group_col and group_col in work.columns:
            work = work.groupby(group_col).apply(lambda g: g.set_index(time_col).resample(rule).agg(agg).dropna(how='all'), include_groups=False).reset_index(level=0)
        else:
            work = work.set_index(time_col).resample(rule).agg(agg).dropna(how='all')
            if time_col not in work.columns:
                work = work.reset_index()

        return work
