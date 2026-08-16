"""因子写入节点 — 将计算后的因子数据写入 DuckDB 因子库。

存储方案：宽表设计，每个因子一张表
表结构：code, dt, factor_value, [params], created_at
主键：(code, dt)

写入模式：
- upsert: 存在则更新，不存在则插入（默认）
- append: 仅追加，存在则跳过
- replace: 清空后重写
"""
import os
import json
from typing import Optional
import pandas as pd
from app.core.workflow_engine import BaseNode
from app.nodes.target_write import _validate_identifier


class FactorWriteNode(BaseNode):
    node_type = "factor_write"
    display_name = "写入因子库"
    category = "因子库"
    params_schema = {
        "factor_id": {
            "type": "text",
            "label": "因子ID（如 ma_5）",
            "default": "",
        },
        "db_path": {
            "type": "text",
            "label": "DuckDB 路径",
            "default": "D:/data/factor_data.duckdb",
        },
        "write_mode": {
            "type": "select",
            "label": "写入模式",
            "options": ["upsert", "append", "replace"],
            "default": "upsert",
        },
        "code_column": {
            "type": "text",
            "label": "代码字段",
            "default": "code",
        },
        "date_column": {
            "type": "text",
            "label": "日期字段",
            "default": "dt",
        },
        "value_column": {
            "type": "text",
            "label": "值字段",
            "default": "factor_value",
        },
        "register_meta": {
            "type": "checkbox",
            "label": "注册因子元数据",
            "default": True,
        },
        "factor_name": {
            "type": "text",
            "label": "因子名称（可选）",
            "default": "",
        },
        "compute_type": {
            "type": "select",
            "label": "计算类型（元数据）",
            "options": [
                "ma", "ema", "macd", "rsi", "boll",
                "return", "volatility", "atr", "bias", "other"
            ],
            "default": "other",
        },
        "params_json_meta": {
            "type": "text",
            "label": "参数JSON（元数据）",
            "default": "{}",
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df

        import duckdb

        factor_id = (params.get("factor_id") or "").strip()
        db_path = params.get("db_path", "D:/data/factor_data.duckdb")
        write_mode = params.get("write_mode", "upsert")
        code_col = params.get("code_column", "code")
        date_col = params.get("date_column", "dt")
        value_col = params.get("value_column", "factor_value")
        register_meta = params.get("register_meta", True)

        if not factor_id:
            raise ValueError("factor_id 不能为空")

        # 校验标识符（防止SQL注入）
        factor_id = _validate_identifier(factor_id, "factor_id")
        table_name = f"factor_{factor_id}"

        # 检查必要字段
        for col in [code_col, date_col, value_col]:
            if col not in df.columns:
                raise ValueError(f"数据中缺少必要字段: {col}")

        # 准备写入数据：标准化为 code, dt, factor_value
        write_df = pd.DataFrame({
            "code": df[code_col].astype(str),
            "dt": df[date_col].astype(str),
            "factor_value": df[value_col].astype(float) if df[value_col].notna().any() else None,
        })

        # 过滤掉 factor_value 为空的行
        write_df = write_df.dropna(subset=["factor_value"])

        if write_df.empty:
            return pd.DataFrame([{
                "_factor_write_status": "success",
                "_factor_write_count": 0,
                "_factor_id": factor_id,
                "_factor_table": table_name,
                "_message": "无有效数据写入",
            }])

        # 确保父目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # 连接 DuckDB 并写入
        conn = duckdb.connect(db_path, read_only=False)
        try:
            # 创建表（如果不存在）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS {table} (
                    code VARCHAR,
                    dt VARCHAR,
                    factor_value DOUBLE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (code, dt)
                )
            """.format(table=table_name))

            if write_mode == "replace":
                conn.execute("DELETE FROM {table}".format(table=table_name))
                conn.execute("INSERT INTO {table} (code, dt, factor_value) SELECT * FROM write_df".format(
                    table=table_name))
            elif write_mode == "append":
                # 先删除已存在的，再插入（模拟 UPSERT 但不覆盖）
                conn.execute("INSERT INTO {table} (code, dt, factor_value) SELECT * FROM write_df".format(
                    table=table_name))
            else:  # upsert
                # DuckDB 支持 INSERT OR REPLACE
                conn.execute("""
                    INSERT OR REPLACE INTO {table} (code, dt, factor_value, created_at)
                    SELECT code, dt, factor_value, CURRENT_TIMESTAMP FROM write_df
                """.format(table=table_name))

            total = len(write_df)

            # 注册元数据
            if register_meta:
                self._register_factor_meta(conn, factor_id, params)

        except Exception as e:
            raise RuntimeError(f"因子写入失败: {e}")
        finally:
            conn.close()

        return pd.DataFrame([{
            "_factor_write_status": "success",
            "_factor_write_count": total,
            "_factor_id": factor_id,
            "_factor_table": table_name,
            "_factor_db": db_path,
        }])

    def _register_factor_meta(self, conn, factor_id: str, params: dict):
        """注册因子元数据到 factor_registry 表。"""
        try:
            # 创建 factor_registry 表（如果不存在）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS factor_registry (
                    factor_id VARCHAR PRIMARY KEY,
                    factor_name VARCHAR,
                    factor_type VARCHAR,
                    category VARCHAR,
                    description VARCHAR,
                    compute_type VARCHAR,
                    params_json VARCHAR,
                    source_column VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            compute_type = params.get("compute_type", "other")
            source_col = params.get("source_column", "close")
            params_json = params.get("params_json_meta", params.get("params_json", "{}"))
            factor_name = params.get("factor_name", "")

            # 如果没有提供 factor_name，根据 compute_type 生成
            if not factor_name:
                name_map = {
                    "ma": "移动平均",
                    "ema": "指数移动平均",
                    "macd": "MACD",
                    "rsi": "RSI 相对强弱",
                    "boll": "布林带",
                    "return": "收益率",
                    "volatility": "波动率",
                    "atr": "ATR 真实波幅",
                    "bias": "BIAS 乖离率",
                    "other": "自定义因子",
                }
                factor_name = name_map.get(compute_type, compute_type)
                try:
                    p = json.loads(params_json) if isinstance(params_json, str) else params_json
                    factor_name = f"{factor_name}({source_col}, {params_json})"
                except Exception:
                    factor_name = f"{factor_name}({source_col})"

            # 插入或更新
            conn.execute("""
                INSERT OR REPLACE INTO factor_registry
                (factor_id, factor_name, factor_type, compute_type, params_json, source_column, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, [factor_id, factor_name, "L2", compute_type, params_json, source_col])
        except Exception as e:
            # 元数据注册失败不影响主流程
            print(f"[factor_write] 元数据注册失败: {e}")
