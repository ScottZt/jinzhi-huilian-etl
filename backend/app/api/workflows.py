"""工作流 API — CRUD + 预览执行。"""
import math
from fastapi import APIRouter
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import uuid
import pandas as pd

from app.persistence import sqlite_repo
from app.core.workflow_engine import get_workflow_engine
from app.core.license_manager import check_feature_or_raise, check_feature
from app.core.workflow_presets import get_workflow_presets

router = APIRouter()


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    workflow_json: dict


class WorkflowNodeUpdate(BaseModel):
    workflow_json: dict


class WorkflowPreview(BaseModel):
    workflow_json: dict
    sample_data: Optional[List[dict]] = None


class PresetRunRequest(BaseModel):
    auto_seed: bool = True
    overwrite_existing: bool = False


class SeedPresetsRequest(BaseModel):
    """按需导入预设请求。keys 为空则导入全部。"""
    keys: Optional[List[str]] = None
    overwrite_existing: bool = False


def _json_safe(value: Any) -> Any:
    """将返回数据转换为严格 JSON 安全格式，避免 NaN/Inf 导致响应序列化失败。"""
    # Python float 中的 NaN/Inf 在严格 JSON 中非法，需要统一转为 None。
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    # 递归处理字典结构，确保嵌套字段同样安全。
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    # 递归处理列表结构，确保数组中的异常数值也被替换。
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


@router.get("/", response_model=List[dict])
async def get_all_workflows():
    return sqlite_repo.list_workflows()


# ---------- 静态路由必须在 /{workflow_id} 之前注册 ----------

@router.get("/presets")
async def list_workflow_presets():
    """列出内置预制工作流清单。"""
    presets = get_workflow_presets()
    result = []
    for item in presets:
        nodes = item.get("workflow_json", {}).get("nodes", [])
        types = {n.get("type") for n in nodes}
        result.append({
            "key": item["key"],
            "name": item["name"],
            "description": item["description"],
            "sample_rows": len(item.get("sample_data", [])),
            "has_source": "source_fetch" in types,
            "has_target": "target_write" in types,
            "node_count": len(nodes),
        })
    return result


@router.post("/seed-presets")
async def seed_workflow_presets(body: Optional[SeedPresetsRequest] = None):
    """写入内置预制工作流。keys 指定时只导入对应预设，否则导入全部。"""
    if body is None:
        body = SeedPresetsRequest()
    saved: List[Dict[str, Any]] = []
    for preset in get_workflow_presets():
        # keys 非空时只导入指定的预设
        if body.keys and preset["key"] not in body.keys:
            continue
        wf = _upsert_workflow_by_name(
            name=preset["name"],
            description=preset["description"],
            workflow_json=preset["workflow_json"],
            overwrite_existing=body.overwrite_existing,
        )
        saved.append({"id": wf["id"], "name": wf["name"], "key": preset["key"]})
    return {"count": len(saved), "workflows": saved}


@router.post("/run-presets")
async def run_workflow_presets(body: Optional[PresetRunRequest] = None):
    """执行所有预制工作流并返回结果，确保样例可跑通。"""
    if body is None:
        body = PresetRunRequest()
    if body.auto_seed:
        await seed_workflow_presets(overwrite_existing=body.overwrite_existing)

    runs: List[Dict[str, Any]] = []
    for preset in get_workflow_presets():
        df = pd.DataFrame(preset.get("sample_data", []))
        result = _execute_workflow_preview(preset["workflow_json"], df)
        runs.append(
            {
                "key": preset["key"],
                "name": preset["name"],
                "input_rows": len(df),
                "result": result,
            }
        )
    return {"count": len(runs), "runs": runs}


@router.get("/nodes")
async def list_node_types():
    """列出所有注册的节点类型。"""
    from app.nodes import NodeRegistry, register_all_nodes, discover_custom_plugins
    register_all_nodes()
    discover_custom_plugins()
    return [
        {"type": nt, "info": NodeRegistry.get_info(nt)}
        for nt in NodeRegistry.list_types()
    ]


