"""自定义 Python 脚本节点 — 用户编写 Python 代码处理 DataFrame（支持 import）。"""
import logging
import traceback
from typing import Optional
import pandas as pd
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class CustomPythonNode(BaseNode):
    node_type = "custom_python"
    display_name = "自定义 Python 脚本"
    category = "高级"
    params_schema = {
        "code": {"type": "textarea", "label": "Python 代码（需定义 def process(df): ...）", "default": "def process(df):\n    return df"},
    }

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> pd.DataFrame:
        code = params.get("code", "")
        if not code:
            return df

        # custom_python 节点允许 import，因为用户需要导入第三方库处理数据
        # 使用普通 exec 而非 sandbox
        # 注意：即使 df 为空也要执行代码，因为用户脚本可能不依赖输入 df，
        # 而是作为数据源入口从外部 API/文件自行生成数据（如示例13 baostock 拉 K 线）。
        local_ns = {
            "df": df.copy() if not df.empty else pd.DataFrame(),
            "pd": pd,
            "context": context or {},  # 注入 context，供用户代码读取
        }

        try:
            exec(code, {"__builtins__": __builtins__, "pd": pd}, local_ns)
            logger.info("CustomPythonNode: 代码执行成功")
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("CustomPythonNode: 代码执行失败 - %s\n%s", e, tb)
            return df

        # 优先查找 process 函数
        func = local_ns.get("process")
        if callable(func):
            try:
                # 尝试传入 context 参数（向后兼容）
                import inspect
                sig = inspect.signature(func)
                if "context" in sig.parameters:
                    result = func(df, context=context)
                else:
                    result = func(df)
                if isinstance(result, pd.DataFrame):
                    return result
                else:
                    logger.error("CustomPythonNode: process 函数必须返回 DataFrame")
                    return df
            except Exception as e:
                tb = traceback.format_exc()
                logger.error("CustomPythonNode: process 函数执行失败 - %s\n%s", e, tb)
                return df

        # 如果没有 process 函数，检查 local_ns 中是否有修改后的 df
        result = local_ns.get("df", df)
        return result if isinstance(result, pd.DataFrame) else df
