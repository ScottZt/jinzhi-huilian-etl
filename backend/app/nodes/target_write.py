"""目标写入节点 — 将处理后的 DataFrame 写入目标数据库。"""
import json
import logging
import re
import time
from typing import List, Optional

import pandas as pd

from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)

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
        "connection_id": {
            "type": "text",
            "label": "目标连接ID(从连接管理选择)",
            "default": "",
        },
        "manual_config": {
            "type": "checkbox",
            "label": "手动配置(高级模式)",
            "default": False,
        },
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

        from app.persistence import sqlite_repo

        connection_id = (params.get("connection_id") or "").strip()
        manual_config = params.get("manual_config", False)

        # 优先从「连接管理」读取已配置的连接
        if connection_id and not manual_config:
            conn_record = sqlite_repo.get_connection(connection_id)
            if not conn_record:
                raise RuntimeError(f"连接不存在: {connection_id}，请到连接管理中检查")
            target_type = conn_record.get("type", "duckdb")
            cfg = dict(conn_record.get("config", {}))
        else:
            # 向后兼容：手动配置模式
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
            # 检查表是否存在
            tables = conn.execute("SHOW TABLES").fetchall()
            table_exists = any(t[0] == table for t in tables)

            # 检测是否有适合做主键的列（K线数据通常是 code + dt）
            pk_cols = self._detect_pk_columns(df)

            if not table_exists:
                # 首次建表
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df LIMIT 0")
                # DuckDB 不支持 ALTER TABLE ADD PRIMARY KEY，建表时也无法加主键
                # 所以所有表都是"无主键模式"，依赖手动过滤去重
                logger.info("DuckDB: 已创建表 %s (无主键模式，依赖手动过滤去重)", table)
            else:
                # 表已存在，检查是否有重复数据（首次运行时）
                if pk_cols and on_duplicate == "ignore":
                    # 检查是否有重复
                    pk_list = ", ".join(pk_cols)
                    dup_count = conn.execute(f"""
                        SELECT COUNT(*) FROM (
                            SELECT {pk_list}, COUNT(*) as cnt
                            FROM {table}
                            GROUP BY {pk_list}
                            HAVING cnt > 1
                        )
                    """).fetchone()[0]
                    if dup_count > 0:
                        logger.warning("DuckDB: 表 %s 存在 %d 组重复数据，将自动清理", table, dup_count)
                        self._deduplicate_table(conn, table, pk_cols)

            # 写入数据
            if not pk_cols:
                # 无法检测主键列，直接插入
                conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
                total = len(df)
            elif on_duplicate == "ignore" and table_exists:
                # 无主键但要求去重：手动过滤已存在的记录
                df_to_write = self._filter_existing_records(conn, table, df, pk_cols)
                if not df_to_write.empty:
                    conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df_to_write")
                total = len(df_to_write)
            elif on_duplicate == "update" and table_exists:
                # 更新模式：删除已存在的，再插入新的
                self._delete_existing_records(conn, table, df, pk_cols)
                if not df.empty:
                    conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
                total = len(df)
            else:
                # 新表或直接插入
                conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
                total = len(df)

            logger.info("DuckDB: 写入 %s 表 %d 行 (主键列: %s, 重复策略: %s)", table, total, pk_cols, on_duplicate)
        except Exception as e:
            raise RuntimeError(f"DuckDB 写入失败: {e}")
        finally:
            conn.close()

        return pd.DataFrame([{
            "_write_status": "success",
            "_write_count": total,
            "_write_target": f"duckdb://{db_path}#{table}",
        }])

    def _deduplicate_table(self, conn, table: str, pk_cols: list):
        """清理表中的重复数据，保留每组主键的第一条记录。"""
        if not pk_cols:
            return

        pk_list = ", ".join(pk_cols)
        try:
            # 用 ROW_NUMBER() 标记重复行，删除非第一条
            conn.execute(f"""
                DELETE FROM {table}
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM {table} GROUP BY {pk_list}
                )
            """)
            logger.info("DuckDB: 已清理表 %s 的重复数据", table)
        except Exception as e:
            # DuckDB 某些版本不支持 rowid，用临时表方式
            logger.warning("DuckDB: rowid 方式去重失败 - %s，尝试临时表方式", e)
            conn.execute(f"CREATE TEMP TABLE _dedup_tmp AS SELECT DISTINCT * FROM {table}")
            conn.execute(f"DELETE FROM {table}")
            conn.execute(f"INSERT INTO {table} SELECT * FROM _dedup_tmp")
            conn.execute("DROP TABLE _dedup_tmp")

    def _filter_existing_records(self, conn, table: str, df: pd.DataFrame, pk_cols: list) -> pd.DataFrame:
        """过滤掉表中已存在的记录（无主键时的去重方案）。"""
        if not pk_cols:
            return df

        try:
            # 查询表中已有的主键组合
            pk_list = ", ".join(pk_cols)
            existing = conn.execute(f"SELECT DISTINCT {pk_list} FROM {table}").fetchdf()

            if existing.empty:
                return df

            # 从 df 中过滤掉已存在的组合
            df_to_write = df.merge(existing, on=pk_cols, how="left", indicator=True)
            df_to_write = df_to_write[df_to_write["_merge"] == "left_only"].drop(columns=["_merge"])

            filtered_count = len(df) - len(df_to_write)
            if filtered_count > 0:
                logger.info("DuckDB: 过滤掉 %d 条已存在记录，实际写入 %d 条", filtered_count, len(df_to_write))

            return df_to_write
        except Exception as e:
            logger.warning("DuckDB: 过滤已存在记录失败 - %s，写入全部 %d 条", e, len(df))
            return df

    def _delete_existing_records(self, conn, table: str, df: pd.DataFrame, pk_cols: list):
        """删除表中已存在的记录（用于 update 模式）。"""
        if not pk_cols or df.empty:
            return

        try:
            # 创建临时表存储要更新的 key
            conn.execute("CREATE TEMP TABLE _update_keys AS SELECT DISTINCT code, dt FROM df")
            # 删除表中已有的记录
            pk_list = ", ".join(pk_cols)
            conn.execute(f"DELETE FROM {table} WHERE ({pk_list}) IN (SELECT {pk_list} FROM _update_keys)")
            conn.execute("DROP TABLE _update_keys")
            logger.info("DuckDB: 已删除表 %s 中待更新的记录", table)
        except Exception as e:
            logger.warning("DuckDB: 删除已存在记录失败 - %s", e)

    def _detect_pk_columns(self, df: pd.DataFrame) -> list:
        """检测 DataFrame 中适合作为主键的列。

        K线数据通常是 (code, dt) 组合唯一，如果这两列都存在就返回它们。
        否则返回空列表（无主键模式）。
        """
        cols_lower = {c.lower(): c for c in df.columns}

        # 查找代码列
        code_col = None
        for candidate in ["code", "symbol", "股票代码", "交易对"]:
            if candidate in cols_lower:
                code_col = cols_lower[candidate]
                break

        # 查找日期列
        dt_col = None
        for candidate in ["dt", "date", "trade_date", "日期", "时间"]:
            if candidate in cols_lower:
                dt_col = cols_lower[candidate]
                break

        if code_col and dt_col:
            return [code_col, dt_col]
        return []

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
