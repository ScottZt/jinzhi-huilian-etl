"""条件循环节点 — while 循环，直到条件不满足。"""
import logging
import pandas as pd
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class LoopNode(BaseNode):
    node_type = "loop"
    display_name = "条件循环"
    category = "流程控制"
    params_schema = {
        "condition": {"type": "text", "label": "循环条件",
                      "default": "context.get('counter', 0) < 10",
                      "placeholder": "Python 表达式，返回 True/False。可引用 context 变量"},
        "max_iterations": {"type": "number", "label": "最大迭代次数", "default": 100,
                           "placeholder": "防止死循环"},
    }

    def process(self, df: pd.DataFrame, params: dict,
                context: Optional[dict] = None) -> pd.DataFrame:
        if context is None:
            logger.warning("LoopNode: context 为空，无法执行循环")
            return df

        condition_expr = params.get("condition", "False")
        max_iterations = int(params.get("max_iterations", 100))

        # 从 context 读取 workflow_json 和自己的 node_id
        workflow_json = context.get("__workflow_json__")
        current_node_id = context.get("__current_node_id__")

        if not workflow_json or not current_node_id:
            logger.warning("LoopNode: 缺少 __workflow_json__ 或 __current_node_id__，无法执行子图")
            return df

        # 提取下游子图
        sub_workflow = self._extract_downstream_subgraph(current_node_id, workflow_json)
        if not sub_workflow["nodes"]:
            logger.warning("LoopNode: 下游子图为空，跳过循环")
            return df

        # 循环执行
        from app.core.workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        engine.register_all()

        iteration = 0
        all_outputs = []

        while iteration < max_iterations:
            # 评估条件
            try:
                eval_context = {"context": context, "len": len, "int": int, "float": float, "str": bool}
                should_continue = eval(condition_expr, {"__builtins__": {}}, eval_context)
            except Exception as e:
                logger.error("LoopNode: 条件评估失败 - %s", e)
                break

            if not should_continue:
                logger.info("LoopNode: 条件不满足，退出循环（迭代 %d 次）", iteration)
                break

            logger.info("LoopNode: 第 %d 次迭代", iteration + 1)

            # 执行下游子图
            try:
                result_df = engine.execute(sub_workflow, df.copy(), workflow_context=context)
                if isinstance(result_df, tuple):
                    result_df = result_df[0]
                if result_df is not None and not result_df.empty:
                    all_outputs.append(result_df)
            except Exception as e:
                logger.error("LoopNode: 第 %d 次迭代执行失败 - %s", iteration + 1, e)

            iteration += 1

        if iteration >= max_iterations:
            logger.warning("LoopNode: 达到最大迭代次数 %d，强制退出", max_iterations)

        # 合并输出
        if all_outputs:
            final_df = pd.concat(all_outputs, ignore_index=True)
            logger.info("LoopNode: 循环完成，迭代 %d 次，合并 %d 个输出", iteration, len(all_outputs))
            return final_df
        else:
            return df

    def _extract_downstream_subgraph(self, loop_node_id: str, workflow_json: dict) -> dict:
        """提取 loop 节点的下游子图（不包括 loop 自身）"""
        nodes = workflow_json.get("nodes", [])
        connections = workflow_json.get("connections", {})

        # 构建邻接表
        adj = {}
        for src_id, targets in connections.items():
            if isinstance(targets, list):
                adj[src_id] = [t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t) for t in targets]
            elif isinstance(targets, dict):
                adj[src_id] = []
                for _k, v in targets.items():
                    if isinstance(v, list):
                        adj[src_id].extend([item.get("node", item.get("id", "")) if isinstance(item, dict) else str(item) for item in v])

        # BFS 找所有下游节点
        downstream_ids = set()
        queue = [loop_node_id]
        visited = {loop_node_id}

        while queue:
            current = queue.pop(0)
            for next_id in adj.get(current, []):
                if next_id not in visited and next_id != loop_node_id:
                    visited.add(next_id)
                    downstream_ids.add(next_id)
                    queue.append(next_id)

        # 提取子工作流
        sub_nodes = [n for n in nodes if n["id"] in downstream_ids]
        sub_connections = {k: v for k, v in connections.items() if k in downstream_ids}

        return {
            "nodes": sub_nodes,
            "connections": sub_connections,
        }
