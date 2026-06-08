"""目标写入节点 — 将处理后的 DataFrame 写入目标数据库。"""
import json
import re
import time
from typing import List, Optional

import pandas as pd

from app.core.workflow_engine import BaseNode

# Whitelist pattern for SQL identifiers (table/column names)
_IDENT_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _validate_identifier(name: str, label: str = "identifier") -> str:
    """Validate a SQL identifier against a safe whitelist. Raises on violation."""
    if not _IDENT_RE.match(name):
        raise ValueError(
            f"{label} '{name}' contains invalid characters. "
            f"Only letters, digits, and underscores are allowed, starting with a letter or underscore."
        )
    return name


def _validate_identifiers(names: List[str], label: str = "identifier") -> List[str]:
    """Validate multiple SQL identifiers."""
    return [_validate_identifier(n, label) for n in names]


class TargetWriteNode(BaseNode):
    node_type = "target_write"
    display_name = "写入目标数据库"
    category = "数据输出"
    params_schema = {
        "target_type": {
            "type": "select",
            "label": "目标类型",
            "options": ["duckdb", "mysql", "postgresql", "clickhouse"],
            "default": "duckdb",
        },
        "target_config": {
            "type": "text",
            "label": "目标连接配置(JSON)",
            "default": '{"db_path": "D:/data/demo.db"}',
        },
        "target_table": {
            "type": "text",
            "label": "目标表名",
            "default": "stock_minute_kline",
        },
        "batch_size": {
            "type": "number",
            "label": "批次大小",
            "default": 5000,
        },
        "on_duplicate": {
            "type": "select",
            "label": "重复策略",
            "options": ["ignore", "update", "error"],
            "default": "ignore",
        },
        "columns": {
            "type": "text",
            "label": "写入字段(逗号分隔,留空=全部)",
            "default": "",
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df

        target_type = params.get("target_type", "duckdb")
        target_config_str = params.get("target_config", "{}")
        try:
            cfg = json.loads(target_config_str)
        except Exception:
            cfg = {}
        target_table = params.get("target_table", "stock_kline")
        batch_size = int(params.get("batch_size", 5000))
        on_duplicate = params.get("on_duplicate", "ignore")

        # 选择写入列
        cols_str = (params.get("columns") or "").strip()
        if cols_str:
            write_cols = [c.strip() for c in cols_str.split(",") if c.strip()]
            write_cols = _validate_identifiers(write_cols, "column")
            available = [c for c in write_cols if c in df.columns]
            df = df[available].copy()

        # Validate table name
        target_table = _validate_identifier(target_table, "target_table")

        # NaN -> None
        df = df.where(pd.notnull(df), None)
        columns = df.columns.tolist()

        if target_type == "duckdb":
            return self._write_duckdb(df, cfg, target_table, batch_size, on_duplicate)
        elif target_type == "mysql":
            return self._write_mysql(df, cfg, target_table, batch_size, on_duplicate, columns)
        elif target_type == "postgresql":
            return self._write_pg(df, cfg, target_table, batch_size, on_duplicate, columns)
        elif target_type == "clickhouse":
            return self._write_ch(df, cfg, target_table, batch_size, columns)
        else:
            raise ValueError(f"不支持的目标类型: {target_type}")

    def _write_duckdb(self, df: pd.DataFrame, cfg: dict, table: str, batch_size: int, on_duplicate: str) -> pd.DataFrame:
        import duckdb
        import os

        db_path = cfg.get("db_path", "")
        if not db_path:
            raise RuntimeError("db_path 为空")

        # 确保父目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = duckdb.connect(db_path, read_only=False)
        try:
            # 表不存在时自动创建
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df LIMIT 0")
            conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
            total = len(df)
        except Exception as e:
            raise RuntimeError(f"DuckDB 写入失败: {e}")
        finally:
            conn.close()

        return pd.DataFrame([{
            "_write_status": "success",
            "_write_count": total,
            "_write_target": f"duckdb://{db_path}#{table}",
        }])

    def _write_mysql(self, df: pd.DataFrame, cfg: dict, table: str, batch_size: int, on_duplicate: str) -> pd.DataFrame:
        import pymysql

        conn = pymysql.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 3306)),
            user=cfg.get("user"),
            password=cfg.get("password"),
            database=cfg.get("database"),
        )
        cursor = conn.cursor()
        fields_str = ", ".join(columns := df.columns.tolist())
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders})"
        if on_duplicate == "ignore":
            sql += " ON DUPLICATE KEY UPDATE id=id"

        total = 0
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i + batch_size]
            values = [tuple(row) for row in batch.values]
            try:
                cursor.executemany(sql, values)
                conn.commit()
                total += len(values)
            except Exception as e:
                conn.rollback()
                raise RuntimeError(f"MySQL 写入失败: {e}")

        cursor.close()
        conn.close()
        return pd.DataFrame([{
            "_write_status": "success",
            "_write_count": total,
            "_write_target": f"mysql://{cfg.get('host')}#{table}",
        }])

    def _write_pg(self, df: pd.DataFrame, cfg: dict, table: str, batch_size: int, on_duplicate: str) -> pd.DataFrame:
        import psycopg2

        conn = psycopg2.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 5432)),
            user=cfg.get("user"),
            password=cfg.get("password"),
            database=cfg.get("database"),
        )
        cursor = conn.cursor()
        columns = df.columns.tolist()
        fields_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))

        if on_duplicate == "ignore":
            conflict_cols = ", ".join(columns[:2])
            sql = (f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders}) "
                   f"ON CONFLICT ({conflict_cols}) DO NOTHING")
        else:
            conflict_cols = ", ".join(columns[:2])
            updates = ", ".join([f"{c} = EXCLUDED.{c}" for c in columns[2:]])
            sql = (f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders}) "
                   f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {updates}")

        total = 0
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i + batch_size]
            values = [tuple(row) for row in batch.values]
            try:
                cursor.executemany(sql, values)
                conn.commit()
                total += len(values)
            except Exception as e:
                conn.rollback()
                raise RuntimeError(f"PostgreSQL 写入失败: {e}")

        cursor.close()
        conn.close()
        return pd.DataFrame([{
            "_write_status": "success",
            "_write_count": total,
            "_write_target": f"postgresql://{cfg.get('host')}#{table}",
        }])

    def _write_ch(self, df: pd.DataFrame, cfg: dict, table: str, batch_size: int) -> pd.DataFrame:
        import clickhouse_driver

        client = clickhouse_driver.Client(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 9000)),
            user=cfg.get("user", "default"),
            password=cfg.get("password", ""),
            database=cfg.get("database", "default"),
        )
        total = 0
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i + batch_size]
            records = batch.to_dict("records")
            try:
                client.execute(f"INSERT INTO {table}", records)
                total += len(records)
            except Exception as e:
                raise RuntimeError(f"ClickHouse 写入失败: {e}")
        client.disconnect()
        return pd.DataFrame([{
            "_write_status": "success",
            "_write_count": total,
            "_write_target": f"clickhouse://{cfg.get('host')}#{table}",
        }])
