"""数据合并节点 — 合并多个数据流。"""
import logging
import pandas as pd
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class MergeNode(BaseNode):
    node_type = "merge"
    display_name = "数据合并"
    category = "数据处理"
    params_schema = {
        "mode": {"type": "select", "label": "合并模式", "options": ["append", "combine", "multiplex"], "default": "append",
                 "placeholder": "append=纵向合并, combine=横向合并, multiplex=多路复用"},
        "join_type": {"type": "select", "label": "连接类型", "options": ["inner", "left", "right", "outer"], "default": "outer",
                      "placeholder": "仅 combine 模式有效"},
        "on_columns": {"type": "text", "label": "连接字段", "default": "",
                       "placeholder": "combine 模式的连接字段（逗号分隔），留空使用所有共同字段"},
        "input_count": {"type": "number", "label": "输入数量", "default": 2,
                        "placeholder": "需要合并的输入数据流数量"},
    }

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> pd.DataFrame:
        """
        合并多个数据流。
        参数:
          df: 主输入数据（第一个输入）
          params: 节点参数
          context: 工作流上下文（用于获取其他输入）
        """
        mode = params.get("mode", "append")
        input_count = int(params.get("input_count", 2))

        # 获取所有输入数据
        inputs = self._collect_all_inputs(df, context, input_count)

        if not inputs:
            logger.warning("MergeNode: 没有输入数据")
            return df

        if len(inputs) == 1:
            return inputs[0]

        if mode == "append":
            return self._merge_append(inputs)
        elif mode == "combine":
            return self._merge_combine(inputs, params)
        elif mode == "multiplex":
            return self._merge_multiplex(inputs, params)
        else:
            logger.warning("MergeNode: 未知合并模式: %s", mode)
            return df

    def _collect_all_inputs(self, main_df: pd.DataFrame, context: Optional[dict], input_count: int) -> list:
        """收集所有输入数据。"""
        inputs = [main_df]

        if context is None:
            return inputs

        # 从上下文中获取其他输入
        # 注意：这里需要根据实际的工作流引擎实现来调整
        # 目前假设其他输入通过 context 传递
        workflow_json = context.get("__workflow_json__")
        current_node_id = context.get("__current_node_id__")

        if not workflow_json or not current_node_id:
            return inputs

        # 查找当前节点的所有输入
        connections = workflow_json.get("connections", {})
        input_nodes = []

        for src_id, targets in connections.items():
            if isinstance(targets, list):
                for t in targets:
                    tgt = t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t)
                    if tgt == current_node_id:
                        input_nodes.append(src_id)
            elif isinstance(targets, dict):
                for target_list in targets.values():
                    if isinstance(target_list, list):
                        for t in target_list:
                            tgt = t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t)
                            if tgt == current_node_id:
                                input_nodes.append(src_id)

        # 从 node_outputs 中获取其他输入的数据
        node_outputs = context.get("__node_outputs__", {})
        for node_id in input_nodes[:input_count - 1]:  # 排除主输入
            if node_id in node_outputs:
                output = node_outputs[node_id]
                if isinstance(output, dict):
                    # 多输出节点，取第一个输出
                    if output:
                        inputs.append(list(output.values())[0])
                else:
                    inputs.append(output)

        return inputs

    def _merge_append(self, inputs: list) -> pd.DataFrame:
        """纵向合并（类似 pd.concat）。"""
        try:
            return pd.concat(inputs, ignore_index=True)
        except Exception as e:
            logger.error("MergeNode: append 合并失败: %s", e)
            return inputs[0]

    def _merge_combine(self, inputs: list, params: dict) -> pd.DataFrame:
        """横向合并（类似 pd.merge/join）。"""
        join_type = params.get("join_type", "outer")
        on_columns = params.get("on_columns", "")

        if on_columns:
            on_cols = [c.strip() for c in on_columns.split(",") if c.strip()]
        else:
            # 使用所有共同字段
            on_cols = None

        try:
            result = inputs[0]
            for i, df in enumerate(inputs[1:], 1):
                if on_cols:
                    result = pd.merge(result, df, on=on_cols, how=join_type, suffixes=(f"_{i}", f"_{i+1}"))
                else:
                    # 找到共同字段
                    common_cols = list(set(result.columns) & set(df.columns))
                    if common_cols:
                        result = pd.merge(result, df, on=common_cols, how=join_type, suffixes=(f"_i{i}", f"_i{i+1}"))
                    else:
                        # 没有共同字段，使用笛卡尔积
                        logger.warning("MergeNode: 第 %d 个输入没有共同字段，使用笛卡尔积", i)
                        result = result.merge(df, how='cross')

            return result
        except Exception as e:
            logger.error("MergeNode: combine 合并失败: %s", e)
            return inputs[0]

    def _merge_multiplex(self, inputs: list, params: dict) -> pd.DataFrame:
        """多路复用（根据条件选择输入）。"""
        # 暂时简单实现：返回第一个非空输入
        for df in inputs:
            if not df.empty:
                return df
        return inputs[0]
