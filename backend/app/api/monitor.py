from fastapi import APIRouter
from typing import List
from datetime import datetime

from app.persistence import sqlite_repo

router = APIRouter()


@router.get("/tasks")
async def get_task_status():
    tasks = sqlite_repo.list_tasks()
    summary = {
        "total": len(tasks),
        "running": sum(1 for t in tasks if t.get("status") == "running"),
        "completed": sum(1 for t in tasks if t.get("status") == "completed"),
        "failed": sum(1 for t in tasks if t.get("status") == "failed"),
        "pending": sum(1 for t in tasks if t.get("status") == "pending"),
    }
    return {**summary, "tasks": tasks}


@router.get("/bulk-imports")
async def get_bulk_import_status():
    imports = sqlite_repo.list_bulk_imports()
    summary = {
        "total": len(imports),
        "running": sum(1 for i in imports if i.get("status") == "running"),
        "completed": sum(1 for i in imports if i.get("status") == "completed"),
        "failed": sum(1 for i in imports if i.get("status") == "failed"),
        "paused": sum(1 for i in imports if i.get("status") == "paused"),
    }
    for imp in imports:
        total = imp.get("total_rows", 0) or 1
        imported = imp.get("imported_rows", 0) or 0
        imp["progress_pct"] = round(imported / total * 100, 1)
    return {**summary, "imports": imports}


@router.get("/summary")
async def get_summary():
    tasks = sqlite_repo.list_tasks()
    imports = sqlite_repo.list_bulk_imports()
    connections = sqlite_repo.list_connections()
    schemas = sqlite_repo.list_schemas()

    return {
        "connections": len(connections),
        "schemas": len(schemas),
        "tasks": {
            "total": len(tasks),
            "running": sum(1 for t in tasks if t.get("status") == "running"),
            "completed": sum(1 for t in tasks if t.get("status") == "completed"),
            "failed": sum(1 for t in tasks if t.get("status") == "failed"),
        },
        "bulk_imports": {
            "total": len(imports),
            "running": sum(1 for i in imports if i.get("status") == "running"),
            "total_rows_imported": sum(i.get("imported_rows", 0) for i in imports),
        },
    }
