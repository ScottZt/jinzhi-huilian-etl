import logging
import pandas as pd
import pymysql
import psycopg2
import duckdb
import clickhouse_driver
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import threading

from app.persistence import sqlite_repo
from app.core.transform_engine import get_transform_engine

logger = logging.getLogger(__name__)


class ExecutionEngine:

    def __init__(self):
        self._running_tasks: Dict[str, threading.Thread] = {}

    def execute_sync(self, task_id: str) -> Dict[str, Any]:
        """Execute a sync task synchronously (called by scheduler or manual run)."""
        task = sqlite_repo.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        task["status"] = "running"
        task["started_at"] = datetime.utcnow().isoformat()
        task["updated_at"] = datetime.utcnow().isoformat()
        sqlite_repo.save_task(task)

        try:
            result = self._do_sync(task)
            task["status"] = "completed"
            task["last_run_at"] = datetime.utcnow().isoformat()
            task["updated_at"] = datetime.utcnow().isoformat()
            task["config_json"]["last_result"] = result
            sqlite_repo.save_task(task)
            return result
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            task["status"] = "failed"
            task["last_run_at"] = datetime.utcnow().isoformat()
            task["updated_at"] = datetime.utcnow().isoformat()
            task["config_json"]["last_error"] = str(e)
            sqlite_repo.save_task(task)
            return {"error": str(e)}

    def execute_async(self, task_id: str) -> str:
        """Execute a sync task in a background thread."""
        if task_id in self._running_tasks and self._running_tasks[task_id].is_alive():
            return f"Task {task_id} is already running"

        thread = threading.Thread(target=self.execute_sync, args=(task_id,), daemon=True)
        self._running_tasks[task_id] = thread
        thread.start()
        return f"Task {task_id} started in background"

    def _do_sync(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task["task_type"]
        source_conn = sqlite_repo.get_connection(task["source_connection_id"])
        target_conn = sqlite_repo.get_connection(task["target_connection_id"])
        config = task["config_json"]

        if not source_conn:
            raise RuntimeError(f"Source connection {task['source_connection_id']} not found")
        if not target_conn:
            raise RuntimeError(f"Target connection {task['target_connection_id']} not found")

        if source_conn["type"] == "csv":
            return self._sync_from_csv(source_conn, target_conn, task, config)
        elif source_conn["type"] in ("mysql", "postgresql", "duckdb", "clickhouse"):
            return self._sync_from_db(source_conn, target_conn, task, config)
        elif source_conn["type"] in ("excel", "json", "parquet"):
            return self._sync_from_file(source_conn, target_conn, task, config)
        else:
            raise RuntimeError(f"Unsupported source type: {source_conn['type']}")

    def _sync_from_csv(self, source_conn, target_conn, task, config) -> Dict[str, Any]:
        file_path = source_conn["config"].get("file_path")
        if not file_path:
            raise RuntimeError("CSV source: file_path not configured")

        df = self._read_file_as_df(source_conn["type"], file_path)

        # Apply field transformations if configured
        field_mappings = config.get("field_mappings", [])
        if field_mappings:
            transform_engine = get_transform_engine()
            df = transform_engine.apply_field_mappings(df, field_mappings)

        start_date = config.get("start_date")
        end_date = config.get("end_date")
        if start_date:
            date_col = config.get("date_column", "date")
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df[df[date_col] >= pd.to_datetime(start_date)]
        if end_date:
            date_col = config.get("date_column", "date")
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df[df[date_col] <= pd.to_datetime(end_date)]

        target_table = task["target_table"]
        batch_size = config.get("batch_size", 5000)

        inserted = self._insert_to_target(df, target_conn, target_table, batch_size)
        return {
            "source": "csv",
            "target": target_conn["type"],
            "table": target_table,
            "rows_read": len(df),
            "rows_inserted": inserted,
            "skipped": len(df) - inserted,
        }

    def _sync_from_db(self, source_conn, target_conn, task, config) -> Dict[str, Any]:
        query = config.get("query")
        table = config.get("source_table") or task["target_table"]

        df = self._read_from_source_db(source_conn, table, query, config)

        target_table = task["target_table"]
        batch_size = config.get("batch_size", 5000)

        inserted = self._insert_to_target(df, target_conn, target_table, batch_size)
        return {
            "source": source_conn["type"],
            "target": target_conn["type"],
            "table": target_table,
            "rows_read": len(df),
            "rows_inserted": inserted,
            "skipped": len(df) - inserted,
        }

    def _sync_from_file(self, source_conn, target_conn, task, config) -> Dict[str, Any]:
        file_path = source_conn["config"].get("file_path")
        if not file_path:
            raise RuntimeError(f"{source_conn['type']} source: file_path not configured")

        df = self._read_file_as_df(source_conn["type"], file_path)

        # Apply field transformations
        field_mappings = config.get("field_mappings", [])
        if field_mappings:
            transform_engine = get_transform_engine()
            df = transform_engine.apply_field_mappings(df, field_mappings)

        target_table = task["target_table"]
        batch_size = config.get("batch_size", 5000)
        inserted = self._insert_to_target(df, target_conn, target_table, batch_size)
        return {
            "source": source_conn["type"],
            "target": target_conn["type"],
            "table": target_table,
            "rows_read": len(df),
            "rows_inserted": inserted,
        }

    def _read_file_as_df(self, file_type: str, file_path: str) -> pd.DataFrame:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_type == "csv":
            return pd.read_csv(file_path, encoding="utf-8", low_memory=False)
        elif file_type == "excel":
            return pd.read_excel(file_path)
        elif file_type == "json":
            return pd.read_json(file_path)
        elif file_type == "parquet":
            return pd.read_parquet(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    def _read_from_source_db(self, conn_data: Dict, table: str, query: Optional[str], config: Dict) -> pd.DataFrame:
        db_type = conn_data["type"]
        cfg = conn_data["config"]

        if query:
            sql = query
        else:
            date_col = config.get("date_column", "trade_date")
            start_date = config.get("start_date")
            end_date = config.get("end_date")
            if start_date and date_col:
                sql = f"SELECT * FROM {table} WHERE {date_col} >= '{start_date}'"
                if end_date:
                    sql += f" AND {date_col} <= '{end_date}'"
            else:
                sql = f"SELECT * FROM {table}"

        if db_type == "mysql":
            conn = pymysql.connect(
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
                user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
            )
            return pd.read_sql(sql, conn)
        elif db_type == "postgresql":
            conn = psycopg2.connect(
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
                user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
            )
            return pd.read_sql(sql, conn)
        elif db_type == "duckdb":
            db_path = cfg.get("db_path", "")
            if not db_path:
                raise ValueError("db_path 为空")
            conn = duckdb.connect(db_path, read_only=False)
            return conn.execute(sql).fetchdf()
        elif db_type == "clickhouse":
            client = clickhouse_driver.Client(
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 9000)),
                user=cfg.get("user", "default"), password=cfg.get("password", ""),
                database=cfg.get("database", "default"),
            )
            return client.query_dataframe(sql)
        else:
            raise ValueError(f"Unsupported source DB type: {db_type}")

    def _insert_to_target(self, df: pd.DataFrame, target_conn: Dict, table: str, batch_size: int) -> int:
        if df.empty:
            return 0

        df = df.where(pd.notnull(df), None)
        db_type = target_conn["type"]
        cfg = target_conn["config"]
        columns = df.columns.tolist()
        fields_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))

        total_inserted = 0

        if db_type == "mysql":
            conn = pymysql.connect(
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
                user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
            )
            cursor = conn.cursor()
            sql = f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders})"
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i+batch_size]
                values = [tuple(row) for row in batch.values]
                cursor.executemany(sql, values)
                conn.commit()
                total_inserted += len(values)
            cursor.close()
            conn.close()

        elif db_type == "postgresql":
            conn = psycopg2.connect(
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
                user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
            )
            cursor = conn.cursor()
            sql = f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders})"
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i+batch_size]
                values = [tuple(row) for row in batch.values]
                cursor.executemany(sql, values)
                conn.commit()
                total_inserted += len(values)
            cursor.close()
            conn.close()

        elif db_type == "duckdb":
            db_path = cfg.get("db_path", "")
            if not db_path:
                raise ValueError("db_path 为空")
            conn = duckdb.connect(db_path, read_only=False)
            conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
            total_inserted = len(df)
            conn.close()

        elif db_type == "clickhouse":
            client = clickhouse_driver.Client(
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 9000)),
                user=cfg.get("user", "default"), password=cfg.get("password", ""),
                database=cfg.get("database", "default"),
            )
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i+batch_size]
                records = batch.to_dict("records")
                client.execute(f"INSERT INTO {table}", records)
                total_inserted += len(records)

        else:
            raise ValueError(f"Unsupported target DB type: {db_type}")

        return total_inserted


_engine = ExecutionEngine()


def get_execution_engine() -> ExecutionEngine:
    return _engine
