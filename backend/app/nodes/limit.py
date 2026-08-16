"""数据限制节点 — 限制数据量。"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class LimitNode(BaseNode):
    node_type = "limit"
    display_name = "数据限制"
    category = "数据处理"
    params_schema = {
        "max_items": {"type": "number", "label": "最大数据量", "default": 100,
                      "placeholder": "限制返回的数据行数"},
        "keep": {"type": "select", "label": "保留策略", "options": ["first", "last"], "default": "first",
                 "placeholder": "first=保留前N条, last=保留后N条"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df

        max_items = int(params.get("max_items", 100))
        keep = params.get("keep", "first")

        if max_items <= 0:
            return df

        if max_items >= len(df):
            return df

        if keep == "first":
            return df.head(max_items)
        else:  # last
            return df.tail(max_items)
