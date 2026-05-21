import pymysql
import psycopg2
import duckdb
import clickhouse_driver
from typing import Dict, Any, Tuple, Optional
from contextlib import contextmanager

from app.models.connection import ConnectionConfig, ConnectionType


class ConnectionManager:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._active_connections: Dict[str, Any] = {}
        return cls._instance

    def check_connection(self, conn_config: ConnectionConfig) -> Tuple[bool, str, Optional[Any]]:
        try:
            db_type = conn_config.type
            cfg = conn_config.config

            if db_type == ConnectionType.MYSQL:
                return self._check_mysql(cfg)
            elif db_type == ConnectionType.POSTGRESQL:
                return self._check_postgresql(cfg)
            elif db_type == ConnectionType.DUCKDB:
                return self._check_duckdb(cfg)
            elif db_type == ConnectionType.CLICKHOUSE:
                return self._check_clickhouse(cfg)
            elif db_type in (ConnectionType.CSV, ConnectionType.EXCEL, ConnectionType.JSON, ConnectionType.PARQUET):
                return self._check_file_connection(db_type, cfg)
            else:
                return False, f"Unsupported connection type: {db_type}", None
        except Exception as e:
            return False, str(e), None

    def _check_mysql(self, cfg: Dict[str, Any]) -> Tuple[bool, str, Any]:
        try:
            conn = pymysql.connect(
                host=cfg.get("host", "localhost"),
                port=int(cfg.get("port", 3306)),
                user=cfg.get("user"),
                password=cfg.get("password"),
                database=cfg.get("database"),
                connect_timeout=5,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            cursor.close()
            # 提取 MySQL 版本号
            ver = version.split("-")[0].strip() if version else version
            return True, f"已连接 MySQL ({ver})", conn
        except Exception as e:
            return False, str(e), None

    def _check_postgresql(self, cfg: Dict[str, Any]) -> Tuple[bool, str, Any]:
        try:
            conn = psycopg2.connect(
                host=cfg.get("host", "localhost"),
                port=int(cfg.get("port", 5432)),
                user=cfg.get("user"),
                password=cfg.get("password"),
                database=cfg.get("database"),
                connect_timeout=5,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.close()
            # 解析 PostgreSQL 版本信息
            parts = version.split(",")
            server_version = parts[0].replace("PostgreSQL ", "").strip() if parts else version
            return True, f"已连接 PostgreSQL ({server_version})", conn
        except Exception as e:
            return False, str(e), None

    def _check_duckdb(self, cfg: Dict[str, Any]) -> Tuple[bool, str, Any]:
        try:
            db_path = cfg.get("db_path", "")
            if not db_path:
                return False, "db_path 为空", None
            conn = duckdb.connect(db_path, read_only=False)
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.close()
            ver = version.split("-")[0].strip() if version else version
            return True, f"已连接 DuckDB ({ver})", conn
        except Exception as e:
            return False, str(e), None

    def _check_clickhouse(self, cfg: Dict[str, Any]) -> Tuple[bool, str, Any]:
        try:
            client = clickhouse_driver.Client(
                host=cfg.get("host", "localhost"),
                port=int(cfg.get("port", 9000)),
                user=cfg.get("user", "default"),
                password=cfg.get("password", ""),
                database=cfg.get("database", "default"),
                connect_timeout=5,
            )
            result = client.execute("SELECT version()")
            version = result[0][0]
            ver = version.split("-")[0].strip() if version else version
            return True, f"已连接 ClickHouse ({ver})", client
        except Exception as e:
            return False, str(e), None

    def _check_file_connection(self, db_type: ConnectionType, cfg: Dict[str, Any]) -> Tuple[bool, str, Any]:
        from pathlib import Path
        file_path = cfg.get("file_path") or cfg.get("dir_path")
        if not file_path:
            return False, "file_path is required", None
        path = Path(file_path)
        if db_type == ConnectionType.FOLDER_WATCH:
            if not path.exists():
                return False, f"目录不存在：{file_path}", None
            if not path.is_dir():
                return False, f"不是有效的目录：{file_path}", None
            return True, f"目录已存在：{file_path}", None
        else:
            if not path.exists():
                return False, f"文件不存在：{file_path}", None
            size = path.stat().st_size
            return True, f"文件已存在（{size:,} 字节）", None

    @contextmanager
    def get_connection(self, conn_config: ConnectionConfig):
        success, msg, conn = self.check_connection(conn_config)
        if not success:
            raise ConnectionError(f"Cannot connect: {msg}")
        try:
            yield conn
        finally:
            self._close_conn(conn)

    def _close_conn(self, conn: Any):
        try:
            if conn is not None:
                if hasattr(conn, 'close'):
                    conn.close()
        except Exception:
            pass

    def get_tables(self, conn_config: ConnectionConfig) -> list:
        # 按连接类型统一分发“列出表名”能力，供前端做目标表下拉。
        db_type = conn_config.type
        cfg = conn_config.config
        try:
            if db_type == ConnectionType.MYSQL:
                return self._mysql_tables(cfg)
            elif db_type == ConnectionType.POSTGRESQL:
                return self._postgresql_tables(cfg)
            elif db_type == ConnectionType.DUCKDB:
                return self._duckdb_tables(cfg)
            elif db_type == ConnectionType.CLICKHOUSE:
                return self._clickhouse_tables(cfg)
            return []
        except Exception as e:
            raise RuntimeError(f"Failed to list tables: {e}")

    def get_table_columns(self, conn_config: ConnectionConfig, table_name: str) -> list:
        # 按连接类型统一分发“读取表字段”能力，供字段映射目标字段候选使用。
        db_type = conn_config.type
        cfg = conn_config.config
        normalized_table = str(table_name or "").strip()
        if not normalized_table:
            return []
        try:
            if db_type == ConnectionType.MYSQL:
                return self._mysql_table_columns(cfg, normalized_table)
            elif db_type == ConnectionType.POSTGRESQL:
                return self._postgresql_table_columns(cfg, normalized_table)
            elif db_type == ConnectionType.DUCKDB:
                return self._duckdb_table_columns(cfg, normalized_table)
            elif db_type == ConnectionType.CLICKHOUSE:
                return self._clickhouse_table_columns(cfg, normalized_table)
            return []
        except Exception as e:
            raise RuntimeError(f"Failed to list columns for table '{normalized_table}': {e}")

    def _mysql_tables(self, cfg: Dict[str, Any]) -> list:
        with pymysql.connect(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
            user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
        ) as conn:
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            return [row[0] for row in cursor.fetchall()]

    def _postgresql_tables(self, cfg: Dict[str, Any]) -> list:
        conn = psycopg2.connect(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
            user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
        )
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return tables

    def _duckdb_tables(self, cfg: Dict[str, Any]) -> list:
        db_path = cfg.get("db_path", "")
        if not db_path:
            return []
        conn = duckdb.connect(db_path, read_only=False)
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables

    def _clickhouse_tables(self, cfg: Dict[str, Any]) -> list:
        client = clickhouse_driver.Client(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 9000)),
            user=cfg.get("user", "default"), password=cfg.get("password", ""),
            database=cfg.get("database", "default"),
        )
        result = client.execute(
            f"SHOW TABLES FROM {cfg.get('database', 'default')}"
        )
        return [row[0] for row in result]

    def _mysql_table_columns(self, cfg: Dict[str, Any], table_name: str) -> list:
        # 通过 information_schema + 参数化查询字段，避免拼接 SQL 标识符导致注入风险。
        with pymysql.connect(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
            user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
        ) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (cfg.get("database"), table_name),
            )
            return [row[0] for row in cursor.fetchall()]

    def _postgresql_table_columns(self, cfg: Dict[str, Any], table_name: str) -> list:
        # PostgreSQL 默认读取 public schema 下的字段顺序。
        conn = psycopg2.connect(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
            user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
        )
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        columns = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return columns

    def _duckdb_table_columns(self, cfg: Dict[str, Any], table_name: str) -> list:
        # DuckDB 通过 information_schema 查询，兼容本地文件库场景。
        db_path = cfg.get("db_path", "")
        if not db_path:
            return []
        conn = duckdb.connect(db_path, read_only=False)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = ?
            ORDER BY ordinal_position
            """,
            [table_name],
        )
        columns = [row[0] for row in cursor.fetchall()]
        conn.close()
        return columns

    def _clickhouse_table_columns(self, cfg: Dict[str, Any], table_name: str) -> list:
        # ClickHouse 从 system.columns 读取字段定义，按 position 返回原始顺序。
        db_name = cfg.get("database", "default")
        client = clickhouse_driver.Client(
            host=cfg.get("host", "localhost"), port=int(cfg.get("port", 9000)),
            user=cfg.get("user", "default"), password=cfg.get("password", ""),
            database=db_name,
        )
        result = client.execute(
            """
            SELECT name
            FROM system.columns
            WHERE database = %(database)s AND table = %(table)s
            ORDER BY position
            """,
            {"database": db_name, "table": table_name},
        )
        return [row[0] for row in result]

    def execute_ddl(self, conn_config: ConnectionConfig, ddl: str) -> Tuple[bool, str]:
        db_type = conn_config.type
        cfg = conn_config.config
        try:
            if db_type == ConnectionType.MYSQL:
                with pymysql.connect(
                    host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
                    user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
                ) as conn:
                    cursor = conn.cursor()
                    cursor.execute(ddl)
                    conn.commit()
                    return True, "DDL executed successfully"
            elif db_type == ConnectionType.POSTGRESQL:
                conn = psycopg2.connect(
                    host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)),
                    user=cfg.get("user"), password=cfg.get("password"), database=cfg.get("database"),
                )
                cursor = conn.cursor()
                cursor.execute(ddl)
                conn.commit()
                cursor.close()
                conn.close()
                return True, "DDL executed successfully"
            elif db_type == ConnectionType.DUCKDB:
                db_path = cfg.get("db_path", "")
                if not db_path:
                    return False, "db_path 为空"
                conn = duckdb.connect(db_path, read_only=False)
                conn.execute(ddl)
                conn.close()
                return True, "DDL executed successfully"
            elif db_type == ConnectionType.CLICKHOUSE:
                client = clickhouse_driver.Client(
                    host=cfg.get("host", "localhost"), port=int(cfg.get("port", 9000)),
                    user=cfg.get("user", "default"), password=cfg.get("password", ""),
                    database=cfg.get("database", "default"),
                )
                client.execute(ddl)
                return True, "DDL executed successfully"
            else:
                return False, f"DDL execution not supported for {db_type}"
        except Exception as e:
            return False, str(e)