@router.post("/seed-demo")
async def seed_demo_workflow():
    """兼容旧接口：写入全部预制工作流。"""
    return await seed_workflow_presets(overwrite_existing=False)


@router.post("/create-plugin")
async def create_plugin(body: dict):
    """创建自定义插件（写入 plugins/ 目录）。"""
    import os
    from pathlib import Path

    name = body.get("name", "")
    node_type = body.get("node_type", "")
    category = body.get("category", "数据处理")
    code = body.get("code", "")
    display_name = body.get("display_name", name)

    if not name or not node_type or not code:
        return {"success": False, "message": "name、node_type、code 为必填项"}

    if not code.strip().startswith("def process"):
        return {"success": False, "message": "代码必须包含 def process(df, params): 函数"}

    plugins_dir = Path(__file__).parent.parent.parent / "plugins"
    plugins_dir.mkdir(exist_ok=True)

    fname = f"{node_type}.py"
    fpath = plugins_dir / fname

    func_body = "\n        ".join(code.strip().split("\n"))

    content = f'''"""自定义插件: {name}"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class CustomNode(BaseNode):
    node_type = "{node_type}"
    display_name = "{display_name}"
    category = "{category}"

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        {func_body}
'''

    try:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "message": f"插件已保存到 {fname}，可在「插件中心」点「重新加载」立即生效"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/plugins/reload")
