"""循环遍历节点 — 对列表逐项执行下游节点链。"""
import json
import logging
import pandas as pd
from typing import Optional, List, Any
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class ForEachNode(BaseNode):
    node_type = "for_each"
    display_name = "循环遍历"
    category = "流程控制"
    params_schema = {
        "items": {"type": "textarea", "label": "循环列表",
                  "default": "[\"item1\", \"item2\"]",
                  "placeholder": "JSON 数组：[\"a\", \"b\", \"c\"]\n或逗号分隔：a, b, c\n或从 context 读取变量名：{{my_list}}"},
        "item_var": {"type": "text", "label": "当前项变量名", "default": "current_item",
                     "placeholder": "下游节点通过 context.get('current_item') 读取"},
        "index_var": {"type": "text", "label": "索引变量名", "default": "item_index",
                      "placeholder": "下游节点通过 context.get('item_index') 读取"},
        "max_iterations": {"type": "number", "label": "最大迭代次数", "default": 1000,
                           "placeholder": "防止死循环"},
    }

    def process(self, df: pd.DataFrame, params: dict,
                context: Optional[dict] = None) -> pd.DataFrame:
        if context is None:
            logger.warning("ForEachNode: context 为空，无法执行循环")
            return df

        # 1. 解析 items 列表
        items = self._parse_items(params.get("items", "[]"), context)
        if not items:
            logger.warning("ForEachNode: items 列表为空，跳过循环")
            return df

        item_var = params.get("item_var", "current_item")
        index_var = params.get("index_var", "item_index")
        max_iterations = int(params.get("max_iterations", 1000))

        # 限制迭代次数
        if len(items) > max_iterations:
            logger.warning("ForEachNode: items 数量 %d 超过上限 %d，截断", len(items), max_iterations)
            items = items[:max_iterations]

        # 2. 从 context 读取 workflow_json 和自己的 node_id
        workflow_json = context.get("__workflow_json__")
        current_node_id = context.get("__current_node_id__")

        if not workflow_json or not current_node_id:
            logger.warning("ForEachNode: 缺少 __workflow_json__ 或 __current_node_id__，无法执行子图")
            # 降级处理：只做第一项
            context[item_var] = items[0]
            context[index_var] = 0
            return df

        # 3. 提取下游子图
        sub_workflow = self._extract_downstream_subgraph(current_node_id, workflow_json)
        if not sub_workflow["nodes"]:
            logger.warning("ForEachNode: 下游子图为空，跳过循环")
            return df

        # 4. 对每项递归调用引擎执行子图
        from app.core.workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        engine.register_all()

        all_outputs = []
        for idx, item in enumerate(items):
            logger.info("ForEachNode: 处理第 %d/%d 项: %s", idx + 1, len(items), item)

            # 注入当前项到 context
            context[item_var] = item
            context[index_var] = idx

            # 递归执行子图
            try:
                result_df = engine.execute(sub_workflow, df.copy(), workflow_context=context)
                if isinstance(result_df, tuple):
                    result_df = result_df[0]  # execute 返回 (df, timings)
                if result_df is not None and not result_df.empty:
                    all_outputs.append(result_df)
            except Exception as e:
                logger.error("ForEachNode: 第 %d 项执行失败 - %s", idx + 1, e)
                continue

        # 5. 合并所有输出
        if all_outputs:
            final_df = pd.concat(all_outputs, ignore_index=True)
            logger.info("ForEachNode: 循环完成，合并 %d 个输出，共 %d 行", len(all_outputs), len(final_df))
            return final_df
        else:
            logger.warning("ForEachNode: 所有项执行失败或输出为空")
            return df

    def _parse_items(self, items_str: str, context: dict) -> List[Any]:
        """解析 items 列表，支持 JSON 数组、逗号分隔、context 变量引用"""
        items_str = items_str.strip()

        # 检查是否是 context 变量引用：{{var_name}}
        if items_str.startswith("{{") and items_str.endswith("}}"):
            var_name = items_str[2:-2].strip()
            items = context.get(var_name, [])
            if isinstance(items, list):
                return items
            else:
                logger.warning("ForEachNode: context 变量 %s 不是列表", var_name)
                return []

        # 尝试 JSON 解析
        if items_str.startswith("["):
            try:
                items = json.loads(items_str)
                if isinstance(items, list):
                    return items
            except json.JSONDecodeError as e:
                logger.warning("ForEachNode: JSON 解析失败 - %s", e)

        # 逗号分隔
        if "," in items_str:
            return [item.strip().strip("\"'") for item in items_str.split(",") if item.strip()]

        # 单项
        return [items_str.strip().strip("\"'")] if items_str.strip() else []

    def _extract_downstream_subgraph(self, for_each_node_id: str, workflow_json: dict) -> dict:
        """提取 for_each 节点的下游子图（不包括 for_each 自身）"""
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
        queue = [for_each_node_id]
        visited = {for_each_node_id}

        while queue:
            current = queue.pop(0)
            for next_id in adj.get(current, []):
                if next_id not in visited and next_id != for_each_node_id:
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
