"""
Parallel processing engine using multiprocessing to bypass GIL.
Each worker process has its own DB connection for true parallelism.
"""
import pandas as pd
import multiprocessing as mp
from typing import Dict, Any, List, Tuple, Optional
import pymysql
import psycopg2
import duckdb
import clickhouse_driver
from concurrent.futures import ProcessPoolExecutor, as_completed
import tempfile
import csv
import os
from pathlib import Path

from app.persistence import sqlite_repo


def _worker_insert(args: Tuple) -> Dict[str, Any]:
    """
    Worker function that runs in a separate process.
    Each worker gets its own DB connection.
    Returns: {"rows_inserted": N, "error": None or str}
    """
    chunk_df, target_conn_data, table, target_fields, source_fields, worker_id = args
    target_type = target_conn_data["type"]
    cfg = target_conn_data["config"]

    try:
        if chunk_df.empty:
            return {"rows_inserted": 0, "worker_id": worker_id, "error": None}

        # Apply field mapping
        if source_fields and target_fields:
            chunk_df = chunk_df[source_fields].copy()
            chunk_df.columns = target_fields
        chunk_df = chunk_df.where(pd.notnull(chunk_df), None)

        if target_type == "mysql":
            return _mysql_insert_worker(chunk_df, cfg, table, worker_id)
        elif target_type == "postgresql":
            return _postgres_insert_worker(chunk_df, cfg, table, worker_id)
        elif target_type == "duckdb":
            return _duckdb_insert_worker(chunk_df, cfg, table, worker_id)
        elif target_type == "clickhouse":
            return _clickhouse_insert_worker(chunk_df, cfg, table, worker_id)
        else:
            return {"rows_inserted": 0, "worker_id": worker_id, "error": f"Unsupported type: {target_type}"}
    except Exception as e:
        return {"rows_inserted": 0, "worker_id": worker_id, "error": str(e)}


def _mysql_insert_worker(df: pd.DataFrame, cfg: Dict, table: str, worker_id: int) -> Dict[str, Any]:
    conn = pymysql.connect(
        host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
        user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
        local_infile=True,
    )
    try:
        cursor = conn.cursor()
        fields_str = ", ".join(df.columns.tolist())
        placeholders = ", ".join(["%s"] * len(df.columns))
        sql = f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders})"
        values = [tuple(row) for row in df.values]
        cursor.executemany(sql, values)
        conn.commit()
        return {"rows_inserted": len(values), "worker_id": worker_id, "error": None}
    finally:
        conn.close()


def _postgres_insert_worker(df: pd.DataFrame, cfg: Dict, table: str, worker_id: int) -> Dict[str, Any]:
    conn = psycopg2.connect(
        host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
        user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
    )
    try:
        cursor = conn.cursor()
        fields_str = ", ".join(df.columns.tolist())
        placeholders = ", ".join(["%s"] * len(df.columns))
        sql = f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders})"
        values = [tuple(row) for row in df.values]
        cursor.executemany(sql, values)
        conn.commit()
        return {"rows_inserted": len(values), "worker_id": worker_id, "error": None}
    finally:
        conn.close()


def _duckdb_insert_worker(df: pd.DataFrame, cfg: Dict, table: str, worker_id: int) -> Dict[str, Any]:
    db_path = cfg.get("db_path", ":memory:")
    conn = duckdb.connect(db_path, read_only=False)
    try:
        conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
        return {"rows_inserted": len(df), "worker_id": worker_id, "error": None}
    finally:
        conn.close()


def _clickhouse_insert_worker(df: pd.DataFrame, cfg: Dict, table: str, worker_id: int) -> Dict[str, Any]:
    client = clickhouse_driver.Client(
        host=cfg.get("host", "localhost"), port=int(cfg.get("port", 9000)),
        user=cfg.get("user", "default"), password=cfg.get("password", ""),
        database=cfg.get("database", "default"),
    )
    try:
        records = df.to_dict("records")
        client.execute(f"INSERT INTO {table}", records)
        return {"rows_inserted": len(records), "worker_id": worker_id, "error": None}
    finally:
        client.disconnect()


class ParallelBulkEngine:
    """
    Parallel bulk import engine using multiprocessing.
    Each worker process handles a chunk of data independently.
    """

    def __init__(self, max_workers: int = None):
        self.max_workers = max_workers or max(1, os.cpu_count() - 1)

    def import_parallel(
        self,
        df: pd.DataFrame,
        target_conn_data: Dict[str, Any],
        table: str,
        target_fields: List[str],
        source_fields: List[str],
        chunk_size: int = 10000,
    ) -> Dict[str, Any]:
        """
        Split DataFrame into chunks and process in parallel using multiprocessing.
        Returns: {"total_inserted": N, "workers_used": N, "errors": []}
        """
        if df.empty:
            return {"total_inserted": 0, "workers_used": 0, "errors": []}

        # Apply field mapping in main process before splitting
        if source_fields and target_fields:
            df = df[source_fields].copy()
            df.columns = target_fields

        # Split into chunks
        chunks = [df.iloc[i:i + chunk_size] for i in range(0, len(df), chunk_size)]

        # Prepare worker arguments (DataFrame must be picklable - use to_dict)
        worker_args = []
        for i, chunk in enumerate(chunks):
            chunk_dicts = chunk.to_dict("records")
            worker_args.append((chunk_dicts, target_conn_data, table, target_fields, [], i))

        results = []
        errors = []

        # Use ProcessPoolExecutor for true parallelism
        with ProcessPoolExecutor(max_workers=min(self.max_workers, len(chunks))) as executor:
            futures = {
                executor.submit(_worker_insert_from_dicts, wa): wa[-1]
                for wa in worker_args
            }
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=300)
                    results.append(result)
                    if result.get("error"):
                        errors.append(result["error"])
                except Exception as e:
                    errors.append(str(e))

        total_inserted = sum(r.get("rows_inserted", 0) for r in results)

        return {
            "total_inserted": total_inserted,
            "workers_used": len(chunks),
            "errors": errors,
            "per_worker": results,
        }


def _worker_insert_from_dicts(args: Tuple) -> Dict[str, Any]:
    """
    Worker that receives list of dicts instead of DataFrame (better pickle support).
    """
    chunk_dicts, target_conn_data, table, target_fields, _, worker_id = args
    target_type = target_conn_data["type"]
    cfg = target_conn_data["config"]

    try:
        if not chunk_dicts:
            return {"rows_inserted": 0, "worker_id": worker_id, "error": None}

        df = pd.DataFrame(chunk_dicts)
        if target_fields:
            df = df[target_fields]
        df = df.where(pd.notnull(df), None)

        if target_type == "mysql":
            return _mysql_insert_worker(df, cfg, table, worker_id)
        elif target_type == "postgresql":
            return _postgres_insert_worker(df, cfg, table, worker_id)
        elif target_type == "duckdb":
            return _duckdb_insert_worker(df, cfg, table, worker_id)
        elif target_type == "clickhouse":
            return _clickhouse_insert_worker(df, cfg, table, worker_id)
        else:
            return {"rows_inserted": 0, "worker_id": worker_id, "error": f"Unsupported: {target_type}"}
    except Exception as e:
        return {"rows_inserted": 0, "worker_id": worker_id, "error": str(e)}
