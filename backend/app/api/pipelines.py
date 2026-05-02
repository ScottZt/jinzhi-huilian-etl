"""数据流编排 API — 统一的数据流管理（多数据源 → ETL工作流 → 目标存储）。"""
from fastapi import APIRouter, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel
import uuid
import time
from datetime import datetime

from app.persistence import sqlite_repo
from app.core.kline_sync_engine import KLineSyncEngine

router = APIRouter()


class PipelineCreate(BaseModel):
    name: str
    description: str = ""
    pipeline_json: dict
    cron_expression: Optional[str] = None


class PipelineExecuteResponse(BaseModel):
    id: str
    status: str
    message: str


def _run_pipeline(pipeline_id: str):
    """后台执行数据流编排。"""
    pipeline = sqlite_repo.get_pipeline(pipeline_id)
    if not pipeline:
        return {"error": "Pipeline not found"}

    t0 = time.time()
    run_id = str(uuid.uuid4())
    run_data = {
        "id": run_id,
        "pipeline_id": pipeline_id,
        "started_at": datetime.now().isoformat(),
        "status": "running",
    }
    sqlite_repo.save_pipeline_run(run_data)

    try:
        pjson = pipeline.get("pipeline_json", {})
        sources = pjson.get("sources", [])
        target = pjson.get("target", {})
        workflow_id = pjson.get("workflow_id")
        field_mappings = pjson.get("field_mappings", [])
        batch_size = pjson.get("batch_size", 5000)
        on_duplicate = pjson.get("on_duplicate", "ignore")

        if not sources or not target:
            raise ValueError("数据流需要至少一个数据源和一个目标")

        engine = KLineSyncEngine()
        total_read = 0
        total_written = 0
        total_skipped = 0

        for source in sources:
            source_conn = sqlite_repo.get_connection(source.get("connection_id"))
            if not source_conn:
                continue
            target_conn = sqlite_repo.get_connection(target.get("connection_id"))
            if not target_conn:
                continue

            params = source.get("params", {})
            codes = params.get("codes", [])
            if not codes:
                continue
            start_time, end_time = engine._resolve_time_range(params)
            interval = params.get("interval", "1min")
            session_only = params.get("session_only", True)

            df = engine._fetch_source(source_conn, codes, start_time, end_time, interval)
            total_read += len(df)

            if df.empty:
                continue

            if session_only and interval == "1min":
                df = engine._filter_session_minutes(df)

            # 工作流处理
            if workflow_id:
                wf_data = sqlite_repo.get_workflow(workflow_id)
                if wf_data and wf_data.get("workflow_json"):
                    from app.core.workflow_engine import get_workflow_engine
                    engine_w = get_workflow_engine()
                    engine_w.register_all()
                    df, _ = engine_w.execute(wf_data["workflow_json"], df)

            if df.empty:
                continue

            # 字段映射
            if field_mappings:
                from app.core.transform_engine import get_transform_engine
                transform_engine = get_transform_engine()
                df = transform_engine.apply_field_mappings(df, field_mappings)

            # 写入目标
            written = engine._insert_to_target(
                df, target_conn, target.get("table", "dat_kline"),
                batch_size, on_duplicate
            )
            total_written += written

        elapsed = time.time() - t0
        sqlite_repo.save_pipeline_run({
            "id": run_id,
            "status": "success",
            "rows_read": total_read,
            "rows_written": total_written,
            "rows_skipped": total_skipped,
            "duration": round(elapsed, 2),
            "finished_at": datetime.now().isoformat(),
        })

        # 更新 pipeline 状态
        pipeline["last_run_at"] = datetime.now().isoformat()
        pipeline["status"] = "completed"
        sqlite_repo.save_pipeline(pipeline)

    except Exception as e:
        sqlite_repo.save_pipeline_run({
            "id": run_id,
            "status": "failed",
            "error_message": str(e),
            "finished_at": datetime.now().isoformat(),
        })
        pipeline["status"] = "failed"
        sqlite_repo.save_pipeline(pipeline)


@router.get("/", response_model=List[dict])
async def get_all_pipelines():
    return sqlite_repo.list_pipelines()


@router.get("/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    data = sqlite_repo.get_pipeline(pipeline_id)
    if not data:
        return {"error": "数据流不存在"}
    return data


@router.post("/")
async def create_pipeline(body: PipelineCreate):
    pipeline_id = str(uuid.uuid4())
    record = {
        "id": pipeline_id,
        "name": body.name,
        "description": body.description,
        "pipeline_json": body.pipeline_json,
        "enabled": True,
        "status": "pending",
        "cron_expression": body.cron_expression,
    }
    result = sqlite_repo.save_pipeline(record)

    if body.cron_expression:
        from app.core.task_scheduler import schedule_task
        schedule_task(pipeline_id, body.cron_expression, lambda tid: _run_pipeline(tid))

    return result


@router.put("/{pipeline_id}")
async def update_pipeline(pipeline_id: str, body: PipelineCreate):
    from app.core.task_scheduler import remove_task, schedule_task
    remove_task(pipeline_id)
    record = {
        "id": pipeline_id,
        "name": body.name,
        "description": body.description,
        "pipeline_json": body.pipeline_json,
        "enabled": True,
        "cron_expression": body.cron_expression,
    }
    result = sqlite_repo.save_pipeline(record)

    if body.cron_expression:
        schedule_task(pipeline_id, body.cron_expression, lambda tid: _run_pipeline(tid))

    return result


@router.patch("/{pipeline_id}/status")
async def update_pipeline_status(pipeline_id: str, enabled: bool):
    existing = sqlite_repo.get_pipeline(pipeline_id)
    if not existing:
        return {"error": "Pipeline not found"}
    existing["enabled"] = enabled
    existing["updated_at"] = datetime.utcnow().isoformat()
    return sqlite_repo.save_pipeline(existing)


@router.delete("/{pipeline_id}")
async def delete_pipeline(pipeline_id: str):
    from app.core.task_scheduler import remove_task
    remove_task(pipeline_id)
    deleted = sqlite_repo.delete_pipeline(pipeline_id)
    return {"deleted": deleted}


@router.post("/{pipeline_id}/run")
async def run_pipeline(pipeline_id: str, background_tasks: BackgroundTasks):
    pipeline = sqlite_repo.get_pipeline(pipeline_id)
    if not pipeline:
        return {"error": "Pipeline not found"}
    background_tasks.add_task(_run_pipeline, pipeline_id)
    return {"id": pipeline_id, "message": "数据流已加入后台执行队列"}


@router.get("/{pipeline_id}/runs")
async def get_pipeline_runs(pipeline_id: str, limit: int = 20):
    return sqlite_repo.list_pipeline_runs(pipeline_id, limit)


@router.get("/runs")
async def get_all_pipeline_runs(limit: int = 50):
    return sqlite_repo.list_pipeline_runs(limit=limit)
