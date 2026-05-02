"""数据过滤节点 — 按条件过滤行。"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class FilterNode(BaseNode):
    node_type = "filter"
    display_name = "数据过滤"
    category = "数据处理"
    params_schema = {
        "mode": {"type": "select", "label": "模式", "options": ["keep", "drop"], "default": "keep"},
        "conditions": {"type": "list", "label": "条件列表", "default": []},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        mode = params.get("mode", "keep")
        conditions = params.get("conditions", [])
        mask = pd.Series(True, index=df.index)
        for cond in conditions:
            col = cond.get("column", "")
            op = cond.get("operator", "is_not_null")
            val = cond.get("value")
            if not col or col not in df.columns:
                continue
            if op == "is_not_null":
                cond_mask = df[col].notna()
            elif op == "is_null":
                cond_mask = df[col].isna()
            elif op == ">":
                cond_mask = pd.to_numeric(df[col], errors='coerce') > float(val)
            elif op == "<":
                cond_mask = pd.to_numeric(df[col], errors='coerce') < float(val)
            elif op == ">=":
                cond_mask = pd.to_numeric(df[col], errors='coerce') >= float(val)
            elif op == "<=":
                cond_mask = pd.to_numeric(df[col], errors='coerce') <= float(val)
            elif op == "==":
                cond_mask = df[col] == val
            elif op == "!=":
                cond_mask = df[col] != val
            elif op == "contains":
                cond_mask = df[col].astype(str).str.contains(str(val), na=False)
            elif op == "between":
                mn = cond.get("min", None)
                mx = cond.get("max", None)
                num = pd.to_numeric(df[col], errors='coerce')
                if mn is not None:
                    cond_mask = cond_mask & (num >= float(mn))
                if mx is not None:
                    cond_mask = cond_mask & (num <= float(mx))
            else:
                continue
            mask = mask & cond_mask

        if mode == "drop":
            mask = ~mask
        return df[mask]
