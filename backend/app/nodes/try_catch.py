"""错误处理节点 — 捕获下游节点异常，支持重试和降级。"""
import time
import logging
import pandas as pd
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class TryCatchNode(BaseNode):
    node_type = "try_catch"
    display_name = "错误处理"
    category = "流程控制"
    params_schema = {
        "retry_times": {"type": "number", "label": "重试次数", "default": 3,
                        "placeholder": "失败后重试几次"},
        "retry_delay": {"type": "number", "label": "重试间隔(秒)", "default": 1,
                        "placeholder": "每次重试间隔多少秒"},
        "on_error": {"type": "select", "label": "失败后",
                     "options": ["continue", "abort", "fallback"],
                     "default": "continue",
                     "placeholder": "continue=继续执行 / abort=终止 / fallback=降级处理"},
        "fallback_value": {"type": "text", "label": "降级值", "default": "",
                           "placeholder": "on_error=fallback 时返回的值（JSON 格式）"},
    }

    def process(self, df: pd.DataFrame, params: dict,
                context: Optional[dict] = None) -> pd.DataFrame:
        retry_times = int(params.get("retry_times", 3))
        retry_delay = float(params.get("retry_delay", 1))
        on_error = params.get("on_error", "continue")
        fallback_value = params.get("fallback_value", "")

        # 从 context 读取 workflow_json 和自己的 node_id
        if context is None:
            context = {}
        workflow_json = context.get("__workflow_json__")
        current_node_id = context.get("__current_node_id__")

        if not workflow_json or not current_node_id:
            logger.warning("TryCatchNode: 缺少 __workflow_json__ 或 __current_node_id__")
            return df

        # 提取下游子图
        sub_workflow = self._extract_downstream_subgraph(current_node_id, workflow_json)
        if not sub_workflow["nodes"]:
            logger.warning("TryCatchNode: 下游子图为空")
            return df

        # 执行下游子图，带重试
        from app.core.workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        engine.register_all()

        last_error = None
        for attempt in range(retry_times + 1):
            try:
                logger.info("TryCatchNode: 第 %d 次执行（共 %d 次）", attempt + 1, retry_times + 1)
                result = engine.execute(sub_workflow, df.copy(), workflow_context=context)
                if isinstance(result, tuple):
                    result_df = result[0]
                else:
                    result_df = result

                logger.info("TryCatchNode: 执行成功")
                return result_df if result_df is not None else df

            except Exception as e:
                last_error = e
                logger.warning("TryCatchNode: 第 %d 次执行失败 - %s", attempt + 1, e)

                if attempt < retry_times:
                    logger.info("TryCatchNode: 等待 %.1f 秒后重试...", retry_delay)
                    time.sleep(retry_delay)

        # 所有重试都失败
        logger.error("TryCatchNode: 所有重试失败，on_error=%s", on_error)

        if on_error == "abort":
            raise RuntimeError(f"TryCatchNode: 下游执行失败（已重试 {retry_times} 次）: {last_error}")
        elif on_error == "fallback":
            logger.info("TryCatchNode: 降级处理")
            if fallback_value:
                try:
                    import json
                    fallback_df = pd.DataFrame([json.loads(fallback_value)])
                    return fallback_df
                except Exception as e:
                    logger.error("TryCatchNode: 降级值解析失败 - %s", e)
            return df
        else:  # continue
            logger.warning("TryCatchNode: 继续执行，返回原始 DataFrame")
            return df

    def _extract_downstream_subgraph(self, try_catch_node_id: str, workflow_json: dict) -> dict:
        """提取 try_catch 节点的下游子图（不包括 try_catch 自身）"""
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
        queue = [try_catch_node_id]
        visited = {try_catch_node_id}

        while queue:
            current = queue.pop(0)
            for next_id in adj.get(current, []):
                if next_id not in visited and next_id != try_catch_node_id:
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
