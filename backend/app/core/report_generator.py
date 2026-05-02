"""
Report generator for task and bulk import executions.
Supports JSON, CSV, and HTML report formats.
"""
import json
import csv
import io
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from app.persistence import sqlite_repo


class ReportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    HTML = "html"


def generate_bulk_import_report(import_id: str) -> Dict[str, Any]:
    """Generate a comprehensive report for a bulk import execution."""
    record = sqlite_repo.get_bulk_import(import_id)
    if not record:
        return {"error": f"Import {import_id} not found"}

    total = record.get("total_rows", 0) or 1
    imported = record.get("imported_rows", 0) or 0
    progress = round(imported / total * 100, 1) if total > 0 else 0

    source_conn = sqlite_repo.get_connection(record["source_connection_id"])
    target_conn = sqlite_repo.get_connection(record["target_connection_id"])
    config = record.get("config_json", {})

    return {
        "report_type": "bulk_import",
        "import_id": import_id,
        "generated_at": datetime.utcnow().isoformat(),
        "status": record.get("status"),
        "file": {
            "path": record.get("file_path"),
            "md5": record.get("file_md5"),
            "total_rows": record.get("total_rows"),
        },
        "target": {
            "connection_id": record.get("target_connection_id"),
            "connection_type": target_conn.get("type") if target_conn else "N/A",
            "table": record.get("target_table"),
        },
        "progress": {
            "imported_rows": imported,
            "remaining_rows": total - imported,
            "progress_pct": progress,
        },
        "timing": {
            "created_at": record.get("created_at"),
            "started_at": record.get("started_at"),
            "completed_at": record.get("completed_at"),
        },
        "config": {
            "import_mode": config.get("import_mode"),
            "batch_size": config.get("batch_size"),
            "parallel_threads": config.get("parallel_threads"),
            "field_mappings_count": len(config.get("field_mappings", [])),
            "enable_checkpoint": config.get("enable_checkpoint"),
        },
        "errors": {
            "error_at_row": record.get("error_at_row"),
            "error_message": record.get("error_message"),
        },
        "summary": _build_import_summary(record),
    }


def generate_task_report(task_id: str) -> Dict[str, Any]:
    """Generate a comprehensive report for a sync task execution."""
    task = sqlite_repo.get_task(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}

    source_conn = sqlite_repo.get_connection(task["source_connection_id"])
    target_conn = sqlite_repo.get_connection(task["target_connection_id"])
    config = task.get("config_json", {})
    last_result = config.get("last_result", {})
    last_error = config.get("last_error")

    return {
        "report_type": "task",
        "task_id": task_id,
        "generated_at": datetime.utcnow().isoformat(),
        "task": {
            "name": task.get("name"),
            "type": task.get("task_type"),
            "status": task.get("status"),
        },
        "source": {
            "connection_id": task.get("source_connection_id"),
            "connection_type": source_conn.get("type") if source_conn else "N/A",
        },
        "target": {
            "connection_id": task.get("target_connection_id"),
            "connection_type": target_conn.get("type") if target_conn else "N/A",
            "table": task.get("target_table"),
        },
        "execution": {
            "last_run_at": task.get("last_run_at"),
            "next_run_at": task.get("next_run_at"),
            "cron_expression": task.get("cron_expression"),
            "last_result": last_result,
            "last_error": last_error,
        },
        "config": {
            "batch_size": config.get("batch_size"),
            "start_date": config.get("start_date"),
            "end_date": config.get("end_date"),
        },
        "summary": _build_task_summary(task),
    }


def generate_summary_report() -> Dict[str, Any]:
    """Generate a system-wide summary report."""
    tasks = sqlite_repo.list_tasks()
    imports = sqlite_repo.list_bulk_imports()
    connections = sqlite_repo.list_connections()
    schemas = sqlite_repo.list_schemas()

    task_by_status = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
    for t in tasks:
        s = t.get("status", "pending")
        task_by_status[s] = task_by_status.get(s, 0) + 1

    import_by_status = {"pending": 0, "running": 0, "paused": 0, "completed": 0, "failed": 0}
    for i in imports:
        s = i.get("status", "pending")
        import_by_status[s] = import_by_status.get(s, 0) + 1

    total_rows_imported = sum(i.get("imported_rows", 0) for i in imports)
    total_rows_target = sum(i.get("total_rows", 0) for i in imports)

    return {
        "report_type": "system_summary",
        "generated_at": datetime.utcnow().isoformat(),
        "connections": {
            "total": len(connections),
            "types": _count_by_type(connections),
        },
        "schemas": {
            "total": len(schemas),
        },
        "tasks": {
            **task_by_status,
            "total": len(tasks),
        },
        "bulk_imports": {
            **import_by_status,
            "total": len(imports),
            "total_rows_imported": total_rows_imported,
            "total_rows_target": total_rows_target,
            "overall_progress_pct": round(total_rows_imported / max(total_rows_target, 1) * 100, 1),
        },
    }


