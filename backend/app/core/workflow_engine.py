"""n8n 风格工作流执行引擎 — Python 原生 DAG 执行。"""
import time
from typing import Dict, Any, List, Optional
import pandas as pd


class BaseNode:
    """节点基类 — 所有节点需继承并实现 process 方法。"""
    node_type: str = "base"
    display_name: str = "Base Node"
    category: str = "数据处理"
    params_schema: Dict[str, Any] = {}

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        raise NotImplementedError

    def validate(self, params: dict) -> tuple:
        return True, ""


class WorkflowEngine:
    """
    工作流执行引擎 — 按 DAG 拓扑顺序执行节点。
    节点间以 DataFrame 传递，支持多输入/单输出。
    """

    def __init__(self):
        self._node_registry: Dict[str, type] = {}

    def register_node(self, node_class: type):
        """注册节点类型。"""
        self._node_registry[node_class.node_type] = node_class

    def register_all(self):
        """注册所有内置节点。"""
        from app.nodes import register_all_nodes, discover_custom_plugins
        from app.nodes import NodeRegistry
        register_all_nodes()
        discover_custom_plugins()
        # 将 NodeRegistry 中的节点同步到执行引擎，避免“已发现但不可执行”。
        self._node_registry = {
            node_type: NodeRegistry.get(node_type)
            for node_type in NodeRegistry.list_types()
        }

    def execute(self, workflow_json: dict, initial_df: pd.DataFrame,
                return_intermediate: bool = False) -> tuple:
        """
        执行工作流。
        返回:
          return_intermediate=False: (最终 DataFrame, {节点执行统计})
          return_intermediate=True:  (最终 DataFrame, {节点执行统计}, {node_id: DataFrame})
        """
        nodes = workflow_json.get("nodes", [])
        connections = workflow_json.get("connections", {})

        if not nodes:
            if return_intermediate:
                return initial_df, {}, {}
            return initial_df, {}

        node_map = {n["id"]: n for n in nodes}
        node_timings = {}
        node_outputs: Dict[str, pd.DataFrame] = {}

        topo_order = self._topological_sort(node_map, connections)

        for node_id in topo_order:
            node_def = node_map[node_id]
            node_type = node_def.get("type", "")
            params = node_def.get("parameters", {})

            node_class = self._node_registry.get(node_type)
            if not node_class:
                raise ValueError(f"未知节点类型: {node_type}")

            input_df = self._collect_inputs(node_id, node_def, node_outputs, connections)
            # 无上游时回退到初始数据，保证首节点可消费外部输入样本。
            if input_df.empty and not node_def.get("inputs"):
                input_df = initial_df
            t0 = time.time()
            node_instance = node_class()
            output_df = node_instance.process(input_df, params)
            elapsed = round(time.time() - t0, 3)
            node_timings[node_def.get("name", node_id)] = elapsed
            node_outputs[node_id] = output_df

        final = self._get_final_output(node_outputs, connections)
        final_df = final if final is not None else initial_df
        if return_intermediate:
            return final_df, node_timings, node_outputs
        return final_df, node_timings

    def _topological_sort(self, node_map: dict, connections: dict) -> list:
        """Kahn 算法拓扑排序。"""
        in_degree = {nid: 0 for nid in node_map}
        adj: Dict[str, list] = {nid: [] for nid in node_map}

        for src_id, targets in connections.items():
            if isinstance(targets, list):
                for t in targets:
                    if isinstance(t, dict):
                        tgt = t.get("node", t.get("id", ""))
                    else:
                        tgt = str(t)
                    if tgt in in_degree:
                        adj[src_id].append(tgt)
                        in_degree[tgt] += 1
            elif isinstance(targets, dict):
                for _k, v in targets.items():
                    if isinstance(v, list):
                        for item in v:
                            tgt = item.get("node", item.get("id", "")) if isinstance(item, dict) else str(item)
                            if tgt in in_degree:
                                adj[src_id].append(tgt)
                                in_degree[tgt] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []
        while queue:
            node_id = queue.pop(0)
            result.append(node_id)
            for next_id in adj[node_id]:
                in_degree[next_id] -= 1
                if in_degree[next_id] == 0:
                    queue.append(next_id)

        if len(result) != len(node_map):
            missing = set(node_map.keys()) - set(result)
            result.extend(missing)
        return result

    def _collect_inputs(self, node_id: str, node_def: dict, node_outputs: dict, connections: dict) -> pd.DataFrame:
        inputs = node_def.get("inputs", [])
        # 兼容仅提供 connections 的工作流定义，自动推导上游节点。
        if not inputs:
            inferred_inputs = []
            for src_id, targets in connections.items():
                target_ids = []
                if isinstance(targets, list):
                    for t in targets:
                        target_ids.append(t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t))
                elif isinstance(targets, dict):
                    for values in targets.values():
                        if isinstance(values, list):
                            for t in values:
                                target_ids.append(t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t))
                if node_id in target_ids:
                    inferred_inputs.append({"node": src_id})
            inputs = inferred_inputs
        if not inputs:
            return pd.DataFrame()
        frames = []
        for inp in inputs:
            src_id = inp.get("node", inp.get("id", ""))
            if src_id in node_outputs:
                df = node_outputs[src_id]
                if not df.empty:
                    frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _get_final_output(self, node_outputs: dict, connections: dict) -> pd.DataFrame:
        all_ids = set(node_outputs.keys())
        # 终点节点定义为“没有任何出边的节点”。
        source_with_outputs = set()
        for src_id, targets in connections.items():
            has_targets = False
            if isinstance(targets, list):
                for t in targets:
                    tgt = t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t)
                    if tgt:
                        has_targets = True
            elif isinstance(targets, dict):
                for values in targets.values():
                    if isinstance(values, list) and values:
                        has_targets = True
            if has_targets:
                source_with_outputs.add(src_id)
        sink_ids = all_ids - source_with_outputs

        if sink_ids:
            for sid in sink_ids:
                if sid in node_outputs and not node_outputs[sid].empty:
                    return node_outputs[sid]
        if node_outputs:
            last_id = list(node_outputs.keys())[-1]
            return node_outputs[last_id]
        return pd.DataFrame()


_workflow_engine = WorkflowEngine()


def get_workflow_engine() -> WorkflowEngine:
    return _workflow_engine
