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
