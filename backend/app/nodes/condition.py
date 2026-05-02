"""条件分支节点 — 按条件分流数据。"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class ConditionNode(BaseNode):
    node_type = "condition"
    display_name = "条件分支"
    category = "流程控制"
    params_schema = {
        "condition": {"type": "text", "label": "条件表达式", "default": "df['close'] > 0"},
        "branch": {"type": "select", "label": "输出分支", "options": ["true", "false"], "default": "true"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        cond_str = params.get("condition", "")
        if not cond_str:
            return df
        try:
            mask = df.eval(cond_str, engine='python')
            branch = params.get("branch", "true")
            if branch == "true":
                return df[mask]
            else:
                return df[~mask]
        except Exception:
            return df
