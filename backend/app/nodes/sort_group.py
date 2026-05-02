"""排序和分组聚合节点。"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class SortNode(BaseNode):
    node_type = "sort"
    display_name = "排序"
    category = "数据处理"
    params_schema = {
        "by": {"type": "text", "label": "排序字段（逗号分隔）", "default": "dt"},
        "ascending": {"type": "checkbox", "label": "升序", "default": True},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        by_str = params.get("by", "dt")
        by = [x.strip() for x in by_str.split(',') if x.strip()]
        ascending = params.get("ascending", True)
        available = [c for c in by if c in df.columns]
        if not available:
            return df
        return df.sort_values(by=available, ascending=ascending).reset_index(drop=True)


class GroupByNode(BaseNode):
    node_type = "group_by"
    display_name = "分组聚合"
    category = "数据处理"
    params_schema = {
        "group_by": {"type": "text", "label": "分组字段（逗号分隔）", "default": "code"},
        "aggregations": {"type": "text", "label": "聚合: 字段=函数（逗号分隔）", "default": "open=first,close=max,low=min,close=last,vol=sum"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        gb_str = params.get("group_by", "code")
        gb_cols = [x.strip() for x in gb_str.split(',') if x.strip() and x.strip() in df.columns]
        if not gb_cols:
            return df
        agg_str = params.get("aggregations", "")
        agg_dict = {}
        for item in agg_str.split(','):
            if '=' in item:
                col, func = item.strip().split('=', 1)
                col = col.strip()
                func = func.strip()
                if col in df.columns:
                    agg_dict[col] = func
        if not agg_dict:
            return df
        return df.groupby(gb_cols).agg(agg_dict).reset_index()
