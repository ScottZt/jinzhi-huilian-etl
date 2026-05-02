import pandas as pd
import pymysql
import psycopg2
import duckdb
import clickhouse_driver
import tempfile
import csv
import hashlib
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from app.persistence import sqlite_repo
from app.core.transform_engine import get_transform_engine
from app.adapters.source_adapters.csv_adapter import CSVAdapter
from app.core.parallel_engine import ParallelBulkEngine
from app.adapters.source_adapters.excel_adapter import ExcelAdapter
from app.adapters.source_adapters.json_adapter import JSONAdapter
from app.adapters.source_adapters.parquet_adapter import ParquetAdapter


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


class BulkImportEngine:

    def __init__(self):
        self._running_tasks: Dict[str, "ImportRunner"] = {}

    def start_import(self, import_id: str) -> str:
        if import_id in self._running_tasks:
            existing = self._running_tasks[import_id]
            if existing.is_alive():
                return f"Import {import_id} is already running"

        record = sqlite_repo.get_bulk_import(import_id)
        if not record:
            return f"Bulk import {import_id} not found"

        runner = ImportRunner(import_id)
        self._running_tasks[import_id] = runner
        runner.start()
        return "Import started"

    def pause_import(self, import_id: str) -> str:
        runner = self._running_tasks.get(import_id)
        if runner:
            runner.pause()
            return "Import paused"
        return "Import not found or not running"

    def resume_import(self, import_id: str) -> str:
        runner = self._running_tasks.get(import_id)
        if runner:
            runner.resume()
            return "Import resumed"
        return "Import not found or not running"


    def stop_import(self, import_id: str) -> str:
        runner = self._running_tasks.get(import_id)
        if runner:
            runner.stop()
            return "Import stopped"
        return "Import not found"

    def get_status(self, import_id: str) -> Optional[Dict[str, Any]]:
        return sqlite_repo.get_bulk_import(import_id)


