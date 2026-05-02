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
        register_all_nodes()
        discover_custom_plugins()

    def execute(self, workflow_json: dict, initial_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        """
        执行工作流。
        返回: (最终 DataFrame, {节点执行统计})
        """
        nodes = workflow_json.get("nodes", [])
        connections = workflow_json.get("connections", {})

        if not nodes:
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

            input_df = self._collect_inputs(node_def, node_outputs)
            t0 = time.time()
            node_instance = node_class()
            output_df = node_instance.process(input_df, params)
            elapsed = round(time.time() - t0, 3)
            node_timings[node_def.get("name", node_id)] = elapsed
            node_outputs[node_id] = output_df

        final = self._get_final_output(node_outputs, connections)
        return final if final is not None else initial_df, node_timings

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

    def _collect_inputs(self, node_def: dict, node_outputs: dict) -> pd.DataFrame:
        inputs = node_def.get("inputs", [])
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
        sink_ids = set(all_ids)
        for src_id, targets in connections.items():
            if isinstance(targets, list):
                for t in targets:
                    tgt = t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t)
                    if tgt in sink_ids:
                        sink_ids.discard(tgt)

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
