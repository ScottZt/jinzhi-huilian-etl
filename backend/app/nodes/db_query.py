"""数据库查询节点 — 执行 SQL 查询或为上游数据增强进度信息。

两种工作模式：

1. source 模式（默认，独立数据源）：
   忽略上游 df，直接执行 SQL 返回新 DataFrame。
   典型用途：从任意数据库读取数据进入工作流。

2. enrich 模式（进度增强）：
   接收上游 df（通常来自 stock_list 节点），为其中每只股票查询目标表的最新进度 dt。
   典型用途：与 stock_list + source_fetch(since_last) 串联，实现增量数据拉取。
   如果目标表不存在或某只股票没有历史记录，使用 default_date 作为兜底。

支持数据库：DuckDB / MySQL / PostgreSQL。
可以走「连接管理」里已配置的连接（推荐），也可以手动填写 JSON 配置。
"""
import json
import logging
import traceback
from typing import Optional

import pandas as pd

from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class DbQueryNode(BaseNode):
    node_type = "db_query"
    display_name = "数据库查询"
    category = "数据接入"
    params_schema = {
        "mode": {
            "type": "select",
            "label": "工作模式",
            "options": [
                {"value": "source", "label": "数据源模式（执行 SQL 返回新数据）"},
                {"value": "enrich", "label": "增强模式（为上游数据附加进度信息）"},
            ],
            "default": "source",
        },
        # ---------- 通用：连接配置 ----------
        "connection_id": {
            "type": "text",
            "label": "数据库连接ID(从连接管理选择)",
            "default": "",
        },
        "manual_config": {
            "type": "checkbox",
            "label": "手动配置(高级模式)",
            "default": False,
        },
        "db_type": {
            "type": "select",
            "label": "数据库类型",
            "options": ["duckdb", "mysql", "postgresql"],
            "default": "duckdb",
        },
        "db_config": {
            "type": "text",
            "label": "连接配置(JSON)",
            "default": '{"db_path": "D:/data/demo.db"}',
        },
        # ---------- source 模式：SQL 查询 ----------
        "sql": {
            "type": "textarea",
            "label": "查询 SQL",
            "default": "SELECT * FROM your_table LIMIT 100",
        },
        "default_rows": {
            "type": "text",
            "label": "默认数据(SQL 为空/失败时返回，JSON 数组)",
            "default": "",
        },
        # ---------- enrich 模式：进度增强 ----------
        "target_table": {
            "type": "text",
            "label": "进度查询表(已写入的目标表)",
            "default": "kline_hfq",
        },
        "date_column": {
            "type": "text",
            "label": "进度日期列名",
            "default": "dt",
        },
        "code_column": {
            "type": "text",
            "label": "上游代码列名",
            "default": "code",
        },
        "default_date": {
            "type": "text",
            "label": "默认起始日期(表不存在/无历史时)",
            "default": "2016-01-01",
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        """根据 mode 选择工作模式。"""
        mode = (params.get("mode") or "source").strip()

        if mode == "enrich":
            return self._process_enrich(df, params)
        else:
            return self._process_source(df, params)

    # ==================================================================
    # source 模式：执行 SQL 返回新数据（忽略上游 df）
    # ==================================================================
    def _process_source(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        sql = (params.get("sql") or "").strip()

        conn_cfg = self._resolve_connection(params)
        db_type = conn_cfg["db_type"]
        cfg = conn_cfg["cfg"]

        if not sql:
            return self._fallback(params)

        try:
            if db_type == "duckdb":
                return self._query_duckdb(cfg, sql)
            elif db_type == "mysql":
                return self._query_mysql(cfg, sql)
            elif db_type == "postgresql":
                return self._query_pg(cfg, sql)
            else:
                raise ValueError(f"不支持的数据库类型: {db_type}")
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("DbQueryNode: SQL 执行失败 - %s\n%s", e, tb)
            return self._fallback(params, error=str(e))

    # ==================================================================
    # enrich 模式：为上游 df 附加进度信息
    # ==================================================================
    def _process_enrich(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        """为上游 df 中的每只股票查目标表的最新 dt，作为新列附加到 df 上。

        输出 df 在原列基础上增加/覆盖 `dt` 列（日期类型），
        供下游 source_fetch(since_last) 使用。
        """
        code_col = (params.get("code_column") or "code").strip()
        date_col = (params.get("date_column") or "dt").strip()
        target_table = (params.get("target_table") or "").strip()
        default_date = (params.get("default_date") or "2016-01-01").strip()

        if df.empty:
            logger.warning("DbQueryNode(enrich): 上游 df 为空，无需增强")
            return df

        if code_col not in df.columns:
            raise RuntimeError(
                f"DbQueryNode(enrich): 上游 df 缺少 '{code_col}' 列，"
                f"当前列: {list(df.columns)}"
            )

        if not target_table:
            raise RuntimeError("DbQueryNode(enrich): target_table 未配置")

        conn_cfg = self._resolve_connection(params)
        db_type = conn_cfg["db_type"]
        cfg = conn_cfg["cfg"]

        # 提取上游所有 code（去重，查询完再 join 回去）
        codes = df[code_col].dropna().astype(str).unique().tolist()
        if not codes:
            logger.warning("DbQueryNode(enrich): 上游无有效 code")
            df[date_col] = pd.to_datetime(default_date)
            return df

        # 查询每只股票的最新 dt
        progress = self._query_progress(cfg, db_type, target_table, date_col, code_col, codes)

        # join 回原 df
        if progress.empty:
            # 表不存在或查询失败 → 全部用默认日期
            logger.warning("DbQueryNode(enrich): 进度查询为空，全部使用默认日期 %s", default_date)
            df = df.copy()
            df[date_col] = pd.to_datetime(default_date)
            return df

        # 把 progress 的列名统一为 code_col / date_col
        progress = progress.rename(
            columns={progress.columns[0]: code_col, progress.columns[1]: date_col}
        )
        progress[code_col] = progress[code_col].astype(str)
        progress[date_col] = pd.to_datetime(progress[date_col], errors="coerce")

        # merge：left join 保留上游全部行；没有进度的股票填充 default_date
        df = df.copy()
        df[code_col] = df[code_col].astype(str)
        merged = df.merge(progress, on=code_col, how="left")
        merged[date_col] = merged[date_col].fillna(pd.to_datetime(default_date))

        # 日志：统计有多少股票是"首次"（使用默认日期）
        first_time = (merged[date_col] == pd.to_datetime(default_date)).sum()
        logger.info(
            "DbQueryNode(enrich): %d 只股票，其中 %d 只首次（用默认日期），%d 只增量",
            len(codes), first_time, len(codes) - first_time,
        )

        return merged

    def _query_progress(
        self, cfg: dict, db_type: str, table: str, date_col: str, code_col: str, codes: list
    ) -> pd.DataFrame:
        """查询目标表里每个 code 的最新 dt。表不存在时返回空 DataFrame。"""
        # 构造参数化的 IN 列表（DuckDB/PG 用 $1, MySQL 用 %s）
        if db_type == "mysql":
            placeholder = "%s"
        else:
            placeholder = "?"

        in_list = ",".join([placeholder] * len(codes))
        sql = (
            f"SELECT {code_col}, MAX({date_col}) AS {date_col} "
            f"FROM {table} WHERE {code_col} IN ({in_list}) GROUP BY {code_col}"
        )

        try:
            if db_type == "duckdb":
                return self._query_duckdb_with_params(cfg, sql, codes)
            elif db_type == "mysql":
                return self._query_mysql_with_params(cfg, sql, codes)
            elif db_type == "postgresql":
                return self._query_pg_with_params(cfg, sql, codes)
            else:
                raise ValueError(f"不支持的数据库类型: {db_type}")
        except Exception as e:
            # 表不存在、列名错误等都返回空，外层用 default_date 兜底
            logger.warning("DbQueryNode(enrich): 进度查询失败 - %s", e)
            return pd.DataFrame()

    def _query_duckdb_with_params(self, cfg: dict, sql: str, params: list) -> pd.DataFrame:
        import duckdb
        import os

        db_path = cfg.get("db_path", "")
        if not db_path:
            raise RuntimeError("DuckDB db_path 为空")
        if not os.path.exists(db_path):
            # 文件不存在 = 首次运行，返回空，外层用 default_date
            return pd.DataFrame()

        conn = duckdb.connect(db_path, read_only=True)
        try:
            result = conn.execute(sql, params).fetchdf()
        finally:
            conn.close()
        return result

    def _query_mysql_with_params(self, cfg: dict, sql: str, params: list) -> pd.DataFrame:
        import pymysql

        conn = pymysql.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 3306)),
            user=cfg.get("user"),
            password=cfg.get("password"),
            database=cfg.get("database"),
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return pd.DataFrame(rows)
        except Exception:
            return pd.DataFrame()
        finally:
            conn.close()

    def _query_pg_with_params(self, cfg: dict, sql: str, params: list) -> pd.DataFrame:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 5432)),
            user=cfg.get("user"),
            password=cfg.get("password"),
            database=cfg.get("database"),
        )
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return pd.DataFrame(rows)
        except Exception:
            return pd.DataFrame()
        finally:
            conn.close()

    # ==================================================================
    # 共用工具
    # ==================================================================
    def _resolve_connection(self, params: dict) -> dict:
        """从「连接管理」或手动配置中解析数据库连接信息。"""
        connection_id = (params.get("connection_id") or "").strip()
        manual_config = params.get("manual_config", False)

        if connection_id and not manual_config:
            from app.persistence import sqlite_repo
            conn_record = sqlite_repo.get_connection(connection_id)
            if not conn_record:
                raise RuntimeError(f"连接不存在: {connection_id}，请到连接管理中检查")
            return {
                "db_type": conn_record.get("type", "duckdb"),
                "cfg": dict(conn_record.get("config", {})),
            }

        db_type = params.get("db_type", "duckdb")
        cfg_str = params.get("db_config", "{}")
        try:
            cfg = json.loads(cfg_str) if isinstance(cfg_str, str) else cfg_str
        except Exception:
            cfg = {}
        return {"db_type": db_type, "cfg": cfg}

    def _query_duckdb(self, cfg: dict, sql: str) -> pd.DataFrame:
        import duckdb
        import os

        db_path = cfg.get("db_path", "")
        if not db_path:
            raise RuntimeError("DuckDB db_path 为空")
        if not os.path.exists(db_path):
            raise RuntimeError(f"DuckDB 文件不存在: {db_path}")

        conn = duckdb.connect(db_path, read_only=True)
        try:
            result = conn.execute(sql).fetchdf()
        finally:
            conn.close()

        logger.info("DbQueryNode(DuckDB): 查询返回 %d 行", len(result))
        return result

    def _query_mysql(self, cfg: dict, sql: str) -> pd.DataFrame:
        import pymysql

        conn = pymysql.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 3306)),
            user=cfg.get("user"),
            password=cfg.get("password"),
            database=cfg.get("database"),
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                result = pd.DataFrame(rows)
        finally:
            conn.close()

        logger.info("DbQueryNode(MySQL): 查询返回 %d 行", len(result))
        return result

    def _query_pg(self, cfg: dict, sql: str) -> pd.DataFrame:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 5432)),
            user=cfg.get("user"),
            password=cfg.get("password"),
            database=cfg.get("database"),
        )
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                result = pd.DataFrame(rows)
        finally:
            conn.close()

        logger.info("DbQueryNode(PostgreSQL): 查询返回 %d 行", len(result))
        return result

    def _fallback(self, params: dict, error: Optional[str] = None) -> pd.DataFrame:
        """source 模式下的兜底数据（SQL 为空或失败时）。"""
        default_rows_str = (params.get("default_rows") or "").strip()
        if default_rows_str:
            try:
                rows = json.loads(default_rows_str)
                if isinstance(rows, list) and rows:
                    df = pd.DataFrame(rows)
                    if error:
                        df["_fallback_reason"] = error
                    return df
            except Exception as e:
                logger.warning("DbQueryNode: default_rows 解析失败 - %s", e)

        if error:
            return pd.DataFrame([{"_error": error}])
        return pd.DataFrame()
