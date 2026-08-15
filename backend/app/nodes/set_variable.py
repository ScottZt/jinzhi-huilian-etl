"""变量赋值节点 — 存储中间状态到工作流全局上下文。"""
import json
import logging
import pandas as pd
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class SetVariableNode(BaseNode):
    node_type = "set_variable"
    display_name = "变量赋值"
    category = "流程控制"
    params_schema = {
        "var_name": {"type": "text", "label": "变量名", "default": "my_var",
                     "placeholder": "例如：counter、total_rows、current_table"},
        "var_value": {"type": "textarea", "label": "变量值", "default": "0",
                      "placeholder": "根据值类型填写：字符串直接写、JSON 写数组/对象、表达式写 Python 代码"},
        "value_type": {"type": "select", "label": "值类型",
                       "options": ["string", "number", "json", "expression"],
                       "default": "string"},
    }

    def process(self, df: pd.DataFrame, params: dict,
                context: Optional[dict] = None) -> pd.DataFrame:
        var_name = params.get("var_name", "").strip()
        var_value_str = params.get("var_value", "")
        value_type = params.get("value_type", "string")

        if not var_name:
            logger.warning("SetVariableNode: var_name 为空，跳过赋值")
            return df

        if context is None:
            logger.warning("SetVariableNode: context 为空，无法赋值变量")
            return df

        # 根据 value_type 解析值
        try:
            if value_type == "string":
                value = var_value_str
            elif value_type == "number":
                value = float(var_value_str) if "." in var_value_str else int(var_value_str)
            elif value_type == "json":
                value = json.loads(var_value_str)
            elif value_type == "expression":
                # 表达式模式：可以用 context 里的其他变量
                # 例如：context.get("counter", 0) + 1
                eval_context = {"context": context, "len": len, "int": int, "float": float, "str": str}
                value = eval(var_value_str, {"__builtins__": {}}, eval_context)
            else:
                logger.warning("SetVariableNode: 未知 value_type=%s，按字符串处理", value_type)
                value = var_value_str

            context[var_name] = value
            logger.info("SetVariableNode: %s = %s (type=%s)", var_name, value, type(value).__name__)

        except Exception as e:
            logger.error("SetVariableNode: 解析变量值失败 - %s", e)

        # 原样返回 df，不影响数据流
        return df
