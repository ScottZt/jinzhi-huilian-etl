from fastapi import APIRouter
from typing import List, Optional
from pydantic import BaseModel
import uuid
from datetime import datetime

from app.persistence import sqlite_repo
from app.core.task_scheduler import (
    schedule_task, remove_task, run_task_now,
    get_scheduler, init_scheduler, get_next_run_times,
)
from app.core.execution_engine import get_execution_engine

router = APIRouter()


class TaskCreate(BaseModel):
    name: str
    task_type: str
    source_connection_id: str
    target_connection_id: str
    target_table: str
    config_json: dict
    cron_expression: Optional[str] = None


@router.get("/", response_model=list)
async def get_all_tasks():
    return sqlite_repo.list_tasks()


@router.get("/next-runs")
async def get_next_runs():
    init_scheduler()
    return get_next_run_times()


@router.get("/{task_id}")
async def get_task(task_id: str):
    data = sqlite_repo.get_task(task_id)
    if not data:
        return {"error": "Task not found"}
    return data


@router.post("/")
async def create_task(body: TaskCreate):
    init_scheduler()
    task_id = str(uuid.uuid4())
    record = {
        "id": task_id,
        "name": body.name,
        "task_type": body.task_type,
        "source_connection_id": body.source_connection_id,
        "target_connection_id": body.target_connection_id,
        "target_table": body.target_table,
        "config_json": body.config_json,
        "status": "pending",
        "cron_expression": body.cron_expression,
        "last_run_at": None,
        "next_run_at": None,
    }
    result = sqlite_repo.save_task(record)

    if body.cron_expression:
        engine = get_execution_engine()
        schedule_task(task_id, body.cron_expression, lambda tid: engine.execute_sync(tid))

    return result


@router.put("/{task_id}")
async def update_task(task_id: str, body: TaskCreate):
    init_scheduler()
    remove_task(task_id)
    record = {
        "id": task_id,
        "name": body.name,
        "task_type": body.task_type,
        "source_connection_id": body.source_connection_id,
        "target_connection_id": body.target_connection_id,
        "target_table": body.target_table,
        "config_json": body.config_json,
        "status": "pending",
        "cron_expression": body.cron_expression,
        "last_run_at": None,
        "next_run_at": None,
    }
    result = sqlite_repo.save_task(record)

    if body.cron_expression:
        engine = get_execution_engine()
        schedule_task(task_id, body.cron_expression, lambda tid: engine.execute_sync(tid))

    return result


@router.patch("/{task_id}/status")
async def update_task_status(task_id: str, status: str):
    existing = sqlite_repo.get_task(task_id)
    if not existing:
        return {"error": "Task not found"}
    existing["status"] = status
    existing["updated_at"] = datetime.utcnow().isoformat()
    return sqlite_repo.save_task(existing)


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    remove_task(task_id)
    deleted = sqlite_repo.delete_task(task_id)
    return {"deleted": deleted}


@router.post("/{task_id}/run")
async def run_task(task_id: str):
    msg = run_task_now(task_id)
    return {"id": task_id, "message": msg}
