from fastapi import APIRouter
from typing import List
from pydantic import BaseModel
import uuid

from app.models.connection import ConnectionConfig, ConnectionTestResult
from app.core.connection_manager import ConnectionManager
from app.persistence import sqlite_repo

router = APIRouter()
conn_mgr = ConnectionManager()


class ConnectionCreate(BaseModel):
    name: str
    type: str
    config: dict


class ConnectionResponse(BaseModel):
    id: str
    name: str
    type: str
    config: dict


@router.get("/", response_model=List[dict])
async def get_all_connections():
    return sqlite_repo.list_connections()


@router.get("/{conn_id}")
async def get_connection(conn_id: str):
    data = sqlite_repo.get_connection(conn_id)
    if not data:
        return {"error": "Connection not found"}
    return data


@router.post("/")
async def create_connection(body: ConnectionCreate):
    conn_id = str(uuid.uuid4())
    record = {
        "id": conn_id,
        "name": body.name,
        "type": body.type,
        "config": body.config,
    }
    result = sqlite_repo.save_connection(record)
    return result


@router.put("/{conn_id}")
async def update_connection(conn_id: str, body: ConnectionCreate):
    record = {
        "id": conn_id,
        "name": body.name,
        "type": body.type,
        "config": body.config,
    }
    result = sqlite_repo.save_connection(record)
    return result


@router.delete("/{conn_id}")
async def delete_connection(conn_id: str):
    deleted = sqlite_repo.delete_connection(conn_id)
    return {"deleted": deleted}


@router.post("/{conn_id}/test")
async def test_connection(conn_id: str):
    data = sqlite_repo.get_connection(conn_id)
    if not data:
        return {"error": "Connection not found", "success": False}

    config = ConnectionConfig(id=data["id"], name=data["name"], type=data["type"], config=data["config"])
    success, msg, _ = conn_mgr.check_connection(config)
    return {"success": success, "message": msg}


@router.get("/{conn_id}/tables")
async def list_connection_tables(conn_id: str):
    """按连接列出目标库中的表名，供前端下拉选择目标表使用。"""
    data = sqlite_repo.get_connection(conn_id)
    if not data:
        return {"error": "Connection not found", "tables": []}

    config = ConnectionConfig(
        id=data["id"],
        name=data["name"],
        type=data["type"],
        config=data["config"],
    )
    try:
        # 统一复用连接管理器的跨库表枚举能力。
        tables = conn_mgr.get_tables(config)
        return {"tables": tables, "count": len(tables)}
    except Exception as e:
        return {"error": str(e), "tables": []}


@router.get("/{conn_id}/columns")
async def list_connection_table_columns(conn_id: str, table: str = ""):
    """按连接+表名读取字段列表，供前端字段映射候选下拉使用。"""
    data = sqlite_repo.get_connection(conn_id)
    if not data:
        return {"error": "Connection not found", "columns": []}

    normalized_table = str(table or "").strip()
    if not normalized_table:
        return {"columns": [], "count": 0}

    config = ConnectionConfig(
        id=data["id"],
        name=data["name"],
        type=data["type"],
        config=data["config"],
    )
    try:
        # 统一复用连接管理器的跨库字段枚举能力。
        columns = conn_mgr.get_table_columns(config, normalized_table)
        return {"columns": columns, "count": len(columns)}
    except Exception as e:
        return {"error": str(e), "columns": []}
