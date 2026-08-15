"""分批处理节点 — 将数据分成多个批次处理。"""
import logging
import pandas as pd
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class SplitBatchesNode(BaseNode):
    node_type = "split_batches"
    display_name = "分批处理"
    category = "流程控制"
    params_schema = {
        "batch_size": {"type": "number", "label": "批次大小", "default": 100,
                       "placeholder": "每个批次的数据行数"},
        "parallel": {"type": "checkbox", "label": "并行处理", "default": False},
        "max_parallel": {"type": "number", "label": "最大并行数", "default": 4,
                         "placeholder": "并行处理时的最大并发数"},
        "error_handling": {"type": "select", "label": "错误处理", "options": ["continue", "stop"], "default": "continue",
                           "placeholder": "continue=跳过错误批次, stop=遇到错误停止"},
    }

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> pd.DataFrame:
        """
        将数据分成多个批次，对每个批次执行下游节点链。
        """
        if df.empty:
            return df

        batch_size = int(params.get("batch_size", 100))
        parallel = params.get("parallel", False)
        max_parallel = int(params.get("max_parallel", 4))
        error_handling = params.get("error_handling", "continue")

        if batch_size <= 0:
            logger.warning("SplitBatchesNode: 批次大小必须大于 0")
            return df

        if batch_size >= len(df):
            logger.info("SplitBatchesNode: 数据量小于批次大小，不需要分批")
            return df

        # 分批
        batches = [df[i:i + batch_size] for i in range(0, len(df), batch_size)]
        logger.info("SplitBatchesNode: 将 %d 行数据分成 %d 个批次", len(df), len(batches))

        # 从 context 读取 workflow_json 和自己的 node_id
        if context is None:
            logger.warning("SplitBatchesNode: context 为空，无法执行子图")
            return df

        workflow_json = context.get("__workflow_json__")
        current_node_id = context.get("__current_node_id__")

        if not workflow_json or not current_node_id:
            logger.warning("SplitBatchesNode: 缺少 __workflow_json__ 或 __current_node_id__")
            return df

        # 提取下游子图
        sub_workflow = self._extract_downstream_subgraph(current_node_id, workflow_json)
        if not sub_workflow["nodes"]:
            logger.warning("SplitBatchesNode: 下游子图为空")
            return df

        # 执行每个批次
        from app.core.workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        engine.register_all()

        all_outputs = []

        if parallel and len(batches) > 1:
            # 并行处理
            all_outputs = self._process_parallel(engine, sub_workflow, batches, context, max_parallel, error_handling)
        else:
            # 串行处理
            all_outputs = self._process_sequential(engine, sub_workflow, batches, context, error_handling)

        # 合并所有输出
        if all_outputs:
            final_df = pd.concat(all_outputs, ignore_index=True)
            logger.info("SplitBatchesNode: 分批处理完成，合并 %d 个批次，共 %d 行", len(all_outputs), len(final_df))
            return final_df
        else:
            logger.warning("SplitBatchesNode: 所有批次执行失败或输出为空")
            return df

    def _process_sequential(self, engine, sub_workflow, batches, context, error_handling):
        """串行处理所有批次。"""
        outputs = []
        for idx, batch_df in enumerate(batches):
            logger.info("SplitBatchesNode: 处理第 %d/%d 个批次（%d 行）", idx + 1, len(batches), len(batch_df))

            try:
                result = engine.execute(sub_workflow, batch_df.copy(), workflow_context=context.copy())
                if isinstance(result, tuple):
                    result_df = result[0]
                else:
                    result_df = result

                if result_df is not None and not result_df.empty:
                    outputs.append(result_df)
            except Exception as e:
                logger.error("SplitBatchesNode: 第 %d 个批次执行失败 - %s", idx + 1, e)
                if error_handling == "stop":
                    raise

        return outputs

    def _process_parallel(self, engine, sub_workflow, batches, context, max_parallel, error_handling):
        """并行处理所有批次。"""
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
        except ImportError:
            logger.warning("SplitBatchesNode: 不支持并行处理，回退到串行模式")
            return self._process_sequential(engine, sub_workflow, batches, context, error_handling)

        outputs = []
        futures = {}

        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
            # 提交所有任务
            for idx, batch_df in enumerate(batches):
                future = executor.submit(
                    self._execute_batch,
                    engine, sub_workflow, batch_df, context, idx, len(batches)
                )
                futures[future] = idx

            # 收集结果
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    result_df = future.result()
                    if result_df is not None and not result_df.empty:
                        outputs.append(result_df)
                except Exception as e:
                    logger.error("SplitBatchesNode: 第 %d 个批次执行失败 - %s", idx + 1, e)
                    if error_handling == "stop":
                        raise

        return outputs

    def _execute_batch(self, engine, sub_workflow, batch_df, context, batch_idx, total_batches):
        """执行单个批次（用于并行处理）。"""
        logger.info("SplitBatchesNode: 处理第 %d/%d 个批次（%d 行）", batch_idx + 1, total_batches, len(batch_df))
        result = engine.execute(sub_workflow, batch_df.copy(), workflow_context=context.copy())
        if isinstance(result, tuple):
            return result[0]
        return result

    def _extract_downstream_subgraph(self, split_node_id: str, workflow_json: dict) -> dict:
        """提取 split_batches 节点的下游子图（不包括 split_batches 自身）"""
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
        queue = [split_node_id]
        visited = {split_node_id}

        while queue:
            current = queue.pop(0)
            for next_id in adj.get(current, []):
                if next_id not in visited and next_id != split_node_id:
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
