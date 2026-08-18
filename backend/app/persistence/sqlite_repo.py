import os
import json
import sqlite3
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

# 全局统一使用上海时间（UTC+8）
_SHANGHAI_TZ = timezone(timedelta(hours=8))


def _now_iso() -> str:
    """返回当前上海时间的 ISO 格式字符串。"""
    return datetime.now(_SHANGHAI_TZ).isoformat()


def _get_data_dir() -> Path:
    if os.environ.get("JINZHIHUILIAN_DATA_DIR"):
        return Path(os.environ["JINZHIHUILIAN_DATA_DIR"])
    if os.environ.get("JINZHIHUI_DATA_DIR"):
        return Path(os.environ["JINZHIHUI_DATA_DIR"])
    if os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "jinzhihuilian"
    return Path(__file__).resolve().parent.parent.parent.parent / "shared"


STORE_DIR = _get_data_dir()
DB_PATH = STORE_DIR / "jinzhihuilian.db"
LEGACY_DB_PATH = STORE_DIR / "jinzhihui.db"


def _ensure_store():
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    if (not DB_PATH.exists()) and LEGACY_DB_PATH.exists():
        shutil.copy2(LEGACY_DB_PATH, DB_PATH)


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


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---- Generic Repository ----

class _BaseRepo:
    """通用 SQLite 仓库，自动处理 JSON 字段序列化。"""

    def __init__(self, table: str, pk: str = "id", json_fields: Optional[List[str]] = None):
        self.table = table
        self.pk = pk
        self.json_fields: List[str] = json_fields or []

    def _encode_json_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(data)
        for f in self.json_fields:
            if f in out and isinstance(out[f], (dict, list)):
                out[f] = json.dumps(out[f], ensure_ascii=False)
        return out

    def _decode_json_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(data)
        for f in self.json_fields:
            raw = out.get(f)
            if isinstance(raw, str):
                out[f] = json.loads(raw)
        return out

    def upsert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        row = self._encode_json_fields(data)
        cols = list(row.keys())
        vals = [row[c] for c in cols]
        with _get_db() as conn:
            existing = conn.execute(
                f"SELECT {self.pk} FROM {self.table} WHERE {self.pk} = ?",
                (data[self.pk],),
            ).fetchone()
            if existing:
                set_clause = ", ".join(f"{c}=?" for c in cols)
                vals.append(data[self.pk])
                conn.execute(f"UPDATE {self.table} SET {set_clause} WHERE {self.pk}=?", vals)
            else:
                placeholders = ", ".join("?" for _ in cols)
                col_names = ", ".join(cols)
                conn.execute(f"INSERT INTO {self.table} ({col_names}) VALUES ({placeholders})", vals)
        return self.get(data[self.pk])

    def get(self, pk: str) -> Optional[Dict[str, Any]]:
        with _get_db() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.table} WHERE {self.pk} = ?", (pk,)
            ).fetchone()
            return self._decode_json_fields(_row_to_dict(row)) if row else None

    def list_all(self, order_by: str = "created_at DESC", limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with _get_db() as conn:
            sql = f"SELECT * FROM {self.table} ORDER BY {order_by}"
            if limit:
                sql += f" LIMIT {limit}"
            rows = conn.execute(sql).fetchall()
            return [self._decode_json_fields(_row_to_dict(r)) for r in rows]

    def delete(self, pk: str) -> bool:
        with _get_db() as conn:
            cursor = conn.execute(
                f"DELETE FROM {self.table} WHERE {self.pk} = ?", (pk,)
            )
            return cursor.rowcount > 0


# ---- Concrete Repositories ----

_connection_repo = _BaseRepo("connections", json_fields=["config"])
_schema_repo = _BaseRepo("table_schemas", json_fields=["schema_json"])
_task_repo = _BaseRepo("tasks", json_fields=["config_json"])
_bulk_import_repo = _BaseRepo("bulk_imports", json_fields=["config_json"])
_workflow_repo = _BaseRepo("workflows", json_fields=["workflow_json"])
_sync_record_repo = _BaseRepo("sync_run_records", json_fields=["config_json"])
_pipeline_repo = _BaseRepo("pipelines", json_fields=["pipeline_json"])
_pipeline_run_repo = _BaseRepo("pipeline_runs", json_fields=["config_json"])
_credential_repo = _BaseRepo("credentials", json_fields=["config"])
_kline_source_repo = _BaseRepo("kline_sources", json_fields=["config"])


# ---- Schema initialization ----

def init_db():
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
                config TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS table_schemas (
                id TEXT PRIMARY KEY, table_name TEXT NOT NULL, database_type TEXT NOT NULL,
                schema_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, task_type TEXT NOT NULL,
                source_connection_id TEXT NOT NULL, target_connection_id TEXT NOT NULL,
                target_table TEXT NOT NULL, config_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', cron_expression TEXT,
                last_run_at TEXT, next_run_at TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bulk_imports (
                id TEXT PRIMARY KEY, source_connection_id TEXT NOT NULL,
                target_connection_id TEXT NOT NULL, target_table TEXT NOT NULL,
                file_path TEXT NOT NULL, file_md5 TEXT NOT NULL, config_json TEXT NOT NULL,
                total_rows INTEGER NOT NULL, imported_rows INTEGER DEFAULT 0,
                last_imported_index INTEGER DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
                error_at_row INTEGER, error_message TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, started_at TEXT, completed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT DEFAULT '',
                workflow_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_run_records (
                id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                rows_read INTEGER DEFAULT 0, rows_written INTEGER DEFAULT 0,
                rows_skipped INTEGER DEFAULT 0, error_message TEXT,
                started_at TEXT NOT NULL, finished_at TEXT, config_json TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipelines (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                pipeline_json TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                cron_expression TEXT, status TEXT NOT NULL DEFAULT 'pending',
                last_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id TEXT PRIMARY KEY, pipeline_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                rows_read INTEGER DEFAULT 0, rows_written INTEGER DEFAULT 0,
                rows_skipped INTEGER DEFAULT 0, error_message TEXT,
                duration REAL DEFAULT 0, started_at TEXT NOT NULL, finished_at TEXT,
                config_json TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                FOREIGN KEY (pipeline_id) REFERENCES pipelines(id)
            )
        """)
        # 兼容旧表：自动补加缺失的列
        try:
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()]
            if "created_at" not in cols:
                conn.execute("ALTER TABLE pipeline_runs ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
            if "updated_at" not in cols:
                conn.execute("ALTER TABLE pipeline_runs ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
            # 如果 config_json 是旧版的 NOT NULL 且现有数据为空，无法直接改约束
            # SQLite 不支持 ALTER COLUMN，所以如果旧表有 NOT NULL 约束且没数据，直接 DROP 重建
            if "config_json" in cols:
                col_info = conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()
                config_col = [c for c in col_info if c["name"] == "config_json"]
                if config_col and config_col[0]["notnull"] == 1:
                    # config_json 是 NOT NULL，检查是否有数据
                    row_count = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
                    if row_count == 0:
                        # 没数据，直接 DROP 重建
                        conn.execute("DROP TABLE pipeline_runs")
                        conn.execute("""
                            CREATE TABLE pipeline_runs (
                                id TEXT PRIMARY KEY, pipeline_id TEXT NOT NULL,
                                status TEXT NOT NULL DEFAULT 'running',
                                rows_read INTEGER DEFAULT 0, rows_written INTEGER DEFAULT 0,
                                rows_skipped INTEGER DEFAULT 0, error_message TEXT,
                                duration REAL DEFAULT 0, started_at TEXT NOT NULL, finished_at TEXT,
                                config_json TEXT,
                                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                                FOREIGN KEY (pipeline_id) REFERENCES pipelines(id)
                            )
                        """)
                        print("[DB] 已重建 pipeline_runs 表（修复 config_json NOT NULL 约束）")
        except Exception as e:
            print(f"[DB] pipeline_runs 表迁移失败: {e}")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
                config TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_config (
                id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT 'default',
                provider TEXT NOT NULL DEFAULT 'cloud_demo',
                base_url TEXT NOT NULL DEFAULT 'https://api.siliconflow.cn/v1',
                api_key TEXT NOT NULL, model TEXT NOT NULL DEFAULT '[redacted]/Qwen2.5-7B-Instruct',
                system_prompt TEXT NOT NULL DEFAULT '你是一个量化交易 ETL 系统的技术顾问，帮助用户排查数据源配置、连接问题。',
                stream_mode TEXT NOT NULL DEFAULT 'normal', enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        llm_cols = [r["name"] for r in conn.execute("PRAGMA table_info(llm_config)").fetchall()]
        if "stream_mode" not in llm_cols:
            conn.execute("ALTER TABLE llm_config ADD COLUMN stream_mode TEXT NOT NULL DEFAULT 'normal'")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kline_sources (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
                credential_id TEXT, config TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_assistant_events (
                id TEXT PRIMARY KEY, event_name TEXT NOT NULL, scene TEXT NOT NULL,
                payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            )
        """)
        # 示例教程表（从内容包导入）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS example_docs (
                id INTEGER PRIMARY KEY,
                example_id INTEGER NOT NULL UNIQUE,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                pack_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # 默认 LLM 配置：确保新用户开箱可体验 AI 辅助
        llm_count_row = conn.execute("SELECT COUNT(1) AS cnt FROM llm_config").fetchone()
        if llm_count_row is None or int(llm_count_row["cnt"]) == 0:
            now = _now_iso()
            conn.execute(
                "INSERT INTO llm_config (id, name, provider, base_url, api_key, model, "
                "system_prompt, stream_mode, enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("default", "default", "cloud_demo",
                 "https://api.siliconflow.cn/v1", "",
                 "Qwen/Qwen2.5-7B-Instruct",
                 "你是一个量化交易 ETL 系统的技术顾问，帮助用户排查数据源配置、连接问题。",
                 "normal", 1, now, now),
            )
        else:
            legacy = conn.execute(
                "SELECT id, provider, api_key FROM llm_config "
                "ORDER BY updated_at DESC, created_at DESC LIMIT 1"
            ).fetchone()
            if legacy and str(legacy["provider"]).lower() == "openai" and not str(legacy["api_key"] or "").strip():
                now = _now_iso()
                conn.execute(
                    "UPDATE llm_config SET provider=?, base_url=?, model=?, "
                    "stream_mode=?, enabled=?, updated_at=? WHERE id=?",
                    ("cloud_demo", "https://api.siliconflow.cn/v1",
                     "Qwen/Qwen2.5-7B-Instruct", "normal", 1, now, legacy["id"]),
                )


# ---- Connection CRUD ----

def save_connection(conn_data: Dict[str, Any]) -> Dict[str, Any]:
    return _connection_repo.upsert(conn_data)


def get_connection(conn_id: str) -> Optional[Dict[str, Any]]:
    return _connection_repo.get(conn_id)


def list_connections() -> List[Dict[str, Any]]:
    return _connection_repo.list_all()


def delete_connection(conn_id: str) -> bool:
    return _connection_repo.delete(conn_id)


# ---- Schema CRUD ----

def save_schema(schema_data: Dict[str, Any]) -> Dict[str, Any]:
    return _schema_repo.upsert(schema_data)


def get_schema(schema_id: str) -> Optional[Dict[str, Any]]:
    return _schema_repo.get(schema_id)


def list_schemas() -> List[Dict[str, Any]]:
    return _schema_repo.list_all()


def delete_schema(schema_id: str) -> bool:
    return _schema_repo.delete(schema_id)


# ---- Task CRUD ----

def save_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    return _task_repo.upsert(task_data)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    return _task_repo.get(task_id)


def list_tasks() -> List[Dict[str, Any]]:
    return _task_repo.list_all()


def delete_task(task_id: str) -> bool:
    return _task_repo.delete(task_id)


# ---- Bulk Import CRUD ----

def save_bulk_import(data: Dict[str, Any]) -> Dict[str, Any]:
    return _bulk_import_repo.upsert(data)


def get_bulk_import(import_id: str) -> Optional[Dict[str, Any]]:
    return _bulk_import_repo.get(import_id)


def list_bulk_imports() -> List[Dict[str, Any]]:
    return _bulk_import_repo.list_all()


def delete_bulk_import(import_id: str) -> bool:
    return _bulk_import_repo.delete(import_id)


# ---- Workflow CRUD ----

def save_workflow(data: Dict[str, Any]) -> Dict[str, Any]:
    return _workflow_repo.upsert(data)


def get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    return _workflow_repo.get(workflow_id)


def list_workflows() -> List[Dict[str, Any]]:
    return _workflow_repo.list_all()


def delete_workflow(workflow_id: str) -> bool:
    return _workflow_repo.delete(workflow_id)


# ---- Example Docs CRUD (教程) ----

def save_example_doc(data: Dict[str, Any]) -> Dict[str, Any]:
    """保存示例教程（upsert by example_id）。"""
    now = _now_iso()
    data.setdefault("created_at", now)
    data["updated_at"] = now
    with _get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM example_docs WHERE example_id = ?",
            (data["example_id"],),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE example_docs SET title=?, content=?, pack_name=?, updated_at=? "
                "WHERE example_id=?",
                (data["title"], data["content"], data["pack_name"], now, data["example_id"]),
            )
        else:
            conn.execute(
                "INSERT INTO example_docs (example_id, title, content, pack_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (data["example_id"], data["title"], data["content"], data["pack_name"], now, now),
            )
    return data


def get_example_doc(example_id: int) -> Optional[Dict[str, Any]]:
    """根据示例 ID 获取教程。"""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM example_docs WHERE example_id = ?",
            (example_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None


def list_example_docs(pack_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """列出所有教程（可按包名筛选）。"""
    with _get_db() as conn:
        if pack_name:
            rows = conn.execute(
                "SELECT * FROM example_docs WHERE pack_name = ? ORDER BY example_id",
                (pack_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM example_docs ORDER BY example_id"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]


def delete_example_docs(pack_name: str) -> int:
    """删除指定包的所有教程。"""
    with _get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM example_docs WHERE pack_name = ?",
            (pack_name,),
        )
        return cursor.rowcount


# ---- Sync Run Records CRUD ----

def save_sync_record(data: Dict[str, Any]) -> Dict[str, Any]:
    return _sync_record_repo.upsert(data)


def get_sync_record(record_id: str) -> Optional[Dict[str, Any]]:
    return _sync_record_repo.get(record_id)


def list_sync_records(task_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sync_run_records WHERE task_id = ? ORDER BY started_at DESC LIMIT ?",
            (task_id, limit)
        ).fetchall()
        return [_sync_record_repo._decode_json_fields(_row_to_dict(r)) for r in rows]


# ---- Pipeline CRUD ----

def save_pipeline(data: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    # 更新时保留已有状态字段
    if "id" in data:
        with _get_db() as conn:
            existing = conn.execute(
                "SELECT status, last_run_at FROM pipelines WHERE id = ?", (data["id"],)
            ).fetchone()
            if existing:
                data.setdefault("status", existing["status"])
                data.setdefault("last_run_at", existing["last_run_at"])
    if "enabled" in data and not isinstance(data["enabled"], int):
        data["enabled"] = 1 if data["enabled"] else 0
    return _pipeline_repo.upsert(data)


def get_pipeline(pipeline_id: str) -> Optional[Dict[str, Any]]:
    return _pipeline_repo.get(pipeline_id)


def list_pipelines() -> List[Dict[str, Any]]:
    return _pipeline_repo.list_all()


def delete_pipeline(pipeline_id: str) -> bool:
    with _get_db() as conn:
        conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = ?", (pipeline_id,))
    return _pipeline_repo.delete(pipeline_id)


def save_pipeline_run(data: Dict[str, Any]) -> Dict[str, Any]:
    return _pipeline_run_repo.upsert(data)


def get_pipeline_run(record_id: str) -> Optional[Dict[str, Any]]:
    return _pipeline_run_repo.get(record_id)


def list_pipeline_runs(pipeline_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
    with _get_db() as conn:
        if pipeline_id:
            rows = conn.execute(
                "SELECT * FROM pipeline_runs WHERE pipeline_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (pipeline_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [_pipeline_run_repo._decode_json_fields(_row_to_dict(r)) for r in rows]


# ---- Metadata CRUD ----

def save_metadata(key: str, value: str) -> None:
    now = _now_iso()
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
    return _credential_repo.upsert(data)


def get_credential(credential_id: str) -> Optional[Dict[str, Any]]:
    return _credential_repo.get(credential_id)


def list_credentials() -> List[Dict[str, Any]]:
    from app.core.credential_manager import mask_sensitive
    raw = _credential_repo.list_all()
    for item in raw:
        item["config"] = mask_sensitive(item["config"])
    return raw


def list_credentials_for_select() -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute("SELECT id, name, type FROM credentials ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]


def delete_credential(credential_id: str) -> bool:
    return _credential_repo.delete(credential_id)


# ---- Kline Source CRUD ----

def save_kline_source(source_data: Dict[str, Any]) -> Dict[str, Any]:
    return _kline_source_repo.upsert(source_data)


def get_kline_source(source_id: str) -> Optional[Dict[str, Any]]:
    return _kline_source_repo.get(source_id)


def list_kline_sources() -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM kline_sources ORDER BY created_at DESC").fetchall()
        results = []
        for row in rows:
            data = _kline_source_repo._decode_json_fields(_row_to_dict(row))
            # Attach credential info (name + type only)
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
    return _kline_source_repo.delete(source_id)


# ---- LLM Config CRUD ----

def _encrypt_api_key(key: str) -> str:
    if not key:
        return ""
    try:
        from app.core.credential_manager import encrypt_credential
        return encrypt_credential({"k": key})
    except Exception:
        return key


def _decrypt_api_key(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        from app.core.credential_manager import decrypt_credential
        data = decrypt_credential(encrypted)
        return data.get("k", "")
    except Exception:
        return encrypted


def save_llm_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(cfg)
    cfg["api_key"] = _encrypt_api_key(cfg.get("api_key", ""))
    return _BaseRepo("llm_config").upsert(cfg)


def get_llm_config(cfg_id: str = "default") -> Optional[Dict[str, Any]]:
    repo = _BaseRepo("llm_config")
    data = repo.get(cfg_id)
    if data:
        data["api_key"] = _decrypt_api_key(data.get("api_key", ""))
    return data


def list_ll_configs() -> List[Dict[str, Any]]:
    repo = _BaseRepo("llm_config")
    rows = repo.list_all()
    for data in rows:
        key = _decrypt_api_key(data.get("api_key", ""))
        if not key:
            data["api_key"] = ""
        elif len(key) > 8:
            data["api_key"] = key[:4] + "****" + key[-4:]
        else:
            data["api_key"] = "****"
    return rows


def delete_llm_config(cfg_id: str) -> bool:
    return _BaseRepo("llm_config").delete(cfg_id)


def get_active_llm_config() -> Optional[Dict[str, Any]]:
    """获取当前可用的 LLM 配置（优先 enabled=1，其次按最近创建回退）。"""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM llm_config ORDER BY enabled DESC, updated_at DESC, created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            data = _row_to_dict(row)
            data["api_key"] = _decrypt_api_key(data.get("api_key", ""))
            return data
    return None


# ---- AI Assistant Event ----

def save_ai_assistant_event(event: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO ai_assistant_events (id, event_name, scene, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (event["id"], event["event_name"], event["scene"],
             json.dumps(event.get("payload", {}), ensure_ascii=False), now),
        )
    return get_ai_assistant_event(event["id"])


def get_ai_assistant_event(event_id: str) -> Optional[Dict[str, Any]]:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM ai_assistant_events WHERE id = ?", (event_id,)
        ).fetchone()
        if not row:
            return None
        data = _row_to_dict(row)
        data["payload"] = json.loads(data["payload_json"]) if data.get("payload_json") else {}
        data.pop("payload_json", None)
        return data


def list_ai_assistant_events(limit: int = 200) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM ai_assistant_events ORDER BY created_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        results: List[Dict[str, Any]] = []
        for row in rows:
            data = _row_to_dict(row)
            data["payload"] = json.loads(data["payload_json"]) if data.get("payload_json") else {}
            data.pop("payload_json", None)
            results.append(data)
        return results
