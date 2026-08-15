"""n8n 风格工作流执行引擎 — Python 原生 DAG 执行。"""
import time
from typing import Dict, Any, List, Optional, Union
import pandas as pd


class BaseNode:
    """节点基类 — 所有节点需继承并实现 process 方法。"""
    node_type: str = "base"
    display_name: str = "Base Node"
    category: str = "数据处理"
    params_schema: Dict[str, Any] = {}

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
        """
        处理数据。
        参数:
          df: 输入 DataFrame
          params: 节点参数
          context: 可选，工作流全局上下文（用于循环节点、变量传递等）
        返回:
          处理后的 DataFrame，或字典形式的多输出（如 {"true": df1, "false": df2}）
        """
        raise NotImplementedError

    def validate(self, params: dict) -> tuple:
        return True, ""


class WorkflowEngine:
    """
    工作流执行引擎 — 按 DAG 拓扑顺序执行节点。
    节点间以 DataFrame 传递，支持多输入/多输出。
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
        # 将 NodeRegistry 中的节点同步到执行引擎，避免"已发现但不可执行"。
        self._node_registry = {
            node_type: NodeRegistry.get(node_type)
            for node_type in NodeRegistry.list_types()
        }

    def execute(self, workflow_json: dict, initial_df: pd.DataFrame,
                workflow_context: Optional[dict] = None,
                return_intermediate: bool = False,
                stop_at_node_id: Optional[str] = None) -> tuple:
        """
        执行工作流。
        参数:
          workflow_context: 可选，工作流全局上下文（dict），用于循环节点、变量传递等。
                           节点可通过 context 参数访问和修改这个字典。
          return_intermediate: 是否返回每个节点的中间输出
          stop_at_node_id: 仅执行到指定节点（用于单节点调试）
        返回:
          return_intermediate=False: (最终 DataFrame, {节点执行统计}) — 如有错误，errors 挂在返回值第3位
          return_intermediate=True:  (最终 DataFrame, {节点执行统计}, {node_id: DataFrame})
          如有节点错误，返回值追加第3或第4项 error_summary (dict)
        """
        if workflow_context is None:
            workflow_context = {}

        nodes = workflow_json.get("nodes", [])
        connections = workflow_json.get("connections", {})

        if not nodes:
            if return_intermediate:
                return initial_df, {}, {}
            return initial_df, {}

        node_map = {n["id"]: n for n in nodes}
        node_timings = {}
        # 存储节点输出：{node_id: {"output_name": df}}
        # 单输出节点转换为 {"output_1": df}
        node_outputs: Dict[str, Dict[str, pd.DataFrame]] = {}
        node_errors: Dict[str, dict] = {}  # 记录每个节点的错误

        topo_order = self._topological_sort(node_map, connections)

        for node_id in topo_order:
            node_def = node_map[node_id]
            node_type = node_def.get("type", "")
            node_name = node_def.get("name", node_id)
            params = node_def.get("parameters", {})

            # 注入特殊上下文变量（供 for_each 等节点使用）
            workflow_context["__workflow_json__"] = workflow_json
            workflow_context["__current_node_id__"] = node_id
            workflow_context["__node_outputs__"] = node_outputs  # 供 merge 等节点使用

            node_class = self._node_registry.get(node_type)
            if not node_class:
                error_info = {"node_id": node_id, "node_name": node_name,
                              "error": f"未知节点类型: {node_type}"}
                node_errors[node_id] = error_info
                # 继续执行其他节点，但记录错误
                continue

            try:
                input_df = self._collect_inputs(node_id, node_def, node_outputs, connections)
                # 无上游时回退到初始数据，保证首节点可消费外部输入样本。
                if input_df.empty and not node_def.get("inputs"):
                    input_df = initial_df
                t0 = time.time()
                node_instance = node_class()
                # 尝试传入 context 参数（向后兼容：老节点没有 context 参数也能跑）
                try:
                    output = node_instance.process(input_df, params, context=workflow_context)
                except TypeError:
                    # 老节点没有 context 参数，回退到 2 参数调用
                    output = node_instance.process(input_df, params)
                elapsed = round(time.time() - t0, 3)
                node_timings[node_name] = elapsed

                # 处理输出：单输出转换为多输出格式
                if isinstance(output, dict):
                    node_outputs[node_id] = output
                else:
                    node_outputs[node_id] = {"output_1": output}
            except Exception as e:
                # 捕获节点执行错误，记录详细信息
                import traceback
                error_info = {
                    "node_id": node_id,
                    "node_name": node_name,
                    "node_type": node_type,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                }
                node_errors[node_id] = error_info
                # 打印错误到控制台
                print(f"\n❌ 节点执行失败: {node_name} ({node_type})")
                print(f"   错误: {e}")
                # 不中断整个工作流，继续执行其他节点

            # 如果指定了 stop_at_node_id，执行到该节点后停止
            if stop_at_node_id and node_id == stop_at_node_id:
                break

        final = self._get_final_output(node_outputs, connections)
        final_df = final if final is not None else initial_df

        # 为了向后兼容，返回中间输出时将多输出转换为单输出（取 output_1 或第一个）
        if return_intermediate:
            compat_outputs = {}
            for nid, outputs in node_outputs.items():
                if "output_1" in outputs:
                    compat_outputs[nid] = outputs["output_1"]
                elif outputs:
                    # 取第一个输出
                    compat_outputs[nid] = list(outputs.values())[0]
                else:
                    compat_outputs[nid] = pd.DataFrame()
            return final_df, node_timings, compat_outputs
        return final_df, node_timings

    def execute_with_errors(self, workflow_json: dict, initial_df: pd.DataFrame,
                            workflow_context: Optional[dict] = None,
                            return_intermediate: bool = False,
                            stop_at_node_id: Optional[str] = None) -> tuple:
        """
        执行工作流并返回详细错误信息（调试用）。
        参数:
          workflow_context: 可选，工作流全局上下文（dict）
        返回:
          return_intermediate=False: (final_df, timings, error_summary|None)
          return_intermediate=True:  (final_df, timings, node_outputs, error_summary|None)
        """
        if workflow_context is None:
            workflow_context = {}

        nodes = workflow_json.get("nodes", [])
        connections = workflow_json.get("connections", {})

        if not nodes:
            if return_intermediate:
                return initial_df, {}, {}, None
            return initial_df, {}, None

        node_map = {n["id"]: n for n in nodes}
        node_timings = {}
        # 存储节点输出：{node_id: {"output_name": df}}
        node_outputs: Dict[str, Dict[str, pd.DataFrame]] = {}
        node_errors: Dict[str, dict] = {}

        topo_order = self._topological_sort(node_map, connections)

        for node_id in topo_order:
            node_def = node_map[node_id]
            node_type = node_def.get("type", "")
            node_name = node_def.get("name", node_id)
            params = node_def.get("parameters", {})

            # 注入特殊上下文变量（供 for_each 等节点使用）
            workflow_context["__workflow_json__"] = workflow_json
            workflow_context["__current_node_id__"] = node_id
            workflow_context["__node_outputs__"] = node_outputs  # 供 merge 等节点使用

            node_class = self._node_registry.get(node_type)
            if not node_class:
                error_info = {"node_id": node_id, "node_name": node_name,
                              "error": f"未知节点类型: {node_type}"}
                node_errors[node_id] = error_info
                continue

            try:
                input_df = self._collect_inputs(node_id, node_def, node_outputs, connections)
                if input_df.empty and not node_def.get("inputs"):
                    input_df = initial_df
                t0 = time.time()
                node_instance = node_class()
                # 尝试传入 context 参数（向后兼容：老节点没有 context 参数也能跑）
                try:
                    output = node_instance.process(input_df, params, context=workflow_context)
                except TypeError:
                    # 老节点没有 context 参数，回退到 2 参数调用
                    output = node_instance.process(input_df, params)
                elapsed = round(time.time() - t0, 3)
                node_timings[node_name] = elapsed

                # 处理输出：单输出转换为多输出格式
                if isinstance(output, dict):
                    node_outputs[node_id] = output
                else:
                    node_outputs[node_id] = {"output_1": output}
            except Exception as e:
                import traceback
                error_info = {
                    "node_id": node_id,
                    "node_name": node_name,
                    "node_type": node_type,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                }
                node_errors[node_id] = error_info
                print(f"\n❌ 节点执行失败: {node_name} ({node_type})")
                print(f"   错误: {e}")

            if stop_at_node_id and node_id == stop_at_node_id:
                break

        final = self._get_final_output(node_outputs, connections)
        final_df = final if final is not None else initial_df
        error_summary = node_errors if node_errors else None

        # 为了向后兼容，返回中间输出时将多输出转换为单输出
        if return_intermediate:
            compat_outputs = {}
            for nid, outputs in node_outputs.items():
                if "output_1" in outputs:
                    compat_outputs[nid] = outputs["output_1"]
                elif outputs:
                    compat_outputs[nid] = list(outputs.values())[0]
                else:
                    compat_outputs[nid] = pd.DataFrame()
            return final_df, node_timings, compat_outputs, error_summary
        return final_df, node_timings, error_summary

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

    def _collect_inputs(self, node_id: str, node_def: dict, node_outputs: Dict[str, Dict[str, pd.DataFrame]], connections: dict) -> pd.DataFrame:
        """收集节点的输入数据。

        支持两种连接格式：
        1. 旧格式：connections[src_id] = [target_ids] 或 [{"node": target_id}] - 单输出（output_1）
        2. 新格式：connections[src_id] = {"output_name": [targets]} - 多输出
        """
        inputs = node_def.get("inputs", [])
        # 兼容仅提供 connections 的工作流定义，自动推导上游节点。
        if not inputs:
            inferred_inputs = []
            for src_id, targets in connections.items():
                # 检查这个源节点的输出是否连接到当前节点
                if isinstance(targets, list):
                    # 旧格式：单输出
                    for t in targets:
                        tgt = t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t)
                        if tgt == node_id:
                            inferred_inputs.append({"node": src_id, "output": "output_1"})
                elif isinstance(targets, dict):
                    # 新格式：多输出
                    for output_name, target_list in targets.items():
                        if isinstance(target_list, list):
                            for t in target_list:
                                tgt = t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t)
                                if tgt == node_id:
                                    inferred_inputs.append({"node": src_id, "output": output_name})
            inputs = inferred_inputs

        if not inputs:
            return pd.DataFrame()

        frames = []
        for inp in inputs:
            src_id = inp.get("node", inp.get("id", ""))
            output_name = inp.get("output", "output_1")  # 默认使用 output_1

            if src_id in node_outputs:
                outputs = node_outputs[src_id]
                if output_name in outputs:
                    df = outputs[output_name]
                    if not df.empty:
                        frames.append(df)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _get_final_output(self, node_outputs: Dict[str, Dict[str, pd.DataFrame]], connections: dict) -> pd.DataFrame:
        """获取工作流的最终输出。

        从没有出边的节点（终点节点）中获取输出。
        对于多输出节点，优先返回 output_1，否则返回第一个输出。
        """
        all_ids = set(node_outputs.keys())
        # 终点节点定义为"没有任何出边的节点"。
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
                if sid in node_outputs:
                    outputs = node_outputs[sid]
                    # 优先返回 output_1
                    if "output_1" in outputs and not outputs["output_1"].empty:
                        return outputs["output_1"]
                    # 否则返回第一个非空输出
                    for output_name, df in outputs.items():
                        if not df.empty:
                            return df

        if node_outputs:
            last_id = list(node_outputs.keys())[-1]
            outputs = node_outputs[last_id]
            if "output_1" in outputs:
                return outputs["output_1"]
            elif outputs:
                return list(outputs.values())[0]
        return pd.DataFrame()


_workflow_engine = WorkflowEngine()


def get_workflow_engine() -> WorkflowEngine:
    return _workflow_engine