def _build_import_summary(record: Dict) -> str:
    imported = record.get("imported_rows", 0) or 0
    total = record.get("total_rows", 0) or 0
    status = record.get("status", "unknown")
    err = record.get("error_message")
    return f"Import {status}: {imported}/{total} rows"


def _build_task_summary(task: Dict) -> str:
    status = task.get("status", "unknown")
    name = task.get("name", "unnamed")
    result = task.get("config_json", {}).get("last_result", {})
    rows = result.get("rows_inserted", "N/A")
    return f"Task '{name}' {status}: {rows} rows inserted"


def _count_by_type(items: List[Dict]) -> Dict[str, int]:
    counts = {}
    for item in items:
        t = item.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


def export_report(report_data: Dict, format: str = "json") -> str:
    """Export a report in the specified format."""
    fmt = format.lower()
    if fmt == "json":
        return json.dumps(report_data, indent=2, ensure_ascii=False, default=str)
    elif fmt == "csv":
        return _export_csv(report_data)
    elif fmt == "html":
        return _export_html(report_data)
    else:
        return json.dumps(report_data, indent=2, ensure_ascii=False, default=str)


def _export_csv(report_data: Dict) -> str:
    """Flatten report data into CSV format."""
    output = io.StringIO()
    if report_data.get("report_type") == "bulk_import":
        flat = {
            "import_id": report_data.get("import_id"),
            "status": report_data.get("status"),
            "file_path": report_data.get("file", {}).get("path"),
            "total_rows": report_data.get("file", {}).get("total_rows"),
            "imported_rows": report_data.get("progress", {}).get("imported_rows"),
            "progress_pct": report_data.get("progress", {}).get("progress_pct"),
            "target_table": report_data.get("target", {}).get("table"),
            "target_type": report_data.get("target", {}).get("connection_type"),
            "started_at": report_data.get("timing", {}).get("started_at"),
            "completed_at": report_data.get("timing", {}).get("completed_at"),
            "error_message": report_data.get("errors", {}).get("error_message"),
            "generated_at": report_data.get("generated_at"),
        }
        writer = csv.DictWriter(output, fieldnames=list(flat.keys()))
        writer.writeheader()
        writer.writerow(flat)
    elif report_data.get("report_type") == "task":
        flat = {
            "task_id": report_data.get("task_id"),
            "task_name": report_data.get("task", {}).get("name"),
            "task_type": report_data.get("task", {}).get("type"),
            "status": report_data.get("status"),
            "target_table": report_data.get("target", {}).get("table"),
            "last_run_at": report_data.get("execution", {}).get("last_run_at"),
            "next_run_at": report_data.get("execution", {}).get("next_run_at"),
            "cron": report_data.get("execution", {}).get("cron_expression"),
            "error": report_data.get("execution", {}).get("last_error"),
            "generated_at": report_data.get("generated_at"),
        }
        writer = csv.DictWriter(output, fieldnames=list(flat.keys()))
        writer.writeheader()
        writer.writerow(flat)
    else:
        flat = {"key": "value"}
        writer = csv.DictWriter(output, fieldnames=["report_type", "generated_at"])
        writer.writeheader()
        writer.writerow({"report_type": report_data.get("report_type"), "generated_at": report_data.get("generated_at")})
    return output.getvalue()


