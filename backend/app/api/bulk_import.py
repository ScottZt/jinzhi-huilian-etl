from fastapi import APIRouter
from typing import List, Optional
from pydantic import BaseModel
import uuid
import hashlib
from datetime import datetime
from pathlib import Path

from app.persistence import sqlite_repo
from app.adapters.source_adapters.csv_adapter import CSVAdapter
from app.adapters.source_adapters.excel_adapter import ExcelAdapter
from app.adapters.source_adapters.json_adapter import JSONAdapter
from app.adapters.source_adapters.parquet_adapter import ParquetAdapter
from app.core.bulk_import_engine import get_engine

router = APIRouter()
bulk_engine = get_engine()


def _get_adapter(file_path: str):
    ext = Path(file_path).suffix.lower()
    if ext in (".xlsx", ".xls"):
        return ExcelAdapter({"file_path": file_path})
    elif ext == ".json":
        return JSONAdapter({"file_path": file_path})
    elif ext == ".parquet":
        return ParquetAdapter({"file_path": file_path})
    else:
        return CSVAdapter({"file_path": file_path, "encoding": "auto", "delimiter": "auto", "has_header": True})


class BulkImportStart(BaseModel):
    source_connection_id: str
    target_connection_id: str
    target_table: str
    file_path: str
    field_mappings: List[dict] = []
    import_mode: str = "incremental"
    batch_size: int = 5000
    parallel_threads: int = 1
    enable_checkpoint: bool = True


@router.get("/", response_model=list)
async def list_bulk_imports():
    return sqlite_repo.list_bulk_imports()


@router.get("/{import_id}")
async def get_bulk_import(import_id: str):
    data = sqlite_repo.get_bulk_import(import_id)
    if not data:
        return {"error": "Bulk import not found"}
    return data


@router.post("/preview")
async def preview_file(file_path: str, encoding: str = "auto", delimiter: str = "auto", nrows: int = 100):
    adapter = _get_adapter(file_path)
    info = adapter.get_file_info()
    df = adapter.read_csv(nrows=nrows) if hasattr(adapter, 'read_csv') else adapter.read_excel(nrows=nrows) if hasattr(adapter, 'read_excel') else adapter.read_json(nrows=nrows) if hasattr(adapter, 'read_json') else adapter.read_parquet(nrows=nrows)
    return {
        "file_info": info,
        "preview": df.head(nrows).to_dict(orient="records"),
        "columns": df.columns.tolist(),
        "file_type": Path(file_path).suffix.lower(),
    }


@router.post("/")
async def start_bulk_import(body: BulkImportStart):
    import_id = str(uuid.uuid4())
    file_md5 = _compute_md5(body.file_path)

    adapter = _get_adapter(body.file_path)
    try:
        info = adapter.get_file_info()
        total_rows = info.get("total_rows", 0)
    except Exception:
        total_rows = 0

    record = {
        "id": import_id,
        "source_connection_id": body.source_connection_id,
        "target_connection_id": body.target_connection_id,
        "target_table": body.target_table,
        "file_path": body.file_path,
        "file_md5": file_md5,
        "config_json": {
            "field_mappings": body.field_mappings,
            "import_mode": body.import_mode,
            "batch_size": body.batch_size,
            "parallel_threads": body.parallel_threads,
            "enable_checkpoint": body.enable_checkpoint,
        },
        "total_rows": total_rows,
        "imported_rows": 0,
        "last_imported_index": 0,
        "status": "pending",
        "error_at_row": None,
        "error_message": None,
        "started_at": None,
        "completed_at": None,
    }
    result = sqlite_repo.save_bulk_import(record)
    return result


@router.post("/{import_id}/execute")
async def execute_bulk_import(import_id: str):
    existing = sqlite_repo.get_bulk_import(import_id)
    if not existing:
        return {"error": "Bulk import not found"}

    existing["status"] = "running"
    existing["started_at"] = datetime.utcnow().isoformat()
    existing["updated_at"] = datetime.utcnow().isoformat()
    sqlite_repo.save_bulk_import(existing)

    msg = bulk_engine.start_import(import_id)

    return {
        "id": import_id,
        "status": "running",
        "started_at": existing["started_at"],
        "message": msg,
    }


@router.post("/{import_id}/pause")
async def pause_bulk_import(import_id: str):
    existing = sqlite_repo.get_bulk_import(import_id)
    if not existing:
        return {"error": "Bulk import not found"}
    bulk_engine.pause_import(import_id)
    existing["status"] = "paused"
    existing["updated_at"] = datetime.utcnow().isoformat()
    return sqlite_repo.save_bulk_import(existing)


@router.post("/{import_id}/resume")
async def resume_bulk_import(import_id: str):
    existing = sqlite_repo.get_bulk_import(import_id)
    if not existing:
        return {"error": "Bulk import not found"}
    bulk_engine.resume_import(import_id)
    existing["status"] = "running"
    existing["updated_at"] = datetime.utcnow().isoformat()
    return sqlite_repo.save_bulk_import(existing)


@router.delete("/{import_id}")
async def delete_bulk_import(import_id: str):
    deleted = sqlite_repo.delete_bulk_import(import_id)
    return {"deleted": deleted}


def _compute_md5(file_path: str) -> str:
    md5 = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception:
        return ""
