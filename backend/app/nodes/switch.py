"""多路分支节点 — 根据多个条件规则分流数据。"""
import logging
from typing import Dict
import pandas as pd
from app.core.workflow_engine import BaseNode
from app.core.secure_exec import validate_code_ast

logger = logging.getLogger(__name__)


class SwitchNode(BaseNode):
    node_type = "switch"
    display_name = "多路分支"
    category = "流程控制"
    params_schema = {
        "rules": {"type": "textarea", "label": "条件规则",
                  "default": '[\n  {"condition": "value > 100", "output": "output_1"},\n  {"condition": "value > 50", "output": "output_2"}\n]',
                  "placeholder": "JSON 数组格式，每个规则包含 condition 和 output 字段"},
        "default_output": {"type": "text", "label": "默认输出", "default": "output_3",
                          "placeholder": "当所有条件都不满足时的输出端口"},
    }

    def process(self, df: pd.DataFrame, params: dict) -> Dict[str, pd.DataFrame]:
        """
        处理数据并根据多个条件规则分流。
        返回:
          字典形式的多输出，如 {"output_1": df1, "output_2": df2, "output_3": df3}
        """
        if df.empty:
            return {"output_1": df}

        rules_str = params.get("rules", "[]")
        default_output = params.get("default_output", "output_3")

        # 解析规则
        try:
            import json
            if isinstance(rules_str, str):
                rules = json.loads(rules_str)
            else:
                rules = rules_str
        except Exception as e:
            logger.warning("SwitchNode: 规则解析失败: %s", e)
            return {"output_1": df}

        if not rules:
            return {"output_1": df}

        # 初始化输出
        outputs = {}
        remaining_mask = pd.Series(True, index=df.index)

        # 按顺序处理每个规则
        for rule in rules:
            condition = rule.get("condition", "")
            output_name = rule.get("output", "output_1")

            if not condition:
                continue

            # 验证表达式
            ok, err = validate_code_ast(condition)
            if not ok:
                logger.warning("SwitchNode: 表达式无效: %s, 错误: %s", condition, err)
                continue

            try:
                # 在剩余数据上评估条件
                mask = df.eval(condition, engine='python') & remaining_mask

                if mask.any():
                    outputs[output_name] = df[mask]
                    remaining_mask = remaining_mask & ~mask  # 从剩余数据中移除已匹配的行
            except Exception as e:
                logger.warning("SwitchNode: 条件评估失败: %s, 错误: %s", condition, e)
                continue

        # 处理默认输出（未匹配任何条件的数据）
        if remaining_mask.any():
            outputs[default_output] = df[remaining_mask]

        # 确保至少有一个输出
        if not outputs:
            outputs["output_1"] = df

        return outputs
