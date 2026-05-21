"""数据范围控制节点 — 去重、分区、分页等优化控制。"""
from typing import List

import pandas as pd

from app.core.workflow_engine import BaseNode


class DedupNode(BaseNode):
    """去重节点 — 按指定字段去重，支持增量模式。"""
    node_type = "dedup"
    display_name = "数据去重"
    category = "数据优化"
    params_schema = {
        "mode": {
            "type": "select",
            "label": "去重模式",
            "options": ["keep_last", "keep_first", "check_existing"],
            "default": "keep_last",
        },
        "columns": {
            "type": "text",
            "label": "去重字段(逗号分隔)",
            "default": "code,dt",
        },
        "target_type": {
            "type": "select",
            "label": "目标类型(仅check_existing需要)",
            "options": ["duckdb", "mysql", "postgresql", "clickhouse", ""],
            "default": "",
        },
        "target_config": {
            "type": "text",
            "label": "目标连接配置(JSON)",
            "default": '{"db_path": ""}',
        },
        "target_table": {
            "type": "text",
            "label": "目标表名",
            "default": "",
        },
        "keep_existing_rows": {
            "type": "text",
            "label": "保留已有行数(0=不限制)",
            "default": "0",
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df

        mode = params.get("mode", "keep_last")
        cols_str = params.get("columns", "code,dt")
        dedup_cols = [c.strip() for c in cols_str.split(",") if c.strip() and c.strip() in df.columns]
        if not dedup_cols:
            return df

        if mode == "check_existing":
            return self._check_existing(df, dedup_cols, params)

        keep = params.get("keep", "last") if mode == "keep_first" else "last"
        result = df.drop_duplicates(subset=dedup_cols, keep=keep)
        removed = len(df) - len(result)
        result = result.copy()
        result.attrs["dedup_removed"] = removed
        return result

    def _check_existing(self, df: pd.DataFrame, dedup_cols: List[str], params: dict) -> pd.DataFrame:
        """从目标数据库查询已有键，排除重复数据。"""
        import json

        target_type = params.get("target_type", "duckdb")
        target_table = params.get("target_table", "")
        if not target_table:
            return df.drop_duplicates(subset=dedup_cols, keep="last")

        target_config_str = params.get("target_config", "{}")
        try:
            cfg = json.loads(target_config_str)
        except Exception:
            cfg = {}

        # 获取已有键
        existing_keys = self._fetch_existing(target_type, cfg, target_table, dedup_cols)
        if not existing_keys:
            return df

        # 构建组合键
        key_col = dedup_cols[0]
        for col in dedup_cols[1:]:
            if col in df.columns:
                df = df.copy()
                df["__dedup_key"] = df[key_col].astype(str) + "|" + df[col].astype(str)
                key_col = "__dedup_key"
            else:
                df = df.copy()
                df["__dedup_key"] = df[key_col].astype(str)

        mask = df["__dedup_key"].isin(existing_keys)
        df = df[~mask].copy()
        if "__dedup_key" in df.columns:
            df = df.drop(columns=["__dedup_key"])
        return df

    def _fetch_existing(self, target_type: str, cfg: dict, table: str, cols: List[str]) -> set:
        """从目标库查询已有数据的主键集合。"""
        if len(cols) >= 2:
            key_col = cols[0]
            time_col = cols[1]
        else:
            key_col = cols[0]
            time_col = cols[0]

        if target_type == "duckdb":
            import duckdb

            db_path = cfg.get("db_path", "")
            if not db_path:
                raise RuntimeError("db_path 为空")
            try:
                conn = duckdb.connect(db_path, read_only=True)
                # 限制读取行数，避免全表扫描
                max_rows = int(cfg.get("dedup_max_rows", 100000))
                rows = conn.execute(
                    f"SELECT {key_col}, {time_col} FROM {table} LIMIT {max_rows}"
                ).fetchall()
                conn.close()
                keys = set()
                for row in rows:
                    k0 = str(row[0]) if row[0] is not None else ""
                    k1 = str(pd.to_datetime(row[1])) if len(row) > 1 and row[1] is not None else ""
                    keys.add(f"{k0}|{k1}")
                return keys
            except Exception:
                return set()

        return set()


class TimeWindowNode(BaseNode):
    """时间窗口节点 — 按时间窗口分批处理数据，避免一次性加载全量数据。"""
    node_type = "time_window"
    display_name = "时间窗口分批"
    category = "数据优化"
    params_schema = {
        "window_size": {
            "type": "number",
            "label": "窗口大小(天)",
            "default": 7,
        },
        "window_step": {
            "type": "number",
            "label": "窗口步长(天)",
            "default": 7,
        },
        "time_column": {
            "type": "text",
            "label": "时间字段",
            "default": "dt",
        },
        "sort_first": {
            "type": "checkbox",
            "label": "先按时间排序",
            "default": True,
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df

        time_col = params.get("time_column", "dt")
        if time_col not in df.columns:
            return df

        window_size = int(params.get("window_size", 7))
        sort_first = params.get("sort_first", True)

        df = df.copy()
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        if sort_first:
            df = df.sort_values(time_col).reset_index(drop=True)

        return df