def _export_html(report_data: Dict) -> str:
    """Generate an HTML report."""
    report_type = report_data.get("report_type", "unknown")
    generated = report_data.get("generated_at", "")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>金智汇联ETL Report</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; padding: 24px; }}
  h1 {{ color: #6366f1; }} h2 {{ color: #818cf8; border-bottom: 1px solid #2d3348; padding-bottom: 8px; }}
  .card {{ background: #22263a; border: 1px solid #2d3348; border-radius: 10px; padding: 16px; margin: 12px 0; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; padding: 8px 12px; color: #8892a4; border-bottom: 1px solid #2d3348; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #2d3348; }}
  .badge {{ padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
  .badge-completed {{ background: rgba(34,197,94,0.15); color: #22c55e; }}
  .badge-running {{ background: rgba(56,189,248,0.15); color: #38bdf8; }}
  .badge-failed {{ background: rgba(239,68,68,0.15); color: #ef4444; }}
  .badge-pending {{ background: rgba(99,102,241,0.15); color: #6366f1; }}
  .progress {{ height: 8px; background: #2d3348; border-radius: 4px; overflow: hidden; margin: 8px 0; }}
  .progress-fill {{ height: 100%; background: #6366f1; border-radius: 4px; }}
  .meta {{ color: #8892a4; font-size: 12px; }}
  .kv {{ display: flex; gap: 16px; }} .kv-item {{ flex: 1; }}
  .kv-label {{ color: #8892a4; font-size: 11px; text-transform: uppercase; }}
  .kv-value {{ font-size: 24px; font-weight: 700; color: #e2e8f0; }}
</style></head><body>
<h1>金智汇联ETL Report</h1>
<p class="meta">生成时间: {generated} | 类型: {report_type}</p>
"""

    if report_type == "bulk_import":
        status = report_data.get("status", "pending")
        progress = report_data.get("progress", {})
        imported = progress.get("imported_rows", 0)
        total = progress.get("total_rows", 1)
        pct = progress.get("progress_pct", 0)

        html += f"""
<h2>批量导入报告</h2>
<div class="card">
  <div class="kv">
    <div class="kv-item"><div class="kv-label">状态</div><div class="kv-value"><span class="badge badge-{status}">{status}</span></div></div>
    <div class="kv-item"><div class="kv-label">导入行数</div><div class="kv-value">{imported:,}</div></div>
    <div class="kv-item"><div class="kv-label">总行数</div><div class="kv-value">{total:,}</div></div>
    <div class="kv-item"><div class="kv-label">进度</div><div class="kv-value">{pct}%</div></div>
  </div>
  <div class="progress"><div class="progress-fill" style="width:{pct}%"></div></div>
</div>
<div class="card">
  <h3>详细信息</h3>
  <table>
    <tr><td>文件路径</td><td>{report_data.get('file', {}).get('path', 'N/A')}</td></tr>
    <tr><td>目标表</td><td>{report_data.get('target', {}).get('table', 'N/A')}</td></tr>
    <tr><td>目标类型</td><td>{report_data.get('target', {}).get('connection_type', 'N/A')}</td></tr>
    <tr><td>导入模式</td><td>{report_data.get('config', {}).get('import_mode', 'N/A')}</td></tr>
    <tr><td>批次大小</td><td>{report_data.get('config', {}).get('batch_size', 'N/A')}</td></tr>
    <tr><td>并行线程</td><td>{report_data.get('config', {}).get('parallel_threads', 'N/A')}</td></tr>
    <tr><td>开始时间</td><td>{report_data.get('timing', {}).get('started_at', 'N/A')}</td></tr>
    <tr><td>完成时间</td><td>{report_data.get('timing', {}).get('completed_at', 'N/A')}</td></tr>
    <tr><td>错误信息</td><td style="color:#ef4444">{report_data.get('errors', {}).get('error_message', '无')}</td></tr>
  </table>
</div>
"""

    elif report_type == "task":
        status = report_data.get("status", "pending")
        execution = report_data.get("execution", {})
        result = execution.get("last_result", {})

        html += f"""
<h2>任务执行报告</h2>
<div class="card">
  <div class="kv">
    <div class="kv-item"><div class="kv-label">任务名称</div><div class="kv-value">{report_data.get('task', {}).get('name', 'N/A')}</div></div>
    <div class="kv-item"><div class="kv-label">任务类型</div><div class="kv-value">{report_data.get('task', {}).get('type', 'N/A')}</div></div>
    <div class="kv-item"><div class="kv-label">状态</div><div class="kv-value"><span class="badge badge-{status}">{status}</span></div></div>
    <div class="kv-item"><div class="kv-label">目标表</div><div class="kv-value">{report_data.get('target', {}).get('table', 'N/A')}</div></div>
  </div>
</div>
<div class="card">
  <h3>执行结果</h3>
  <table>
    <tr><td>插入行数</td><td>{result.get('rows_inserted', 'N/A')}</td></tr>
    <tr><td>读取行数</td><td>{result.get('rows_read', 'N/A')}</td></tr>
    <tr><td>跳过行数</td><td>{result.get('skipped', 'N/A')}</td></tr>
    <tr><td>上次运行</td><td>{execution.get('last_run_at', 'N/A')}</td></tr>
    <tr><td>下次运行</td><td>{execution.get('next_run_at', 'N/A')}</td></tr>
    <tr><td>Cron</td><td>{execution.get('cron_expression', 'N/A')}</td></tr>
    <tr><td>错误</td><td style="color:#ef4444">{execution.get('last_error', '无')}</td></tr>
  </table>
</div>
"""

    html += "<p class='meta'>Generated by 金智汇联ETL</p></body></html>"
    return html
