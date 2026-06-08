"""数据流编排 API - 统一的数据流管理（多数据源 → ETL工作流 → 目标存储）。"""
from fastapi import APIRouter, BackgroundTasks
from typing import List, Optional, Set
from pydantic import BaseModel
import uuid
import time
import math
from datetime import datetime
import pandas as pd

from app.persistence import sqlite_repo
from app.core.kline_sync_engine import KLineSyncEngine
from app.core.license_manager import check_feature_or_raise
from app.core.connection_manager import ConnectionManager
from app.adapters.source_adapters.kline_base import normalize_config

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


def _apply_pipeline_field_mappings(df: pd.DataFrame, field_mappings: List[dict]) -> pd.DataFrame:
    """应用数据流字段映射，并仅保留映射后的目标字段，避免未映射列误写入目标表。"""
    if not field_mappings or df.empty:
        return df
    from app.core.transform_engine import get_transform_engine
    transform_engine = get_transform_engine()
    mapped = transform_engine.apply_field_mappings(df, field_mappings)
    target_fields = []
    for mapping in field_mappings:
        tgt = mapping.get("target_field") or mapping.get("source_field")
        if tgt:
            target_fields.append(str(tgt))
    # 去重并保持顺序，只选择实际存在的字段。
    dedup_targets = [f for i, f in enumerate(target_fields) if f and f not in target_fields[:i]]
    existing_targets = [f for f in dedup_targets if f in mapped.columns]
    if existing_targets:
        return mapped[existing_targets].copy()
    return mapped


def _analyze_workflow_capabilities(workflow_json: dict) -> Set[str]:
    """分析工作流是否包含 source_fetch 和 target_write 节点，避免与 Pipeline 冲突。"""
    nodes = workflow_json.get("nodes", [])
    types = {n.get("type") for n in nodes}
    caps: Set[str] = set()
    if "source_fetch" in types:
        caps.add("source_fetch")
    if "target_write" in types:
        caps.add("target_write")
    return caps


def _get_pipeline_source_data(source_id: str):
    # 数据流来源优先读取 kline_sources；兼容历史配置中的 connections。
    return sqlite_repo.get_kline_source(source_id) or sqlite_repo.get_connection(source_id)


