"""条件分支节点 — 按条件分流数据。"""
import logging
from typing import Dict
import pandas as pd
from app.core.workflow_engine import BaseNode
from app.core.secure_exec import validate_code_ast

logger = logging.getLogger(__name__)


class ConditionNode(BaseNode):
    node_type = "condition"
    display_name = "条件分支"
    category = "流程控制"
    params_schema = {
        "condition": {"type": "text", "label": "条件表达式", "default": "df['close'] > 0"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> Dict[str, pd.DataFrame]:
        """
        处理数据并返回两个输出分支。
        返回:
          {"output_1": 满足条件的数据 (true), "output_2": 不满足条件的数据 (false)}
        """
        if df.empty:
            return {"output_1": df, "output_2": df}

        cond_str = params.get("condition", "")
        if not cond_str:
            return {"output_1": df, "output_2": df}

        # Validate expression before passing to pandas.eval
        ok, err = validate_code_ast(cond_str)
        if not ok:
            logger.warning("ConditionNode: expression rejected: %s", err)
            return {"output_1": df, "output_2": df}

        try:
            mask = df.eval(cond_str, engine='python')
            return {"output_1": df[mask], "output_2": df[~mask]}
        except Exception:
            return {"output_1": df, "output_2": df}
