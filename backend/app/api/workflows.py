"""工作流 API — CRUD + 预览执行。"""
from fastapi import APIRouter
from typing import List, Optional
from pydantic import BaseModel
import uuid
import pandas as pd

from app.persistence import sqlite_repo
from app.core.workflow_engine import get_workflow_engine
from app.nodes import register_all_nodes

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


@router.get("/", response_model=List[dict])
async def get_all_workflows():
    return sqlite_repo.list_workflows()


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    data = sqlite_repo.get_workflow(workflow_id)
    if not data:
        return {"error": "Workflow not found"}
    return data


@router.post("/")
async def create_workflow(body: WorkflowCreate):
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


@router.post("/preview")
async def preview_workflow_direct(body: WorkflowPreview):
    """直接预览工作流（传入 workflow_json + 可选 sample_data）。"""
    df = None
    if body.sample_data:
        df = pd.DataFrame(body.sample_data)
    return _execute_workflow_preview(body.workflow_json, df)


def _execute_workflow_preview(workflow_json: dict, df: Optional[pd.DataFrame]):
    """执行工作流并返回结果。"""
    if df is None:
        df = pd.DataFrame()

    engine = get_workflow_engine()
    register_all_nodes()

    try:
        result_df, timings = engine.execute(workflow_json, df)
        return {
            "rows": len(result_df),
            "columns": list(result_df.columns),
            "preview": result_df.head(50).to_dict("records"),
            "timings": timings,
        }
    except Exception as e:
        return {"error": str(e)}


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

    content = f'''"""自定义插件: {name}"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class CustomNode(BaseNode):
    node_type = "{node_type}"
    display_name = "{display_name}"
    category = "{category}"

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        {code}

        return result if "result" in dir() else df
'''
    # Replace the placeholder with actual code
    content = content.replace(
        "def process(df, params):\n        # df: pandas.DataFrame\n        # params: dict\n        return df",
        code
    )

    # Simpler approach: write the class with the user's code
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