async def reload_plugins_endpoint():
    """热加载插件：清空非 built-in 注册项，重新扫描 plugins/，刷新 official.json 缓存。"""
    from app.nodes import reload_plugins
    try:
        result = reload_plugins()
        removed_count = len(result['removed'])
        removed_hint = f"，移除 {removed_count} 个旧插件" if removed_count else ""
        return {
            "success": True,
            "message": (
                f"加载完成：新增 {len(result['loaded'])} 个插件"
                f"{removed_hint}，官方清单 {result['official_count']} 条"
            ),
            "detail": result,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.delete("/plugins/{node_type}")
async def delete_plugin(node_type: str):
    """删除自定义插件：从 plugins/ 删除源文件并卸载注册项。"""
    import os
    from pathlib import Path
    from app.nodes import NodeRegistry, _builtin_nodes

    # 安全检查：built-in 不能删
    if node_type in _builtin_nodes:
        return {"success": False, "message": f"内置节点 {node_type} 不可删除"}

    plugins_dir = Path(__file__).parent.parent.parent / "plugins"
    fpath = plugins_dir / f"{node_type}.py"
    removed_file = False
    if fpath.exists():
        try:
            os.remove(fpath)
            removed_file = True
        except Exception as e:
            return {"success": False, "message": f"删除文件失败: {e}"}

    # 从注册表移除
    NodeRegistry.unregister(node_type)

    if not removed_file and NodeRegistry.get(node_type) is None:
        return {"success": False, "message": f"未找到插件 {node_type}"}
    return {"success": True, "message": f"已删除插件 {node_type}"}


# ---------- /{workflow_id} 通配路由（必须放在静态路由之后） ----------


def _execute_workflow_preview(workflow_json: dict, df: Optional[pd.DataFrame],
                               max_rows: int = 50, stop_at_node_id: Optional[str] = None):
    """执行工作流并返回结果，包含每个节点的中间输出和错误信息。"""
    import json
    import logging
    logger = logging.getLogger("workflow_preview")

    if df is None:
        df = pd.DataFrame()

    # 输出节点参数详情
    print("\n" + "-" * 80)
    print("🔧 [工作流执行] 节点参数详情:")
    print("-" * 80)
    nodes = workflow_json.get("nodes", [])
    for idx, node in enumerate(nodes, 1):
        node_name = node.get("name", node.get("id", "unknown"))
        node_type = node.get("type", "unknown")
        params = node.get("parameters", {})
        print(f"\n[{idx}] {node_name} (类型: {node_type})")
        print(f"    参数: {json.dumps(params, ensure_ascii=False, indent=6)}")
    print("\n" + "-" * 80 + "\n")

    engine = get_workflow_engine()
    engine.register_all()

    result_df, timings, all_outputs, node_errors = engine.execute_with_errors(
        workflow_json, df, return_intermediate=True, stop_at_node_id=stop_at_node_id
    )

    # 收集每个节点的中间输出（供前端数据预览面板使用）
    node_outputs = {}

    print("\n" + "-" * 80)
    print("📊 [工作流执行结果] 节点输出统计:")
    print("-" * 80)

    for node_def in nodes:
        nid = node_def.get("id", "")
        name = node_def.get("name", nid)
        # 如果该节点有错误，跳过输出收集
        if nid in (node_errors or {}):
            err = node_errors[nid]
            print(f"❌ {name} ({node_def.get('type', '')}): 执行失败 - {err.get('error', 'Unknown error')}")
            continue
        ndf = all_outputs.get(nid)
        if ndf is not None and not ndf.empty:
            node_outputs[nid] = {
                "name": name,
                "type": node_def.get("type", ""),
                "rows": len(ndf),
                "columns": list(ndf.columns),
                "preview": _json_safe(ndf.head(max_rows).to_dict("records")),
                "time_seconds": timings.get(name, 0),
            }
            print(f"✅ {name} ({node_def.get('type', '')}): {len(ndf)} 行, {len(ndf.columns)} 列, 耗时 {timings.get(name, 0):.3f}s")
        else:
            print(f"⚠️  {name} ({node_def.get('type', '')}): 无输出")

    print("-" * 80 + "\n")

    # 输出最终结果
    print("\n" + "=" * 80)
    print("🎯 [工作流执行完成] 最终结果:")
    print("=" * 80)
    print(f"总行数: {len(result_df)}")
    print(f"列名: {list(result_df.columns)}")
    print(f"总耗时: {sum(timings.values()):.3f}s")
    if node_errors:
        print(f"⚠️  {len(node_errors)} 个节点执行失败")
    print("=" * 80 + "\n")

    result = {
        "rows": len(result_df),
        "columns": list(result_df.columns),
        "preview": _json_safe(result_df.head(max_rows).to_dict("records")),
        "timings": _json_safe(timings),
        "node_outputs": node_outputs,
    }

    # 如果有错误，添加错误信息
    if node_errors:
        # 格式化错误信息供前端显示
        formatted_errors = []
        for nid, err in node_errors.items():
            formatted_errors.append({
                "node_id": nid,
                "node_name": err.get("node_name", nid),
                "node_type": err.get("node_type", ""),
                "error": err.get("error", ""),
                "error_type": err.get("error_type", ""),
                "traceback": err.get("traceback", ""),
            })
        result["errors"] = formatted_errors
        # 第一个错误作为主错误（兼容旧前端）
        first_error = formatted_errors[0]
        result["error"] = f"节点 {first_error['node_name']} 执行失败: {first_error['error']}"

    return result


def _upsert_workflow_by_name(name: str, description: str, workflow_json: dict, overwrite_existing: bool) -> dict:
    """按名称写入工作流，支持覆盖或复用。"""
    existing = sqlite_repo.list_workflows()
    for wf in existing:
        if wf.get("name") == name:
            if overwrite_existing:
                record = {
                    "id": wf["id"],
                    "name": name,
                    "description": description,
                    "workflow_json": workflow_json,
                }
                return sqlite_repo.save_workflow(record)
            return wf
    record = {
        "id": str(uuid.uuid4()),
        "name": name,
        "description": description,
        "workflow_json": workflow_json,
    }
    return sqlite_repo.save_workflow(record)


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    data = sqlite_repo.get_workflow(workflow_id)
    if not data:
        return {"error": "Workflow not found"}
    return data


@router.post("/")
async def create_workflow(body: WorkflowCreate):
    check_feature_or_raise("max_workflows")  # free: 1, personal: 5, professional: unlimited
    workflow_id = str(uuid.uuid4())
    record = {
        "id": workflow_id,
        "name": body.name,
        "description": body.description or "",
        "workflow_json": body.workflow_json,
    }
    sqlite_repo.save_workflow(record)
    return {"id": workflow_id, **record}


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, body: WorkflowCreate):
    check_feature_or_raise("max_workflows")
    record = {
        "id": workflow_id,
        "name": body.name,
        "description": body.description or "",
        "workflow_json": body.workflow_json,
    }
    sqlite_repo.save_workflow(record)
    return record


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    deleted = sqlite_repo.delete_workflow(workflow_id)
    return {"deleted": deleted}


