"""列操作节点 — 重命名、表达式计算。"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class ColumnRenameNode(BaseNode):
    node_type = "column_rename"
    display_name = "列重命名"
    category = "数据处理"
    params_schema = {
        "renames": {"type": "text", "label": "映射: old=new（逗号分隔）", "default": "code=stock_code,dt=trade_time"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        renames_str = params.get("renames", "")
        renames = {}
        for item in renames_str.split(','):
            if '=' in item:
                old, new = item.strip().split('=', 1)
                old = old.strip()
                new = new.strip()
                if old in df.columns:
                    renames[old] = new
        if renames:
            return df.rename(columns=renames)
        return df


class ExpressionNode(BaseNode):
    node_type = "expression"
    display_name = "表达式计算"
    category = "数据处理"
    params_schema = {
        "target_column": {"type": "text", "label": "目标列名", "default": "new_col"},
        "expression": {"type": "text", "label": "Python 表达式", "default": "df['open'] + df['close']"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        target = params.get("target_column", "new_col")
        expr = params.get("expression", "")
        if not expr:
            return df
        work = df.copy()
        try:
            work[target] = work.eval(expr, engine='python')
        except Exception:
            work[target] = None
        return work
