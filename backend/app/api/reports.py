from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from typing import Optional
import io

from app.core.report_generator import (
    generate_bulk_import_report, generate_task_report,
    generate_summary_report, export_report,
)

router = APIRouter()


@router.get("/summary")
async def get_summary_report():
    data = generate_summary_report()
    return data


@router.get("/bulk-import/{import_id}")
async def get_bulk_import_report(
    import_id: str,
    format: str = "json",
):
    data = generate_bulk_import_report(import_id)
    if "error" in data:
        return data

    content = export_report(data, format)

    if format == "json":
        return Response(content=content, media_type="application/json")
    elif format == "csv":
        return Response(content=content, media_type="text/csv")
    elif format == "html":
        return Response(content=content, media_type="text/html")
    else:
        return Response(content=content, media_type="application/json")


@router.get("/task/{task_id}")
async def get_task_report(
    task_id: str,
    format: str = "json",
):
    data = generate_task_report(task_id)
    if "error" in data:
        return data

    content = export_report(data, format)

    if format == "json":
        return Response(content=content, media_type="application/json")
    elif format == "csv":
        return Response(content=content, media_type="text/csv")
    elif format == "html":
        return Response(content=content, media_type="text/html")
    else:
        return Response(content=content, media_type="application/json")


@router.get("/all")
async def get_all_reports():
    """Get a combined report of all recent tasks and imports."""
    from app.persistence import sqlite_repo

    tasks = sqlite_repo.list_tasks()
    imports = sqlite_repo.list_bulk_imports()

    task_reports = []
    for t in tasks[:20]:
        r = generate_task_report(t["id"])
        if "error" not in r:
            task_reports.append(r)

    import_reports = []
    for i in imports[:20]:
        r = generate_bulk_import_report(i["id"])
        if "error" not in r:
            import_reports.append(r)

    summary = generate_summary_report()

    return {
        "summary": summary,
        "task_reports": task_reports,
        "import_reports": import_reports,
    }
