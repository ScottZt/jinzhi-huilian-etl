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
async def seed_workflow_presets(overwrite_existing: bool = False):
    """写入内置预制工作流。"""
    saved: List[Dict[str, Any]] = []
    for preset in get_workflow_presets():
        wf = _upsert_workflow_by_name(
            name=preset["name"],
            description=preset["description"],
            workflow_json=preset["workflow_json"],
            overwrite_existing=overwrite_existing,
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
        return {"success": True, "message": f"插件已保存到 {fname}，重启服务后生效"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ---------- /{workflow_id} 通配路由（必须放在静态路由之后） ----------


def _execute_workflow_preview(workflow_json: dict, df: Optional[pd.DataFrame], max_rows: int = 50):
    """执行工作流并返回结果，包含每个节点的中间输出。"""
    if df is None:
        df = pd.DataFrame()
    engine = get_workflow_engine()
    engine.register_all()
    try:
        result_df, timings, all_outputs = engine.execute(
            workflow_json, df, return_intermediate=True
        )
        preview_records = _json_safe(result_df.head(max_rows).to_dict("records"))

        # 收集每个节点的中间输出（供前端数据预览面板使用）
        node_outputs = {}
        nodes = workflow_json.get("nodes", [])
        for node_def in nodes:
            nid = node_def.get("id", "")
            name = node_def.get("name", nid)
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

        return {
            "rows": len(result_df),
            "columns": list(result_df.columns),
            "preview": preview_records,
            "timings": _json_safe(timings),
            "node_outputs": node_outputs,
        }
    except Exception as e:
        return {"error": str(e)}


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
    wf_data = sqlite_repo.get_workflow(workflow_id)
    if not wf_data:
        return {"error": "Workflow not found"}

    return _execute_workflow_preview(wf_data["workflow_json"], None)


@router.get("/{workflow_id}/preview")
async def preview_workflow_get_compat(workflow_id: str):
    """兼容旧前端缓存：允许 GET 方式访问工作流预览。"""
    return await preview_workflow(workflow_id)


@router.post("/preview")
async def preview_workflow_direct(body: WorkflowPreview):
    """直接预览工作流（传入 workflow_json + 可选 sample_data）。"""
    df = None
    if body.sample_data:
        df = pd.DataFrame(body.sample_data)
    return _execute_workflow_preview(body.workflow_json, df)
