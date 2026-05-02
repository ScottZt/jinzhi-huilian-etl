"""K线同步任务 API — 任务 CRUD + 手动执行 + 执行记录。"""
from fastapi import APIRouter, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel
import json
import uuid
from datetime import datetime

from app.persistence import sqlite_repo
from app.core.kline_sync_engine import KLineSyncEngine

router = APIRouter()


class KLineTaskCreate(BaseModel):
    name: str
    source_connection_id: str
    target_connection_id: str
    target_table: str
    config_json: dict
    cron_expression: Optional[str] = None


class KLineTaskResponse(BaseModel):
    id: str
    name: str
    source_connection_id: str
    target_connection_id: str
    target_table: str
    config_json: dict
    status: str
    cron_expression: Optional[str]
    last_run_at: Optional[str]
    next_run_at: Optional[str]


def _run_sync_task(task_id: str):
    """后台执行同步任务。"""
    engine = KLineSyncEngine()
    result = engine.sync(task_id)
    sqlite_repo.save_sync_record({
        "id": str(uuid.uuid4()),
        "task_id": task_id,
        "started_at": datetime.now().isoformat(),
        "rows_read": result.get("rows_read", 0),
        "rows_written": result.get("rows_written", 0),
        "rows_skipped": result.get("rows_skipped", 0),
        "error_message": ", ".join(result.get("errors", [])) if result.get("errors") else None,
        "status": "failed" if result.get("error") else "success",
    })
    task = sqlite_repo.get_task(task_id)
    if task:
        task["last_run_at"] = datetime.now().isoformat()
        sqlite_repo.save_task(task)


@router.get("/", response_model=List[dict])
async def get_all_tasks():
    return sqlite_repo.list_tasks()


@router.get("/next-runs")
async def get_next_runs():
    from app.core.task_scheduler import init_scheduler, get_next_run_times
    init_scheduler()
    return get_next_run_times()


@router.get("/{task_id}")
async def get_task(task_id: str):
    data = sqlite_repo.get_task(task_id)
    if not data:
        return {"error": "Task not found"}
    return data


@router.post("/")
async def create_task(body: KLineTaskCreate):
    task_id = str(uuid.uuid4())
    record = {
        "id": task_id,
        "name": body.name,
        "task_type": "kline_sync",
        "source_connection_id": body.source_connection_id,
        "target_connection_id": body.target_connection_id,
        "target_table": body.target_table,
        "config_json": body.config_json,
        "status": "pending",
        "cron_expression": body.cron_expression,
        "last_run_at": None,
        "next_run_at": None,
    }
    sqlite_repo.save_task(record)

    if body.cron_expression:
        from app.core.task_scheduler import schedule_task
        schedule_task(task_id, body.cron_expression, lambda tid: _run_sync_task(tid))

    return {"id": task_id, **record}


@router.put("/{task_id}")
async def update_task(task_id: str, body: KLineTaskCreate):
    from app.core.task_scheduler import remove_task, schedule_task
    remove_task(task_id)
    record = {
        "id": task_id,
        "name": body.name,
        "task_type": "kline_sync",
        "source_connection_id": body.source_connection_id,
        "target_connection_id": body.target_connection_id,
        "target_table": body.target_table,
        "config_json": body.config_json,
        "status": "pending",
        "cron_expression": body.cron_expression,
        "last_run_at": None,
        "next_run_at": None,
    }
    sqlite_repo.save_task(record)

    if body.cron_expression:
        schedule_task(task_id, body.cron_expression, lambda tid: _run_sync_task(tid))

    return record


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
    from app.core.task_scheduler import remove_task
    remove_task(task_id)
    deleted = sqlite_repo.delete_task(task_id)
    return {"deleted": deleted}


@router.post("/{task_id}/run")
async def run_task(task_id: str, background_tasks: BackgroundTasks):
    task = sqlite_repo.get_task(task_id)
    if not task:
        return {"error": "Task not found"}

    background_tasks.add_task(_run_sync_task, task_id)
    return {"id": task_id, "message": "任务已加入后台执行队列"}


@router.post("/{task_id}/dry-run")
async def dry_run_task(task_id: str):
    """预览同步结果（不写入目标库）。"""
    task = sqlite_repo.get_task(task_id)
    if not task:
        return {"error": "Task not found"}

    source_conn = sqlite_repo.get_connection(task["source_connection_id"])
    if not source_conn:
        return {"error": "数据源连接不存在"}

    config = task["config_json"]
    codes = config.get("codes", [])
    if not codes:
        return {"error": "No stock codes configured"}

    from app.core.kline_sync_engine import KLineSyncEngine
    engine = KLineSyncEngine()
    start_time, end_time = engine._resolve_time_range(config)
    interval = config.get("interval", "1min")

    try:
        df = engine._fetch_source(source_conn, codes, start_time, end_time, interval)
        return {
            "rows_fetched": len(df),
            "columns": list(df.columns),
            "preview": df.head(20).to_dict("records"),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/{task_id}/records")
async def get_task_records(task_id: str, limit: int = 20):
    return sqlite_repo.list_sync_records(task_id, limit)


@router.get("/records")
async def get_all_records(limit: int = 50):
    from app.persistence import sqlite_repo as _sr
    with _sr._get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sync_run_records ORDER BY started_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        result = []
        for row in rows:
            d = _sr._row_to_dict(row)
            d["config_json"] = json.loads(d["config_json"]) if d["config_json"] else {}
            result.append(d)
        return result
