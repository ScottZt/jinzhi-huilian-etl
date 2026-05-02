"""自定义 Python 脚本节点 — 用户编写 Python 代码处理 DataFrame。"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class CustomPythonNode(BaseNode):
    node_type = "custom_python"
    display_name = "自定义 Python 脚本"
    category = "高级"
    params_schema = {
        "code": {"type": "textarea", "label": "Python 代码（需定义 def process(df): ...）", "default": "def process(df):\n    return df"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        code = params.get("code", "")
        if not code:
            return df
        safe_globals = {
            "pd": pd, "np": __import__('numpy'),
            "np_where": __import__('numpy').where,
            "np_select": __import__('numpy').select,
            "__builtins__": {},
        }
        local_ns = {"df": df.copy()}
        try:
            exec(code, safe_globals, local_ns)
            result = local_ns.get("df", df)
            if not isinstance(result, pd.DataFrame):
                func = local_ns.get("process")
                if callable(func):
                    result = func(df)
            if isinstance(result, pd.DataFrame):
                return result
            return df
        except Exception as e:
            print(f"CustomPythonNode error: {e}")
            return df
