"""自定义 Python 脚本节点 — 用户编写 Python 代码处理 DataFrame（沙箱执行）。"""
import logging
import pandas as pd
from app.core.workflow_engine import BaseNode
from app.core.secure_exec import make_sandbox_globals, safe_exec

logger = logging.getLogger(__name__)


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
        safe_globals = make_sandbox_globals()
        local_ns = {"df": df.copy()}
        ok, err = safe_exec(code, safe_globals, local_ns, label="custom_python_node")
        if not ok:
            logger.error("CustomPythonNode: %s", err)
            return df
        result = local_ns.get("df", df)
        if not isinstance(result, pd.DataFrame):
            func = local_ns.get("process")
            if callable(func):
                result = func(df)
        return result if isinstance(result, pd.DataFrame) else df