@router.post("/{workflow_id}/preview")
async def preview_workflow(workflow_id: str):
    """执行工作流预览（带 sample_data 时使用自定义数据，否则使用空 DataFrame）。"""
    import json
    import logging
    logger = logging.getLogger("workflow_preview")

    wf_data = sqlite_repo.get_workflow(workflow_id)
    if not wf_data:
        return {"error": "Workflow not found"}

    # 输出完整的 workflow_json 到终端，方便调试
    print("\n" + "=" * 80)
    print(f"📋 [工作流预览] workflow_id={workflow_id}，完整 workflow_json:")
    print("=" * 80)
    print(json.dumps(wf_data["workflow_json"], ensure_ascii=False, indent=2))
    print("=" * 80 + "\n")

    return _execute_workflow_preview(wf_data["workflow_json"], None)


@router.get("/{workflow_id}/preview")
async def preview_workflow_get_compat(workflow_id: str):
    """兼容旧前端缓存：允许 GET 方式访问工作流预览。"""
    return await preview_workflow(workflow_id)


@router.post("/preview")
async def preview_workflow_direct(body: WorkflowPreview):
    """直接预览工作流（传入 workflow_json + 可选 sample_data）。"""
    import json
    import logging
    logger = logging.getLogger("workflow_preview")

    # 输出完整的 workflow_json 到终端，方便调试
    print("\n" + "=" * 80)
    print("📋 [工作流预览] 接收到请求，完整 workflow_json:")
    print("=" * 80)
    print(json.dumps(body.workflow_json, ensure_ascii=False, indent=2))
    print("=" * 80 + "\n")

    df = None
    if body.sample_data:
        df = pd.DataFrame(body.sample_data)
    return _execute_workflow_preview(body.workflow_json, df)


class NodeExecuteRequest(BaseModel):
    workflow_json: dict
    node_id: str
    sample_data: Optional[List[dict]] = None