def _has_postgres_unique_constraint(conn_cfg: dict, table_name: str, columns: List[str]) -> bool:
    # 写入前检查 ON CONFLICT 依赖的唯一约束是否存在，避免执行时才报错。
    if not columns:
        return False
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=conn_cfg.get("host", "localhost"),
            port=int(conn_cfg.get("port", 5432)),
            user=conn_cfg.get("user"),
            password=conn_cfg.get("password"),
            database=conn_cfg.get("database"),
            connect_timeout=5,
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT array_agg(att.attname ORDER BY ord.ordinality) AS key_cols
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            JOIN unnest(con.conkey) WITH ORDINALITY AS ord(attnum, ordinality) ON TRUE
            JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ord.attnum
            WHERE con.contype IN ('u', 'p')
              AND rel.relname = %s
              AND nsp.nspname = 'public'
            GROUP BY con.oid
            """,
            (table_name,),
        )
        normalized = [str(c).strip().lower() for c in columns if str(c).strip()]
        for row in cur.fetchall():
            key_cols = [str(c).strip().lower() for c in (row[0] or [])]
            if key_cols == normalized:
                cur.close()
                conn.close()
                return True
        cur.close()
        conn.close()
        return False
    except Exception:
        return False


def _precheck_pipeline_config(pipeline: dict) -> dict:
    """统一预检查入口：运行前先做结构校验，避免执行成功但0写入或运行时才爆错。"""
    pjson = pipeline.get("pipeline_json", {}) or {}
    sources = pjson.get("sources", []) or []
    target = pjson.get("target", {}) or {}
    field_mappings = pjson.get("field_mappings", []) or []
    on_duplicate = str(pjson.get("on_duplicate", "ignore"))
    workflow_id = pjson.get("workflow_id")

    # 分析工作流能力，决定 Pipeline 是否需要 Source/Target
    wf_caps: Set[str] = set()
    if workflow_id:
        wf_data = sqlite_repo.get_workflow(workflow_id)
        if wf_data and wf_data.get("workflow_json"):
            wf_caps = _analyze_workflow_capabilities(wf_data["workflow_json"])

    errors: List[str] = []
    warnings: List[str] = []
    conn_mgr = ConnectionManager()

    if "source_fetch" not in wf_caps and not sources:
        errors.append("未配置数据源（工作流也未包含 source_fetch 节点）")
    if "target_write" not in wf_caps:
        if not target or not target.get("connection_id"):
            errors.append("未配置目标连接（工作流也未包含 target_write 节点）")
        if not target or not str(target.get("table", "")).strip():
            errors.append("未配置目标表名（工作流也未包含 target_write 节点）")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    if "source_fetch" in wf_caps:
        warnings.append("工作流包含 source_fetch 节点，Pipeline 数据源配置将被跳过")
    else:
        # 检查来源配置完整性
        for idx, source in enumerate(sources):
            source_id = source.get("connection_id")
            source_data = _get_pipeline_source_data(source_id)
            if not source_data:
                errors.append(f"数据源#{idx + 1} 不存在: {source_id}")
                continue
            preview_mode = str(source_data.get("config", {}).get("preview_mode", "kline")).lower()
            codes = source.get("params", {}).get("codes", []) or []
            if preview_mode != "codes" and not codes:
                errors.append(f"数据源#{idx + 1} 未配置股票代码（当前为K线模式）")

    if "target_write" in wf_caps:
        warnings.append("工作流包含 target_write 节点，Pipeline 目标库配置将被跳过")
    else:
        target_conn = sqlite_repo.get_connection(target.get("connection_id"))
        if not target_conn:
            errors.append("目标连接不存在")
            return {"ok": False, "errors": errors, "warnings": warnings}

        # 检查目标表是否存在，避免执行时才报"表不存在"。
        target_table = str(target.get("table", "")).strip()
        try:
            tables = conn_mgr.get_tables(type("Obj", (), {
                "type": target_conn["type"],
                "config": target_conn.get("config", {}),
            })())
            if target_table and target_table not in tables:
                errors.append(f"目标表不存在: {target_table}")
        except Exception as e:
            warnings.append(f"无法预读取目标表列表: {e}")

        # 若已配置字段映射，检查目标字段是否在目标表中。
        if target_table and field_mappings:
            expected_fields = []
            for mapping in field_mappings:
                tgt = mapping.get("target_field") or mapping.get("source_field")
                if tgt:
                    expected_fields.append(str(tgt))
            expected_fields = [f for i, f in enumerate(expected_fields) if f not in expected_fields[:i]]
            if expected_fields:
                try:
                    table_cols = conn_mgr.get_table_columns(type("Obj", (), {
                        "type": target_conn["type"],
                        "config": target_conn.get("config", {}),
                    })(), target_table)
                    miss = [f for f in expected_fields if f not in table_cols]
                    if miss:
                        errors.append(f"目标表缺少映射字段: {', '.join(miss)}")
                except Exception as e:
                    warnings.append(f"无法预读取目标字段列表: {e}")

        # PostgreSQL 下 ON CONFLICT 必须匹配唯一/主键约束，缺失时执行必失败。
        if target_conn.get("type") == "postgresql" and on_duplicate in ("ignore", "update") and field_mappings:
            conflict_cols = []
            for mapping in field_mappings:
                tgt = mapping.get("target_field") or mapping.get("source_field")
                if tgt:
                    conflict_cols.append(str(tgt))
                if len(conflict_cols) >= 2:
                    break
            if len(conflict_cols) >= 2:
                if not _has_postgres_unique_constraint(target_conn.get("config", {}), target_table, conflict_cols):
                    errors.append(
                        f"PostgreSQL 缺少唯一约束: ({', '.join(conflict_cols)})，无法使用 ON CONFLICT"
                    )
            else:
                warnings.append("字段映射不足2列，ON CONFLICT 键推断可能不稳定")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def _json_safe(value):
    """将响应中的 NaN/Inf 转换为 JSON 可序列化值。"""
    # 预览数据经过指标计算后可能出现 NaN/Inf，这里统一转换成 None。
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    # 递归处理字典结构，避免嵌套字段序列化失败。
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    # 递归处理列表结构，确保数组成员也被清洗。
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _build_codes_df(source_data: dict) -> pd.DataFrame:
    """代码列表模式：直接读取 list_codes 结果并转成 DataFrame。"""
    source_type = source_data.get("type", "")
    cfg = normalize_config(source_data.get("config", {}) or {})
    if source_type == "tdx":
        from app.adapters.source_adapters.tdx_adapter import TdxAdapter
        adapter = TdxAdapter()
    elif source_type == "mootdx":
        from app.adapters.source_adapters.mootdx_adapter import MootdxAdapter
        adapter = MootdxAdapter()
    elif source_type == "akshare":
        from app.adapters.source_adapters.akshare_adapter import HttpAdapter
        adapter = HttpAdapter()
    elif source_type == "tushare":
        from app.adapters.source_adapters.tushare_adapter import HttpAdapter
        adapter = HttpAdapter()
    else:
        return pd.DataFrame()
    codes = adapter.list_codes(cfg) or []
    if not codes:
        return pd.DataFrame()
    if isinstance(codes[0], dict):
        return pd.DataFrame(codes)
    return pd.DataFrame([{"code": str(v)} for v in codes])


def _build_pipeline_preview(pipeline: dict) -> dict:
    """执行数据流预览：拉源 + 工作流 + 字段映射，不写入目标库。"""
    pjson = pipeline.get("pipeline_json", {})
    sources = pjson.get("sources", [])
    workflow_id = pjson.get("workflow_id")
    field_mappings = pjson.get("field_mappings", [])

    # 分析工作流是否自带 Source，有则由工作流完成拉取
    wf_caps: Set[str] = set()
    wf_data = None
    if workflow_id:
        wf_data = sqlite_repo.get_workflow(workflow_id)
        if wf_data and wf_data.get("workflow_json"):
            wf_caps = _analyze_workflow_capabilities(wf_data["workflow_json"])

    if "source_fetch" in wf_caps:
        # 工作流自带 source_fetch：直接执行工作流预览
        from app.core.workflow_engine import get_workflow_engine
        engine_w = get_workflow_engine()
        engine_w.register_all()
        df, workflow_timings = engine_w.execute(wf_data["workflow_json"], pd.DataFrame())
        if field_mappings and not df.empty:
            df = _apply_pipeline_field_mappings(df, field_mappings)
        return {
            "pipeline_id": pipeline.get("id"),
            "pipeline_name": pipeline.get("name", ""),
            "rows": len(df),
            "columns": list(df.columns),
            "preview": _json_safe(df.head(50).to_dict("records")),
            "sources": [{"index": 1, "connection_id": "workflow:source_fetch", "status": "ok",
                         "rows_read": len(df), "rows_after_transform": len(df),
                         "interval": "n/a (workflow-managed)", "codes_count": 0}],
            "workflow_timings": _json_safe(workflow_timings),
        }

    if not sources:
        return {"error": "数据流未配置数据源"}

    engine = KLineSyncEngine()
    preview_frames: List[pd.DataFrame] = []
    source_reports = []
    total_rows_after_transform = 0
    workflow_timings = {}

    for idx, source in enumerate(sources):
        source_conn_id = source.get("connection_id")
        source_conn = _get_pipeline_source_data(source_conn_id)
        if not source_conn:
            source_reports.append({"index": idx + 1, "connection_id": source_conn_id, "status": "error", "message": "数据源不存在"})
            continue

        params = source.get("params", {})
        codes = params.get("codes", [])
        preview_mode = str(source_conn.get("config", {}).get("preview_mode", "kline")).lower()
        if (not codes) and preview_mode == "codes":
            df = _build_codes_df(source_conn)
            source_rows = len(df)
        else:
            if not codes:
                source_reports.append({"index": idx + 1, "connection_id": source_conn_id, "status": "skipped", "message": "未配置股票代码"})
                continue
            start_time, end_time = engine._resolve_time_range(params)
            interval = params.get("interval", "1min")
            session_only = params.get("session_only", True)
            # 按数据流配置拉取源数据，仅用于预览。
            df = engine._fetch_source(source_conn, codes, start_time, end_time, interval)
            source_rows = len(df)
            if session_only and interval == "1min":
                df = engine._filter_session_minutes(df)

        interval = params.get("interval", "1min")

        # 按数据流配置应用工作流，便于预览"加工后"的结果。
        if workflow_id and not df.empty:
            wf_data = sqlite_repo.get_workflow(workflow_id)
            if wf_data and wf_data.get("workflow_json"):
                from app.core.workflow_engine import get_workflow_engine
                engine_w = get_workflow_engine()
                engine_w.register_all()
                df, workflow_timings = engine_w.execute(wf_data["workflow_json"], df)

        # 按数据流配置应用字段映射，保证预览与执行结果一致。
        if field_mappings and not df.empty:
            df = _apply_pipeline_field_mappings(df, field_mappings)

        transformed_rows = len(df)
        total_rows_after_transform += transformed_rows
        source_reports.append({
            "index": idx + 1,
            "connection_id": source_conn_id,
            "status": "ok",
            "rows_read": source_rows,
            "rows_after_transform": transformed_rows,
            "interval": interval,
            "codes_count": len(codes),
        })

        if not df.empty:
            # 给每条预览记录打上来源标识，便于多数据源排查。
            sample_df = df.head(20).copy()
            sample_df["__source_conn_id"] = source_conn_id
            preview_frames.append(sample_df)

    if preview_frames:
        merged = pd.concat(preview_frames, ignore_index=True, sort=False).head(50)
        preview_records = _json_safe(merged.to_dict("records"))
        columns = list(merged.columns)
    else:
        preview_records = []
        columns = []

    return {
        "pipeline_id": pipeline.get("id"),
        "pipeline_name": pipeline.get("name", ""),
        "rows": total_rows_after_transform,
        "columns": columns,
        "preview": preview_records,
        "sources": source_reports,
        "workflow_timings": _json_safe(workflow_timings),
    }


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

        # 分析工作流是否自带 Source/Target，避免与 Pipeline 冲突
        wf_caps: Set[str] = set()
        wf_data = None
        if workflow_id:
            wf_data = sqlite_repo.get_workflow(workflow_id)
            if wf_data and wf_data.get("workflow_json"):
                wf_caps = _analyze_workflow_capabilities(wf_data["workflow_json"])

        engine = KLineSyncEngine()
        total_read = 0
        total_written = 0
        total_skipped = 0

        if "source_fetch" in wf_caps:
            # 工作流自带 source_fetch：由工作流独立完成拉取+写入，Pipeline 仅做调度
            from app.core.workflow_engine import get_workflow_engine
            engine_w = get_workflow_engine()
            engine_w.register_all()
            df, _ = engine_w.execute(wf_data["workflow_json"], pd.DataFrame())
            total_read = len(df)
            if df.empty:
                raise ValueError("工作流 source_fetch 未拉取到数据")
            if field_mappings:
                df = _apply_pipeline_field_mappings(df, field_mappings)
            if "target_write" not in wf_caps:
                # 工作流没有 target_write，Pipeline 负责写入
                target_conn = sqlite_repo.get_connection(target.get("connection_id"))
                if target_conn:
                    total_written = engine._insert_to_target(
                        df, target_conn, target.get("table", "dat_kline"),
                        batch_size, on_duplicate
                    )
            else:
                total_written = total_read
        else:
            # 常规流程：Pipeline 拉取 → 工作流 Transform → Pipeline 写入
            processed_sources = 0

            for source in sources:
                source_conn = _get_pipeline_source_data(source.get("connection_id"))
                if not source_conn:
                    total_skipped += 1
                    continue
                target_conn = sqlite_repo.get_connection(target.get("connection_id"))
                if not target_conn:
                    total_skipped += 1
                    continue

                params = source.get("params", {})
                codes = params.get("codes", [])
                preview_mode = str(source_conn.get("config", {}).get("preview_mode", "kline")).lower()
                interval = params.get("interval", "1min")
                session_only = params.get("session_only", True)
                if (not codes) and preview_mode == "codes":
                    df = _build_codes_df(source_conn)
                else:
                    if not codes:
                        total_skipped += 1
                        continue
                    start_time, end_time = engine._resolve_time_range(params)
                    df = engine._fetch_source(source_conn, codes, start_time, end_time, interval)
                total_read += len(df)
                processed_sources += 1

                if df.empty:
                    continue

                if session_only and interval == "1min":
                    df = engine._filter_session_minutes(df)

                # 工作流处理
                if workflow_id and wf_data and wf_data.get("workflow_json"):
                    from app.core.workflow_engine import get_workflow_engine
                    engine_w = get_workflow_engine()
                    engine_w.register_all()
                    df, _ = engine_w.execute(wf_data["workflow_json"], df)

                if df.empty:
                    continue

                # 字段映射
                if field_mappings:
                    df = _apply_pipeline_field_mappings(df, field_mappings)

                # 写入目标（工作流已有 target_write 时跳过）
                if "target_write" not in wf_caps:
                    written = engine._insert_to_target(
                        df, target_conn, target.get("table", "dat_kline"),
                        batch_size, on_duplicate
                    )
                    total_written += written

            if processed_sources == 0:
                raise ValueError("未读取到可执行的数据源，请检查数据流来源是否有效或是否配置了股票代码")

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


@router.get("/runs/all")
async def get_all_pipeline_runs(limit: int = 50):
    """返回所有数据流运行记录（避免与 /{pipeline_id} 路由冲突）。"""
    return sqlite_repo.list_pipeline_runs(limit=limit)


@router.get("/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    data = sqlite_repo.get_pipeline(pipeline_id)
    if not data:
        return {"error": "数据流不存在"}
    return data


@router.post("/")
async def create_pipeline(body: PipelineCreate):
    check_feature_or_raise("max_workflows")
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
async def run_pipeline(pipeline_id: str, background_tasks: BackgroundTasks, force: bool = False):
    check_feature_or_raise("concurrent_tasks")
    pipeline = sqlite_repo.get_pipeline(pipeline_id)
    if not pipeline:
        return {"error": "Pipeline not found"}
    # 运行前统一做预检查：有错误直接拦截；仅告警时允许用户二次确认后强制执行。
    precheck = _precheck_pipeline_config(pipeline)
    if precheck.get("errors"):
        return {"error": "运行前检查未通过", "precheck": precheck}
    if precheck.get("warnings") and not force:
        return {
            "error": "运行前检查存在风险提示，需二次确认",
            "need_confirm": True,
            "precheck": precheck,
        }
    background_tasks.add_task(_run_pipeline, pipeline_id)
    return {"id": pipeline_id, "message": "数据流已加入后台执行队列"}


@router.post("/{pipeline_id}/precheck")
async def precheck_pipeline(pipeline_id: str):
    # 提供显式预检查接口，前端可在"执行"前先展示问题并做二次确认。
    pipeline = sqlite_repo.get_pipeline(pipeline_id)
    if not pipeline:
        return {"error": "Pipeline not found", "ok": False, "errors": ["数据流不存在"], "warnings": []}
    return _precheck_pipeline_config(pipeline)


@router.post("/{pipeline_id}/preview")
async def preview_pipeline(pipeline_id: str):
    """预览数据流：不写入目标库，仅返回加工后样例数据。"""
    pipeline = sqlite_repo.get_pipeline(pipeline_id)
    if not pipeline:
        return {"error": "Pipeline not found"}
    try:
        return _build_pipeline_preview(pipeline)
    except Exception as e:
        return {"error": str(e)}


@router.get("/{pipeline_id}/runs")
async def get_pipeline_runs(pipeline_id: str, limit: int = 20):
    return sqlite_repo.list_pipeline_runs(pipeline_id, limit)
