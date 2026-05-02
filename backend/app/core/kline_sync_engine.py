"""K线数据增量同步引擎。"""
import hashlib
import time
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

import pandas as pd

from app.persistence import sqlite_repo
from app.core.transform_engine import get_transform_engine
from app.core.workflow_engine import get_workflow_engine
from app.adapters.source_adapters.kline_base import KLineSourceAdapter, normalize_config

_KLINE_INTERVALS = {"1min", "5min", "15min", "30min", "60min", "D"}


class SyncResult:
    def __init__(self):
        self.rows_read = 0
        self.rows_written = 0
        self.rows_skipped = 0
        self.errors: List[str] = []
        self.duration = 0.0


class KLineSyncEngine:
    """K线增量同步引擎 — 拉源 → 差集 → 工作流 → 字段映射 → 写入目标。"""

    def __init__(self):
        self._adapters: Dict[str, KLineSourceAdapter] = {}

    def sync(self, task_id: str) -> Dict[str, Any]:
        """执行一次完整的K线同步。"""
        result = SyncResult()
        t0 = time.time()

        task = sqlite_repo.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        source_conn = sqlite_repo.get_connection(task["source_connection_id"])
        target_conn = sqlite_repo.get_connection(task["target_connection_id"])
        config = task["config_json"]

        if not source_conn:
            return {"error": "Source connection not found"}
        if not target_conn:
            return {"error": "Target connection not found"}

        codes = config.get("codes", [])
        if not codes:
            return {"error": "No stock codes configured"}

        start_time, end_time = self._resolve_time_range(config)
        interval = config.get("interval", "1min")
        session_only = config.get("session_only", True)
        batch_size = config.get("batch_size", 5000)

        # Step 1: 拉取源数据
        df = self._fetch_source(source_conn, codes, start_time, end_time, interval)
        result.rows_read = len(df)

        if df.empty:
            result.duration = time.time() - t0
            return self._build_result(result)

        # Session filter
        if session_only and interval == "1min":
            df = self._filter_session_minutes(df)

        # Step 2: 查询目标已有 keys
        existing_keys = self._fetch_existing_keys(
            target_conn, task["target_table"], codes, start_time, end_time
        )
        result.rows_skipped = len(existing_keys)

        # Step 3: 计算差集
        if existing_keys:
            df["_key"] = df["code"] + "|" + df["dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
            df = df[~df["_key"].isin(existing_keys)].drop(columns=["_key"])
        result.rows_read = len(df)

        if df.empty:
            result.duration = time.time() - t0
            return self._build_result(result)

        # Step 4: 执行工作流
        workflow_id = config.get("workflow_id")
        if workflow_id:
            wf_data = sqlite_repo.get_workflow(workflow_id)
            if wf_data and wf_data.get("workflow_json"):
                engine = get_workflow_engine()
                engine.register_all()
                df, wf_timings = engine.execute(wf_data["workflow_json"], df)
                result.wf_timings = wf_timings

        if df.empty:
            result.duration = time.time() - t0
            return self._build_result(result)

        # Step 5: 字段映射
        field_mappings = config.get("field_mappings", [])
        if field_mappings:
            transform_engine = get_transform_engine()
            df = transform_engine.apply_field_mappings(df, field_mappings)

        # Step 6: Upsert 到目标表
        target_fields = list(df.columns)
        written = self._insert_to_target(
            df, target_conn, task["target_table"], batch_size, config.get("on_duplicate", "ignore")
        )
        result.rows_written = written

        result.duration = time.time() - t0
        return self._build_result(result)

    def _build_result(self, result: SyncResult) -> Dict[str, Any]:
        return {
            "rows_read": result.rows_read,
            "rows_written": result.rows_written,
            "rows_skipped": result.rows_skipped,
            "duration": round(result.duration, 2),
            "errors": result.errors,
        }

    def _resolve_time_range(self, config: dict) -> tuple:
        """解析时间范围配置。"""
        time_mode = config.get("time_mode", "lookback")
        if time_mode == "custom":
            start_str = config.get("start_date")
            end_str = config.get("end_date")
            if start_str and end_str:
                return pd.to_datetime(start_str), pd.to_datetime(end_str)
        lookback = int(config.get("lookback_days", 10))
        end_time = datetime.now()
        start_time = end_time - timedelta(days=lookback)
        return start_time, end_time

    def _fetch_source(self, conn_data: dict, codes: list, start, end, interval: str) -> pd.DataFrame:
        """从数据源拉取 K 线数据。"""
        conn_type = conn_data["type"]
        config = conn_data.get("config", {})

        if conn_type == "tdx":
            from app.adapters.source_adapters.tdx_adapter import HttpAdapter
            adapter = HttpAdapter()
        elif conn_type == "akshare":
            from app.adapters.source_adapters.akshare_adapter import HttpAdapter
            adapter = HttpAdapter()
        elif conn_type == "tushare":
            from app.adapters.source_adapters.tushare_adapter import HttpAdapter
            adapter = HttpAdapter()
        else:
            raise ValueError(f"Unsupported source type: {conn_type}")

        return adapter.fetch_kline(config, codes, start, end, interval)

    def _fetch_existing_keys(self, target_conn: dict, table: str,
                             codes: list, start: datetime, end: datetime) -> set:
        """查询目标表中已存在的 (code, dt) 键。"""
        try:
            target_type = target_conn["type"]
            cfg = target_conn["config"]

            if target_type == "duckdb":
                import duckdb
                db_path = cfg.get("db_path", ":memory:")
                conn = duckdb.connect(db_path, read_only=False)
                try:
                    df = conn.execute(
                        f"SELECT stock_code, trade_time FROM {table} "
                        f"WHERE trade_time >= ? AND trade_time <= ?",
                        [start, end]
                    ).fetchdf()
                except Exception:
                    df = pd.DataFrame()
                conn.close()
            elif target_type == "postgresql":
                import psycopg2
                conn = psycopg2.connect(
                    host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
                    user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
                )
                df = pd.read_sql(
                    f"SELECT stock_code, trade_time FROM {table} "
                    f"WHERE trade_time >= %s AND trade_time <= %s",
                    conn, params=[start, end]
                )
                conn.close()
            elif target_type == "mysql":
                import pymysql
                conn = pymysql.connect(
                    host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
                    user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
                )
                df = pd.read_sql(
                    f"SELECT stock_code, trade_time FROM {table} "
                    f"WHERE trade_time >= %s AND trade_time <= %s",
                    conn, params=[start, end]
                )
                conn.close()
            elif target_type == "clickhouse":
                import clickhouse_driver
                client = clickhouse_driver.Client(
                    host=cfg.get("host", "localhost"), port=int(cfg.get("port", 9000)),
                    user=cfg.get("user", "default"), password=cfg.get("password", ""),
                    database=cfg.get("database", "default"),
                )
                rows = client.execute(
                    f"SELECT stock_code, trade_time FROM {table} "
                    f"WHERE trade_time >= %s AND trade_time <= %s",
                    [start, end]
                )
                if rows:
                    df = pd.DataFrame(rows, columns=["stock_code", "trade_time"])
                else:
                    df = pd.DataFrame()
            else:
                return set()
        except Exception:
            return set()

        if df.empty:
            return set()

        keys = set()
        if "stock_code" in df.columns and "trade_time" in df.columns:
            for _, row in df.iterrows():
                keys.add(f"{row['stock_code']}|{pd.to_datetime(row['trade_time']).strftime('%Y-%m-%d %H:%M:%S')}")
        return keys

    def _insert_to_target(self, df: pd.DataFrame, target_conn: dict,
                          table: str, batch_size: int, on_duplicate: str) -> int:
        """批量写入目标表。"""
        if df.empty:
            return 0
        df = df.where(pd.notnull(df), None)
        target_type = target_conn["type"]
        cfg = target_conn["config"]
        columns = df.columns.tolist()
        placeholders = ", ".join(["%s"] * len(columns))
        total = 0

        if target_type == "duckdb":
            import duckdb
            db_path = cfg.get("db_path", ":memory:")
            conn = duckdb.connect(db_path, read_only=False)
            try:
                conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
                total = len(df)
            except Exception as e:
                print(f"DuckDB insert error: {e}")
            conn.close()

        elif target_type == "postgresql":
            import psycopg2
            conn = psycopg2.connect(
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
                user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
            )
            cursor = conn.cursor()
            fields_str = ", ".join(columns)
            if on_duplicate == "ignore":
                conflict_cols = ", ".join(columns[:2])
                sql = (f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders}) "
                       f"ON CONFLICT ({conflict_cols}) DO NOTHING")
            else:
                updates = ", ".join([f"{c} = EXCLUDED.{c}" for c in columns[2:]])
                conflict_cols = ", ".join(columns[:2])
                sql = (f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders}) "
                       f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {updates}")
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i + batch_size]
                values = [tuple(row) for row in batch.values]
                try:
                    cursor.executemany(sql, values)
                    conn.commit()
                    total += len(values)
                except Exception as e:
                    print(f"PostgreSQL insert error: {e}")
                    conn.rollback()
            cursor.close()
            conn.close()

        elif target_type == "mysql":
            import pymysql
            conn = pymysql.connect(
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
                user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
            )
            cursor = conn.cursor()
            fields_str = ", ".join(columns)
            sql = f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders})"
            if on_duplicate == "ignore":
                sql += " ON DUPLICATE KEY UPDATE id=id"
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i + batch_size]
                values = [tuple(row) for row in batch.values]
                try:
                    cursor.executemany(sql, values)
                    conn.commit()
                    total += len(values)
                except Exception as e:
                    print(f"MySQL insert error: {e}")
                    conn.rollback()
            cursor.close()
            conn.close()

        elif target_type == "clickhouse":
            import clickhouse_driver
            client = clickhouse_driver.Client(
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 9000)),
                user=cfg.get("user", "default"), password=cfg.get("password", ""),
                database=cfg.get("database", "default"),
            )
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i + batch_size]
                records = batch.to_dict("records")
                try:
                    client.execute(f"INSERT INTO {table}", records)
                    total += len(records)
                except Exception as e:
                    print(f"ClickHouse insert error: {e}")
            client.disconnect()

        return total

    @staticmethod
    def _filter_session_minutes(df: pd.DataFrame) -> pd.DataFrame:
        """过滤非交易时段数据。"""
        if df.empty or "dt" not in df.columns:
            return df
        work = df.copy()
        work["dt"] = pd.to_datetime(work["dt"], errors="coerce")
        work = work.dropna(subset=["dt"])
        minutes = work["dt"].dt.hour * 60 + work["dt"].dt.minute
        mask = ((minutes >= 9 * 60 + 30) & (minutes <= 11 * 60 + 30)) | \
               ((minutes >= 13 * 60) & (minutes <= 15 * 60))
        return work.loc[mask].reset_index(drop=True)