@router.post("/execute-node")
async def execute_single_node(body: NodeExecuteRequest):
    """
    执行单个节点（含其上游依赖路径），用于节点级调试。
    返回目标节点的输入数据、输出数据、执行时间。
    """
    import json
    import logging
    logger = logging.getLogger("node_execute")

    workflow_json = body.workflow_json
    target_node_id = body.node_id

    # 找到目标节点
    nodes = workflow_json.get("nodes", [])
    target_node = None
    for n in nodes:
        if n.get("id") == target_node_id:
            target_node = n
            break

    if not target_node:
        return {"error": f"节点 {target_node_id} 不存在"}

    # 截取从根到目标节点的子图（只执行必要路径）
    sub_graph = _extract_upstream_subgraph(workflow_json, target_node_id)

    logger.info(f"执行节点 {target_node.get('name', target_node_id)}，上游子图包含 {len(sub_graph['nodes'])} 个节点")

    df = None
    if body.sample_data:
        df = pd.DataFrame(body.sample_data)

    engine = get_workflow_engine()
    engine.register_all()

    # 执行子图，保留所有中间输出（用于显示目标节点的输入）
    result_df, timings, all_outputs, node_errors = engine.execute_with_errors(
        sub_graph, df, return_intermediate=True, stop_at_node_id=target_node_id
    )

    # 构造目标节点的输入数据（所有上游节点输出 concat）
    connections = workflow_json.get("connections", {})
    input_df = _collect_node_inputs(target_node_id, target_node, all_outputs, connections)
    output_df = all_outputs.get(target_node_id)
    error_info = (node_errors or {}).get(target_node_id)

    result = {
        "node_id": target_node_id,
        "node_name": target_node.get("name", target_node_id),
        "node_type": target_node.get("type", ""),
        "executed_nodes": list(timings.keys()),
        "time_seconds": timings.get(target_node.get("name", target_node_id), 0),
    }

    if error_info:
        result["error"] = error_info.get("error", "Unknown error")
        result["error_type"] = error_info.get("error_type", "")
        result["traceback"] = error_info.get("traceback", "")
        # 即使目标节点报错，也返回上游节点的输入数据供调试
        if input_df is not None and not input_df.empty:
            result["input"] = {
                "rows": len(input_df),
                "columns": list(input_df.columns),
                "preview": _json_safe(input_df.head(50).to_dict("records")),
            }
    else:
        if input_df is not None and not input_df.empty:
            result["input"] = {
                "rows": len(input_df),
                "columns": list(input_df.columns),
                "preview": _json_safe(input_df.head(50).to_dict("records")),
            }
        if output_df is not None:
            result["output"] = {
                "rows": len(output_df),
                "columns": list(output_df.columns),
                "preview": _json_safe(output_df.head(50).to_dict("records")),
            }

    # 如果上游节点有错误，也一并返回
    upstream_errors = []
    for nid, err in (node_errors or {}).items():
        if nid != target_node_id:
            upstream_errors.append({
                "node_id": nid,
                "node_name": err.get("node_name", nid),
                "error": err.get("error", ""),
                "error_type": err.get("error_type", ""),
            })
    if upstream_errors:
        result["upstream_errors"] = upstream_errors

    return result


def _extract_upstream_subgraph(workflow_json: dict, target_node_id: str) -> dict:
    """
    提取从根节点到目标节点的上游子图。
    只保留对目标节点有贡献的节点和连接。
    """
    nodes = workflow_json.get("nodes", [])
    connections = workflow_json.get("connections", {})

    # 构建反向邻接表（子 -> 父）
    reverse_adj: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
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
        for tid in target_ids:
            if tid in reverse_adj:
                reverse_adj[tid].append(src_id)

    # 从目标节点向上游 BFS，收集所有祖先节点
    needed_ids = set()
    queue = [target_node_id]
    while queue:
        nid = queue.pop(0)
        if nid in needed_ids:
            continue
        needed_ids.add(nid)
        for parent_id in reverse_adj.get(nid, []):
            if parent_id not in needed_ids:
                queue.append(parent_id)

    # 构造子图
    sub_nodes = [n for n in nodes if n["id"] in needed_ids]
    sub_connections = {}
    for src_id, targets in connections.items():
        if src_id not in needed_ids:
            continue
        # 过滤目标，只保留在子图中的
        if isinstance(targets, list):
            new_targets = []
            for t in targets:
                tid = t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t)
                if tid in needed_ids:
                    new_targets.append(t)
            if new_targets:
                sub_connections[src_id] = new_targets
        elif isinstance(targets, dict):
            new_dict = {}
            for k, values in targets.items():
                if isinstance(values, list):
                    new_values = []
                    for t in values:
                        tid = t.get("node", t.get("id", "")) if isinstance(t, dict) else str(t)
                        if tid in needed_ids:
                            new_values.append(t)
                    if new_values:
                        new_dict[k] = new_values
            if new_dict:
                sub_connections[src_id] = new_dict

    return {"nodes": sub_nodes, "connections": sub_connections}


def _collect_node_inputs(node_id: str, node_def: dict, node_outputs: dict, connections: dict):
    """收集指定节点的输入数据（复用引擎逻辑）。"""
    inputs = node_def.get("inputs", [])
    if not inputs:
        inferred = []
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
                inferred.append({"node": src_id})
        inputs = inferred
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
