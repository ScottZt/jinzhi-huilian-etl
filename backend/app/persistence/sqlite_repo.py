import os
import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import contextmanager

def _get_data_dir() -> Path:
    if os.environ.get("JINZHIHUI_DATA_DIR"):
        return Path(os.environ["JINZHIHUI_DATA_DIR"])
    if os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "JinZhiHuiETL"
    return Path(__file__).resolve().parent.parent.parent.parent / "shared"

STORE_DIR = _get_data_dir()
DB_PATH = STORE_DIR / "jinzhihui.db"


def _ensure_store():
    STORE_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def _get_db():
    _ensure_store()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                config TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS table_schemas (
                id TEXT PRIMARY KEY,
                table_name TEXT NOT NULL,
                database_type TEXT NOT NULL,
                schema_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                task_type TEXT NOT NULL,
                source_connection_id TEXT NOT NULL,
                target_connection_id TEXT NOT NULL,
                target_table TEXT NOT NULL,
                config_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                cron_expression TEXT,
                last_run_at TEXT,
                next_run_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bulk_imports (
                id TEXT PRIMARY KEY,
                source_connection_id TEXT NOT NULL,
                target_connection_id TEXT NOT NULL,
                target_table TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_md5 TEXT NOT NULL,
                config_json TEXT NOT NULL,
                total_rows INTEGER NOT NULL,
                imported_rows INTEGER DEFAULT 0,
                last_imported_index INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                error_at_row INTEGER,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                workflow_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_run_records (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                rows_read INTEGER DEFAULT 0,
                rows_written INTEGER DEFAULT 0,
                rows_skipped INTEGER DEFAULT 0,
                error_message TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                config_json TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipelines (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                pipeline_json TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                cron_expression TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                last_run_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id TEXT PRIMARY KEY,
                pipeline_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                rows_read INTEGER DEFAULT 0,
                rows_written INTEGER DEFAULT 0,
                rows_skipped INTEGER DEFAULT 0,
                error_message TEXT,
                duration REAL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                config_json TEXT NOT NULL,
                FOREIGN KEY (pipeline_id) REFERENCES pipelines(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                config TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_config (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT 'default',
                provider TEXT NOT NULL DEFAULT 'openai',
                base_url TEXT NOT NULL DEFAULT 'https://api.openai.com/v1',
                api_key TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
                system_prompt TEXT NOT NULL DEFAULT '你是一个量化交易 ETL 系统的技术顾问，帮助用户排查数据源配置、连接问题。',
                enabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kline_sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                credential_id TEXT,
                config TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---- Connection CRUD ----

def save_connection(conn_data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM connections WHERE id = ?", (conn_data["id"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE connections SET name=?, type=?, config=?, updated_at=? WHERE id=?",
                (conn_data["name"], conn_data["type"], json.dumps(conn_data["config"]), now, conn_data["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO connections (id, name, type, config, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (conn_data["id"], conn_data["name"], conn_data["type"], json.dumps(conn_data["config"]), now, now),
            )
    return get_connection(conn_data["id"])


def get_connection(conn_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM connections WHERE id = ?", (conn_id,)).fetchone()
        if row:
            data = _row_to_dict(row)
            data["config"] = json.loads(data["config"])
            return data
    return None


def list_connections() -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM connections ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["config"] = json.loads(d["config"])
            result.append(d)
        return result


def delete_connection(conn_id: str) -> bool:
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
        return cursor.rowcount > 0


# ---- Schema CRUD ----

def save_schema(schema_data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM table_schemas WHERE id = ?", (schema_data["id"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE table_schemas SET table_name=?, database_type=?, schema_json=?, updated_at=? WHERE id=?",
                (schema_data["table_name"], schema_data["database_type"],
                 json.dumps(schema_data["schema_json"]), now, schema_data["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO table_schemas (id, table_name, database_type, schema_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (schema_data["id"], schema_data["table_name"], schema_data["database_type"],
                 json.dumps(schema_data["schema_json"]), now, now),
            )
    return get_schema(schema_data["id"])


def get_schema(schema_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM table_schemas WHERE id = ?", (schema_id,)).fetchone()
        if row:
            data = _row_to_dict(row)
            data["schema_json"] = json.loads(data["schema_json"])
            return data
    return None


def list_schemas() -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM table_schemas ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["schema_json"] = json.loads(d["schema_json"])
            result.append(d)
        return result


def delete_schema(schema_id: str) -> bool:
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM table_schemas WHERE id = ?", (schema_id,))
        return cursor.rowcount > 0


# ---- Task CRUD ----

def save_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM tasks WHERE id = ?", (task_data["id"],)
        ).fetchone()
        if existing:
            updates = []
            vals = []
            for key in ["name", "task_type", "source_connection_id", "target_connection_id",
                        "target_table", "config_json", "status", "cron_expression",
                        "last_run_at", "next_run_at", "updated_at"]:
                if key in task_data:
                    updates.append(f"{key}=?")
                    vals.append(task_data.get(key))
            vals.append(task_data["id"])
            conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id=?", vals)
        else:
            conn.execute(
                """INSERT INTO tasks (id, name, task_type, source_connection_id, target_connection_id,
                   target_table, config_json, status, cron_expression, last_run_at, next_run_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_data["id"], task_data["name"], task_data["task_type"],
                 task_data["source_connection_id"], task_data["target_connection_id"],
                 task_data["target_table"], json.dumps(task_data.get("config_json", {})),
                 task_data.get("status", "pending"), task_data.get("cron_expression"),
                 task_data.get("last_run_at"), task_data.get("next_run_at"), now, now),
            )
    return get_task(task_data["id"])


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            data = _row_to_dict(row)
            data["config_json"] = json.loads(data["config_json"]) if data["config_json"] else {}
            return data
    return None


def list_tasks() -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["config_json"] = json.loads(d["config_json"]) if d["config_json"] else {}
            result.append(d)
        return result


def delete_task(task_id: str) -> bool:
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cursor.rowcount > 0


# ---- Bulk Import CRUD ----

def save_bulk_import(data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM bulk_imports WHERE id = ?", (data["id"],)
        ).fetchone()
        if existing:
            updates = []
            vals = []
            for key in ["source_connection_id", "target_connection_id", "target_table",
                        "file_path", "file_md5", "config_json", "total_rows", "imported_rows",
                        "last_imported_index", "status", "error_at_row", "error_message",
                        "started_at", "completed_at", "updated_at"]:
                if key in data:
                    updates.append(f"{key}=?")
                    vals.append(data.get(key))
            vals.append(data["id"])
            conn.execute(f"UPDATE bulk_imports SET {', '.join(updates)} WHERE id=?", vals)
        else:
            conn.execute(
                """INSERT INTO bulk_imports (id, source_connection_id, target_connection_id,
                   target_table, file_path, file_md5, config_json, total_rows, imported_rows,
                   last_imported_index, status, error_at_row, error_message, created_at, updated_at,
                   started_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data["id"], data["source_connection_id"], data["target_connection_id"],
                 data["target_table"], data["file_path"], data["file_md5"],
                 json.dumps(data.get("config_json", {})), data.get("total_rows", 0),
                 data.get("imported_rows", 0), data.get("last_imported_index", 0),
                 data.get("status", "pending"), data.get("error_at_row"),
                 data.get("error_message"), now, now, data.get("started_at"),
                 data.get("completed_at")),
            )
    return get_bulk_import(data["id"])


def get_bulk_import(import_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM bulk_imports WHERE id = ?", (import_id,)).fetchone()
        if row:
            data = _row_to_dict(row)
            data["config_json"] = json.loads(data["config_json"]) if data["config_json"] else {}
            return data
    return None


def list_bulk_imports() -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM bulk_imports ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["config_json"] = json.loads(d["config_json"]) if d["config_json"] else {}
            result.append(d)
        return result


def delete_bulk_import(import_id: str) -> bool:
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM bulk_imports WHERE id = ?", (import_id,))
        return cursor.rowcount > 0


# ---- Workflow CRUD ----

def save_workflow(data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute("SELECT id FROM workflows WHERE id = ?", (data["id"],)).fetchone()
        if existing:
            conn.execute(
                "UPDATE workflows SET name=?, description=?, workflow_json=?, updated_at=? WHERE id=?",
                (data["name"], data.get("description", ""), json.dumps(data["workflow_json"]),
                 now, data["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO workflows (id, name, description, workflow_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (data["id"], data["name"], data.get("description", ""),
                 json.dumps(data["workflow_json"]), now, now),
            )
    return get_workflow(data["id"])


def get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        if row:
            d = _row_to_dict(row)
            d["workflow_json"] = json.loads(d["workflow_json"]) if d["workflow_json"] else {}
            return d
    return None


def list_workflows() -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["workflow_json"] = json.loads(d["workflow_json"]) if d["workflow_json"] else {}
            result.append(d)
        return result


def delete_workflow(workflow_id: str) -> bool:
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        return cursor.rowcount > 0


# ---- Sync Run Records CRUD ----

def save_sync_record(data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute("SELECT id FROM sync_run_records WHERE id = ?", (data["id"],)).fetchone()
        if existing:
            updates = []
            vals = []
            for key in ["task_id", "status", "rows_read", "rows_written", "rows_skipped",
                        "error_message", "finished_at", "config_json"]:
                if key in data:
                    updates.append(f"{key}=?")
                    vals.append(data.get(key))
            vals.append(data["id"])
            conn.execute(f"UPDATE sync_run_records SET {', '.join(updates)} WHERE id=?", vals)
        else:
            conn.execute(
                """INSERT INTO sync_run_records (id, task_id, status, rows_read, rows_written,
                   rows_skipped, error_message, started_at, finished_at, config_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data["id"], data["task_id"], data.get("status", "running"),
                 data.get("rows_read", 0), data.get("rows_written", 0), data.get("rows_skipped", 0),
                 data.get("error_message"), data.get("started_at", now),
                 data.get("finished_at"), json.dumps(data.get("config_json", {}))),
            )
    return get_sync_record(data["id"])


def get_sync_record(record_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM sync_run_records WHERE id = ?", (record_id,)).fetchone()
        if row:
            d = _row_to_dict(row)
            d["config_json"] = json.loads(d["config_json"]) if d["config_json"] else {}
            return d
    return None


def list_sync_records(task_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sync_run_records WHERE task_id = ? ORDER BY started_at DESC LIMIT ?",
            (task_id, limit)
        ).fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["config_json"] = json.loads(d["config_json"]) if d["config_json"] else {}
            result.append(d)
        return result


# ---- Pipeline CRUD ----

def save_pipeline(data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM pipelines WHERE id = ?", (data["id"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE pipelines SET name=?, description=?, pipeline_json=?, enabled=?, "
                "cron_expression=?, updated_at=? WHERE id=?",
                (data["name"], data.get("description", ""), json.dumps(data.get("pipeline_json", {})),
                 1 if data.get("enabled", True) else 0, data.get("cron_expression"), now, data["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO pipelines (id, name, description, pipeline_json, enabled, "
                "cron_expression, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data["id"], data["name"], data.get("description", ""),
                 json.dumps(data.get("pipeline_json", {})),
                 1 if data.get("enabled", True) else 0, data.get("cron_expression"),
                 data.get("status", "pending"), now, now),
            )
    return get_pipeline(data["id"])


def get_pipeline(pipeline_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()
        if row:
            d = _row_to_dict(row)
            d["pipeline_json"] = json.loads(d["pipeline_json"]) if d["pipeline_json"] else {}
            return d
    return None


def list_pipelines() -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM pipelines ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["pipeline_json"] = json.loads(d["pipeline_json"]) if d["pipeline_json"] else {}
            result.append(d)
        return result


def delete_pipeline(pipeline_id: str) -> bool:
    with _get_db() as conn:
        conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = ?", (pipeline_id,))
        conn.execute("DELETE FROM pipelines WHERE id = ?", (pipeline_id,))
        return conn.total_changes > 0


def save_pipeline_run(data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM pipeline_runs WHERE id = ?", (data["id"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE pipeline_runs SET status=?, rows_read=?, rows_written=?, "
                "rows_skipped=?, error_message=?, duration=?, finished_at=?, config_json=? WHERE id=?",
                (data.get("status", "running"), data.get("rows_read", 0), data.get("rows_written", 0),
                 data.get("rows_skipped", 0), data.get("error_message"),
                 data.get("duration", 0), data.get("finished_at"),
                 json.dumps(data.get("config_json", {})), data["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO pipeline_runs (id, pipeline_id, status, rows_read, rows_written, "
                "rows_skipped, error_message, duration, started_at, finished_at, config_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data["id"], data["pipeline_id"], data.get("status", "running"),
                 data.get("rows_read", 0), data.get("rows_written", 0), data.get("rows_skipped", 0),
                 data.get("error_message"), data.get("duration", 0),
                 data.get("started_at", now), data.get("finished_at"),
                 json.dumps(data.get("config_json", {}))),
            )
    return get_pipeline_run(data["id"])


def get_pipeline_run(record_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (record_id,)).fetchone()
        if row:
            d = _row_to_dict(row)
            d["config_json"] = json.loads(d["config_json"]) if d["config_json"] else {}
            return d
    return None


def list_pipeline_runs(pipeline_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
    with _get_db() as conn:
        if pipeline_id:
            rows = conn.execute(
                "SELECT * FROM pipeline_runs WHERE pipeline_id = ? ORDER BY started_at DESC LIMIT ?",
                (pipeline_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["config_json"] = json.loads(d["config_json"]) if d["config_json"] else {}
            result.append(d)
        return result

# ---- Metadata CRUD ----

def save_metadata(key: str, value: str) -> None:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute('SELECT key FROM metadata WHERE key = ?', (key,)).fetchone()
        if existing:
            conn.execute('UPDATE metadata SET value=?, updated_at=? WHERE key=?', (value, now, key))
        else:
            conn.execute('INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)', (key, value, now))


def get_metadata(key: str) -> Optional[str]:
    with _get_db() as conn:
        row = conn.execute('SELECT value FROM metadata WHERE key = ?', (key,)).fetchone()
        return row[0] if row else None


def delete_metadata(key: str) -> bool:
    with _get_db() as conn:
        cursor = conn.execute('DELETE FROM metadata WHERE key = ?', (key,))
        return cursor.rowcount > 0


# ---- Credential CRUD ----

def save_credential(data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM credentials WHERE id = ?", (data["id"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE credentials SET name=?, type=?, config=?, updated_at=? WHERE id=?",
                (data["name"], data["type"], json.dumps(data["config"]), now, data["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO credentials (id, name, type, config, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (data["id"], data["name"], data["type"], json.dumps(data["config"]), now, now),
            )
    return get_credential(data["id"])


def get_credential(credential_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM credentials WHERE id = ?", (credential_id,)).fetchone()
        if row:
            data = _row_to_dict(row)
            data["config"] = json.loads(data["config"])
            return data
    return None


def list_credentials() -> List[Dict[str, Any]]:
    from app.core.credential_manager import mask_sensitive
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM credentials ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            cfg = json.loads(d["config"])
            d["config"] = mask_sensitive(cfg)
            result.append(d)
        return result


def list_credentials_for_select() -> List[Dict[str, Any]]:
    """Return only id, name, type for dropdown selection."""
    with _get_db() as conn:
        rows = conn.execute("SELECT id, name, type FROM credentials ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]


def delete_credential(credential_id: str) -> bool:
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM credentials WHERE id = ?", (credential_id,))
        return cursor.rowcount > 0


# ---- Kline Source CRUD (independent from connections) ----

def save_kline_source(source_data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM kline_sources WHERE id = ?", (source_data["id"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE kline_sources SET name=?, type=?, credential_id=?, config=?, updated_at=? WHERE id=?",
                (source_data["name"], source_data["type"], source_data.get("credential_id", ""),
                 json.dumps(source_data["config"]), now, source_data["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO kline_sources (id, name, type, credential_id, config, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source_data["id"], source_data["name"], source_data["type"],
                 source_data.get("credential_id", ""), json.dumps(source_data["config"]), now, now),
            )
    return get_kline_source(source_data["id"])


def get_kline_source(source_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM kline_sources WHERE id = ?", (source_id,)).fetchone()
        if row:
            data = _row_to_dict(row)
            data["config"] = json.loads(data["config"])
            return data
    return None


def list_kline_sources() -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM kline_sources ORDER BY created_at DESC").fetchall()
        results = []
        for row in rows:
            data = _row_to_dict(row)
            data["config"] = json.loads(data["config"])
            # Attach credential info (name + type only, not the token)
            if data.get("credential_id"):
                cred = conn.execute(
                    "SELECT id, name, type FROM credentials WHERE id = ?",
                    (data["credential_id"],)
                ).fetchone()
                if cred:
                    data["credential"] = _row_to_dict(cred)
            results.append(data)
        return results


def delete_kline_source(source_id: str) -> bool:
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM kline_sources WHERE id = ?", (source_id,))
        return cursor.rowcount > 0


# ---- LLM Config CRUD ----

def save_llm_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        existing = conn.execute("SELECT id FROM llm_config WHERE id = ?", (cfg["id"],)).fetchone()
        if existing:
            conn.execute(
                "UPDATE llm_config SET name=?, provider=?, base_url=?, api_key=?, model=?, system_prompt=?, enabled=?, updated_at=? WHERE id=?",
                (cfg.get("name", "default"), cfg.get("provider", "openai"), cfg.get("base_url", ""),
                 cfg.get("api_key", ""), cfg.get("model", "gpt-4o-mini"),
                 cfg.get("system_prompt", ""), cfg.get("enabled", 0), now, cfg["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO llm_config (id, name, provider, base_url, api_key, model, system_prompt, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cfg.get("id", "default"), cfg.get("name", "default"), cfg.get("provider", "openai"),
                 cfg.get("base_url", ""), cfg.get("api_key", ""),
                 cfg.get("model", "gpt-4o-mini"), cfg.get("system_prompt", ""),
                 cfg.get("enabled", 0), now, now),
            )
    return get_llm_config(cfg["id"])


def get_llm_config(cfg_id: str = "default") -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM llm_config WHERE id = ?", (cfg_id,)).fetchone()
        if row:
            return _row_to_dict(row)
    return None


def list_ll_configs() -> List[Dict[str, Any]]:
    """List all LLM configs, with api_key masked."""
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM llm_config ORDER BY created_at DESC").fetchall()
        results = []
        for row in rows:
            data = _row_to_dict(row)
            # Mask API key in list
            key = data.get("api_key", "")
            if key and len(key) > 8:
                data["api_key"] = key[:4] + "****" + key[-4:]
            else:
                data["api_key"] = "****"
            results.append(data)
        return results


def delete_llm_config(cfg_id: str) -> bool:
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM llm_config WHERE id = ?", (cfg_id,))
        return cursor.rowcount > 0