class ImportRunner(threading.Thread):
    """Background thread that runs a bulk import."""

    def __init__(self, import_id: str):
        super().__init__(daemon=True)
        self.import_id = import_id
        self._pause_event = threading.Event()
        self._stop_event = threading.Event()
        self._paused = False

    def pause(self):
        self._paused = True
        self._pause_event.clear()

    def resume(self):
        self._paused = False
        self._pause_event.set()

    def stop(self):
        self._stop_event.set()
        self._pause_event.set()

    def run(self):
        try:
            self._do_import()
        except Exception as e:
            record = sqlite_repo.get_bulk_import(self.import_id)
            if record:
                record["status"] = "failed"
                record["error_message"] = str(e)
                record["updated_at"] = datetime.utcnow().isoformat()
                sqlite_repo.save_bulk_import(record)

    def _do_import(self):
        record = sqlite_repo.get_bulk_import(self.import_id)
        if not record:
            return

        record["status"] = "running"
        record["started_at"] = datetime.utcnow().isoformat()
        record["updated_at"] = datetime.utcnow().isoformat()
        sqlite_repo.save_bulk_import(record)

        source_conn = sqlite_repo.get_connection(record["source_connection_id"])
        target_conn = sqlite_repo.get_connection(record["target_connection_id"])
        config = record["config_json"]
        field_mappings = config.get("field_mappings", [])
        import_mode = config.get("import_mode", "incremental")
        batch_size = config.get("batch_size", 5000)
        parallel_threads = config.get("parallel_threads", 1)

        if not source_conn or not target_conn:
            raise RuntimeError("Source or target connection not found")

        adapter = _get_adapter(record["file_path"])

        target_type = target_conn["type"]
        total_rows = record["total_rows"]
        imported = record["imported_rows"]
        last_idx = record["last_imported_index"]

        if import_mode == "bulk_load":
            if target_type == "mysql":
                self._mysql_bulk_load(record, adapter, field_mappings, batch_size)
            elif target_type == "postgresql":
                self._postgresql_bulk_load(record, adapter, field_mappings, batch_size)
            elif target_type == "duckdb":
                self._duckdb_bulk_load(record, adapter, field_mappings)
            else:
                self._batch_insert(record, adapter, field_mappings, batch_size, parallel_threads)
        elif parallel_threads > 1:
            # Use multiprocessing pool for true parallelism
            self._parallel_insert(record, adapter, field_mappings, batch_size, parallel_threads)
        else:
            self._batch_insert(record, adapter, field_mappings, batch_size, parallel_threads)

        record["status"] = "completed"
        record["completed_at"] = datetime.utcnow().isoformat()
        record["updated_at"] = datetime.utcnow().isoformat()
        sqlite_repo.save_bulk_import(record)

    def _parallel_insert(self, record, adapter, field_mappings, batch_size, parallel_threads):
        """Use multiprocessing pool for true parallel insert."""
        target_conn = sqlite_repo.get_connection(record["target_connection_id"])
        table = record["target_table"]
        target_fields = [m["target_field"] for m in field_mappings]
        source_fields = [m["source_field"] for m in field_mappings]

        # Read full data
        ext = Path(record["file_path"]).suffix.lower()
        if ext == ".csv":
            df = pd.read_csv(record["file_path"], encoding="auto", delimiter="auto", low_memory=False)
        elif ext in (".xlsx", ".xls"):
            df = adapter.read_excel()
        elif ext == ".json":
            df = adapter.read_json()
        elif ext == ".parquet":
            df = adapter.read_parquet()
        else:
            df = pd.read_csv(record["file_path"], encoding="auto", delimiter="auto", low_memory=False)

        # Apply transformations
        if field_mappings:
            transform_engine = get_transform_engine()
            df = transform_engine.apply_field_mappings(df, field_mappings)

        # Use parallel engine
        parallel_engine = ParallelBulkEngine(max_workers=parallel_threads)
        result = parallel_engine.import_parallel(
            df=df,
            target_conn_data=target_conn,
            table=table,
            target_fields=target_fields,
            source_fields=[],
            chunk_size=batch_size,
        )

        record["imported_rows"] = result["total_inserted"]
        record["last_imported_index"] = result["total_inserted"]
        record["updated_at"] = datetime.utcnow().isoformat()
        sqlite_repo.save_bulk_import(record)

        if result["errors"]:
            raise RuntimeError(f"Parallel insert errors: {result['errors']}")

    def _batch_insert(self, record, adapter, field_mappings, batch_size, parallel_threads):
        target_conn = sqlite_repo.get_connection(record["target_connection_id"])
        target_type = target_conn["type"]
        cfg = target_conn["config"]
        table = record["target_table"]

        total_rows = record["total_rows"]
        imported = record["imported_rows"]
        last_idx = record["last_imported_index"]

        ext = Path(record["file_path"]).suffix.lower()
        if ext == ".csv":
            chunk_size = min(batch_size, 10000)
            chunk_iter = pd.read_csv(record["file_path"], encoding="auto", delimiter="auto",
                                     header=0, skiprows=range(1, last_idx + 1) if last_idx > 0 else None,
                                     chunksize=chunk_size, low_memory=False)
        else:
            df_full = adapter.read_csv() if hasattr(adapter, 'read_csv') else \
                      adapter.read_excel() if hasattr(adapter, 'read_excel') else \
                      adapter.read_json() if hasattr(adapter, 'read_json') else \
                      adapter.read_parquet()
            chunk_iter = [df_full]

        # Apply field transformations
        if field_mappings:
            transform_engine = get_transform_engine()
            for i in range(len(chunk_iter)):
                chunk_iter[i] = transform_engine.apply_field_mappings(chunk_iter[i], field_mappings)

        target_fields = [m["target_field"] for m in field_mappings]
        source_fields = [m["source_field"] for m in field_mappings]

        if target_type == "mysql":
            self._mysql_batch_insert(cfg, table, target_fields, source_fields, chunk_iter, record)
        elif target_type == "postgresql":
            self._postgresql_batch_insert(cfg, table, target_fields, source_fields, chunk_iter, record)
        elif target_type == "duckdb":
            self._duckdb_batch_insert(cfg, table, target_fields, source_fields, chunk_iter, record)
        elif target_type == "clickhouse":
            self._clickhouse_batch_insert(cfg, table, target_fields, source_fields, chunk_iter, record)
        else:
            raise RuntimeError(f"Unsupported target type: {target_type}")

    def _mysql_batch_insert(self, cfg, table, target_fields, source_fields, chunk_iter, record):
        conn = pymysql.connect(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
            user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
            local_infile=True,
        )
        cursor = conn.cursor()
        fields_str = ", ".join(target_fields)
        placeholders = ", ".join(["%s"] * len(target_fields))
        sql = f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders})"

        total_rows = record["total_rows"]
        imported = record["imported_rows"]
        last_idx = record["last_imported_index"]

        for chunk_idx, chunk in enumerate(chunk_iter):
            if self._stop_event.is_set():
                break
            if self._paused:
                self._pause_event.wait()

            chunk = chunk[source_fields].copy()
            chunk.columns = target_fields
            chunk = chunk.where(pd.notnull(chunk), None)

            values = [tuple(row) for row in chunk.values]
            if values:
                cursor.executemany(sql, values)
                conn.commit()
                imported += len(values)
                last_idx += len(chunk)

                record["imported_rows"] = imported
                record["last_imported_index"] = last_idx
                record["updated_at"] = datetime.utcnow().isoformat()
                sqlite_repo.save_bulk_import(record)

        cursor.close()
        conn.close()

    def _postgresql_batch_insert(self, cfg, table, target_fields, source_fields, chunk_iter, record):
        conn = psycopg2.connect(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
            user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
        )
        cursor = conn.cursor()
        fields_str = ", ".join(target_fields)
        placeholders = ", ".join(["%s"] * len(target_fields))
        sql = f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders})"

        total_rows = record["total_rows"]
        imported = record["imported_rows"]
        last_idx = record["last_imported_index"]

        for chunk in chunk_iter:
            if self._stop_event.is_set():
                break
            if self._paused:
                self._pause_event.wait()

            chunk = chunk[source_fields].copy()
            chunk.columns = target_fields
            chunk = chunk.where(pd.notnull(chunk), None)

            values = [tuple(row) for row in chunk.values]
            if values:
                cursor.executemany(sql, values)
                conn.commit()
                imported += len(values)
                last_idx += len(chunk)

                record["imported_rows"] = imported
                record["last_imported_index"] = last_idx
                record["updated_at"] = datetime.utcnow().isoformat()
                sqlite_repo.save_bulk_import(record)

        cursor.close()
        conn.close()

    def _duckdb_batch_insert(self, cfg, table, target_fields, source_fields, chunk_iter, record):
        db_path = cfg.get("db_path", ":memory:")
        conn = duckdb.connect(db_path, read_only=False)
        cursor = conn.cursor()

        total_rows = record["total_rows"]
        imported = record["imported_rows"]
        last_idx = record["last_imported_index"]

        for chunk in chunk_iter:
            if self._stop_event.is_set():
                break
            if self._paused:
                self._pause_event.wait()

            chunk = chunk[source_fields].copy()
            chunk.columns = target_fields
            conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM chunk")
            imported += len(chunk)
            last_idx += len(chunk)

            record["imported_rows"] = imported
            record["last_imported_index"] = last_idx
            record["updated_at"] = datetime.utcnow().isoformat()
            sqlite_repo.save_bulk_import(record)

        conn.close()

    def _clickhouse_batch_insert(self, cfg, table, target_fields, source_fields, chunk_iter, record):
        client = clickhouse_driver.Client(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 9000)),
            user=cfg.get("user", "default"), password=cfg.get("password", ""),
            database=cfg.get("database", "default"),
        )

        total_rows = record["total_rows"]
        imported = record["imported_rows"]
        last_idx = record["last_imported_index"]

        for chunk in chunk_iter:
            if self._stop_event.is_set():
                break
            if self._paused:
                self._pause_event.wait()

            chunk = chunk[source_fields].copy()
            chunk.columns = target_fields
            client.execute(f"INSERT INTO {table}", chunk.to_dict("records"))
            imported += len(chunk)
            last_idx += len(chunk)

            record["imported_rows"] = imported
            record["last_imported_index"] = last_idx
            record["updated_at"] = datetime.utcnow().isoformat()
            sqlite_repo.save_bulk_import(record)

    def _mysql_bulk_load(self, record, adapter, field_mappings, batch_size):
        conn_cfg = sqlite_repo.get_connection(record["target_connection_id"])
        cfg = conn_cfg["config"]
        table = record["target_table"]
        target_fields = [m["target_field"] for m in field_mappings]
        source_fields = [m["source_field"] for m in field_mappings]
        fields_str = ", ".join(target_fields)

        df_all = adapter.read_csv()
        df_mapped = df_all[source_fields].copy()
        df_mapped.columns = target_fields

        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='', encoding='utf-8')
        df_mapped.to_csv(temp_file.name, index=False, quoting=csv.QUOTE_MINIMAL)
        temp_file.close()

        conn = pymysql.connect(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
            user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
            local_infile=True,
        )
        cursor = conn.cursor()
        csv_path = temp_file.name.replace('\\', '/')
        sql = f"""
        LOAD DATA LOCAL INFILE '{csv_path}'
        INTO TABLE {table}
        FIELDS TERMINATED BY ','
        ENCLOSED BY '"'
        LINES TERMINATED BY '\\n'
        IGNORE 1 ROWS
        ({fields_str})
        """
        cursor.execute(sql)
        conn.commit()
        record["imported_rows"] = len(df_mapped)
        record["last_imported_index"] = len(df_mapped)
        record["updated_at"] = datetime.utcnow().isoformat()
        sqlite_repo.save_bulk_import(record)
        cursor.close()
        conn.close()

    def _postgresql_bulk_load(self, record, adapter, field_mappings, batch_size):
        conn_cfg = sqlite_repo.get_connection(record["target_connection_id"])
        cfg = conn_cfg["config"]
        table = record["target_table"]
        target_fields = [m["target_field"] for m in field_mappings]
        source_fields = [m["source_field"] for m in field_mappings]

        df_all = adapter.read_csv()
        df_mapped = df_all[source_fields].copy()
        df_mapped.columns = target_fields

        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='', encoding='utf-8')
        df_mapped.to_csv(temp_file.name, index=False, quoting=csv.QUOTE_MINIMAL)
        temp_file.close()

        conn = psycopg2.connect(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
            user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
        )
        cursor = conn.cursor()
        with open(temp_file.name, 'r') as f:
            cursor.copy_expert(
                f"COPY {table} ({', '.join(target_fields)}) FROM STDIN WITH CSV HEADER",
                f
            )
        conn.commit()
        record["imported_rows"] = len(df_mapped)
        record["last_imported_index"] = len(df_mapped)
        record["updated_at"] = datetime.utcnow().isoformat()
        sqlite_repo.save_bulk_import(record)
        cursor.close()
        conn.close()

    def _duckdb_bulk_load(self, record, adapter, field_mappings):
        conn_cfg = sqlite_repo.get_connection(record["target_connection_id"])
        cfg = conn_cfg["config"]
        table = record["target_table"]
        db_path = cfg.get("db_path", ":memory:")
        conn = duckdb.connect(db_path, read_only=False)
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='', encoding='utf-8')
        adapter.read_csv().to_csv(temp_file.name, index=False)
        temp_file.close()
        conn.execute(f"COPY {table} FROM '{temp_file.name}' (FORMAT CSV, HEADER TRUE)")
        df = adapter.read_csv()
        record["imported_rows"] = len(df)
        record["last_imported_index"] = len(df)
        record["updated_at"] = datetime.utcnow().isoformat()
        sqlite_repo.save_bulk_import(record)
        conn.close()


_engine = BulkImportEngine()


def get_engine() -> BulkImportEngine:
    return _engine
