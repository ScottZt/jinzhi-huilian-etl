"""数据格式转换节点 — JSON/CSV 解析与转换。"""
import logging
import json
import pandas as pd
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class DataConvertNode(BaseNode):
    node_type = "data_convert"
    display_name = "格式转换"
    category = "数据处理"
    params_schema = {
        "operation": {
            "type": "select",
            "label": "操作类型",
            "options": ["json_to_df", "df_to_json", "csv_to_df", "df_to_csv", "flatten", "explode"],
            "default": "json_to_df",
            "placeholder": "选择转换操作"
        },
        "source_column": {
            "type": "text",
            "label": "源字段",
            "default": "",
            "placeholder": "包含 JSON/CSV 数据的列名"
        },
        "target_column": {
            "type": "text",
            "label": "输出字段",
            "default": "",
            "placeholder": "转换结果保存的列名（留空=替换输入数据）"
        },
        "json_path": {
            "type": "text",
            "label": "JSON 路径",
            "default": "",
            "placeholder": "JSON 中提取数据的路径（如 data.items）"
        },
        "sep": {
            "type": "text",
            "label": "分隔符",
            "default": ",",
            "placeholder": "CSV 解析时使用的分隔符"
        },
        "flatten_separator": {
            "type": "text",
            "label": "嵌套分隔符",
            "default": "_",
            "placeholder": "展平嵌套 JSON 时列名的分隔符"
        },
        "max_rows": {
            "type": "number",
            "label": "最大行数",
            "default": 0,
            "placeholder": "最多转换的行数（0=不限）"
        },
    }

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> pd.DataFrame:
        """
        执行数据格式转换。
        """
        if df.empty:
            return df

        operation = params.get("operation", "json_to_df")
        max_rows = int(params.get("max_rows", 0))

        if operation == "json_to_df":
            return self._json_to_df(df, params, max_rows)
        elif operation == "df_to_json":
            return self._df_to_json(df, params)
        elif operation == "csv_to_df":
            return self._csv_to_df(df, params, max_rows)
        elif operation == "df_to_csv":
            return self._df_to_csv(df, params)
        elif operation == "flatten":
            return self._flatten_json(df, params)
        elif operation == "explode":
            return self._explode_list(df, params)
        else:
            logger.warning("DataConvertNode: 未知操作 '%s'", operation)
            return df

    def _json_to_df(self, df: pd.DataFrame, params: dict, max_rows: int) -> pd.DataFrame:
        """将 JSON 字符串列转换为 DataFrame。"""
        source_column = params.get("source_column", "").strip()
        json_path = params.get("json_path", "").strip()

        if not source_column or source_column not in df.columns:
            logger.warning("DataConvertNode: 源列 '%s' 不存在", source_column)
            return df

        try:
            # 获取 JSON 字符串
            json_str = str(df[source_column].iloc[0]) if not df.empty else ""
            data = json.loads(json_str)

            # 如果指定了路径，提取嵌套数据
            if json_path:
                for key in json_path.split("."):
                    if isinstance(data, dict) and key in data:
                        data = data[key]
                    else:
                        logger.warning("DataConvertNode: JSON 路径 '%s' 不存在", json_path)
                        return df

            # 转换为 DataFrame
            if isinstance(data, list):
                result = pd.DataFrame(data)
            elif isinstance(data, dict):
                result = pd.DataFrame([data])
            else:
                logger.warning("DataConvertNode: JSON 数据不是列表或字典")
                return df

            # 限制行数
            if max_rows > 0:
                result = result.head(max_rows)

            logger.info("DataConvertNode: JSON 转 DataFrame 完成，%d 行", len(result))
            return result

        except Exception as e:
            logger.error("DataConvertNode: JSON 解析失败: %s", e)
            return df

    def _df_to_json(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        """将 DataFrame 转换为 JSON 字符串。"""
        target_column = params.get("target_column", "json").strip() or "json"

        try:
            json_str = df.to_json(orient="records", force_ascii=False, indent=2)

            # 如果指定了目标列，添加到该列
            if target_column:
                result = pd.DataFrame({target_column: [json_str]})
                return result
            else:
                return pd.DataFrame({"json": [json_str]})

        except Exception as e:
            logger.error("DataConvertNode: DataFrame 转 JSON 失败: %s", e)
            return df

    def _csv_to_df(self, df: pd.DataFrame, params: dict, max_rows: int) -> pd.DataFrame:
        """将 CSV 字符串列转换为 DataFrame。"""
        source_column = params.get("source_column", "").strip()
        sep = params.get("sep", ",").strip()

        if not source_column or source_column not in df.columns:
            logger.warning("DataConvertNode: 源列 '%s' 不存在", source_column)
            return df

        try:
            # 获取 CSV 字符串
            csv_str = str(df[source_column].iloc[0]) if not df.empty else ""

            # 使用 pandas 解析 CSV
            from io import StringIO
            result = pd.read_csv(StringIO(csv_str), sep=sep)

            # 限制行数
            if max_rows > 0:
                result = result.head(max_rows)

            logger.info("DataConvertNode: CSV 转 DataFrame 完成，%d 行", len(result))
            return result

        except Exception as e:
            logger.error("DataConvertNode: CSV 解析失败: %s", e)
            return df

    def _df_to_csv(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        """将 DataFrame 转换为 CSV 字符串。"""
        target_column = params.get("target_column", "csv").strip() or "csv"
        sep = params.get("sep", ",").strip()

        try:
            csv_str = df.to_csv(index=False, sep=sep)
            result = pd.DataFrame({target_column: [csv_str]})
            return result

        except Exception as e:
            logger.error("DataConvertNode: DataFrame 转 CSV 失败: %s", e)
            return df

    def _flatten_json(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        """展平嵌套的 JSON 列。"""
        source_column = params.get("source_column", "").strip()
        sep = params.get("flatten_separator", "_").strip()

        if not source_column or source_column not in df.columns:
            logger.warning("DataConvertNode: 源列 '%s' 不存在", source_column)
            return df

        try:
            # 解析 JSON 列
            json_col = df[source_column].apply(lambda x: json.loads(str(x)) if pd.notna(x) else {})

            # 使用 pandas 的 json_normalize 展平
            result = pd.json_normalize(json_col, sep=sep)

            # 合并其他列
            other_cols = [c for c in df.columns if c != source_column]
            if other_cols:
                result = pd.concat([df[other_cols].reset_index(drop=True), result], axis=1)

            logger.info("DataConvertNode: JSON 展平完成，%d 列", len(result.columns))
            return result

        except Exception as e:
            logger.error("DataConvertNode: JSON 展平失败: %s", e)
            return df

    def _explode_list(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        """将列表列展开为多行。"""
        source_column = params.get("source_column", "").strip()

        if not source_column or source_column not in df.columns:
            logger.warning("DataConvertNode: 源列 '%s' 不存在", source_column)
            return df

        try:
            # 尝试解析 JSON 列表
            df_copy = df.copy()
            df_copy[source_column] = df_copy[source_column].apply(
                lambda x: json.loads(str(x)) if isinstance(x, str) and x.startswith("[") else x
            )

            # 展开列表
            result = df_copy.explode(source_column, ignore_index=True)

            logger.info("DataConvertNode: 列表展开完成，%d 行", len(result))
            return result

        except Exception as e:
            logger.error("DataConvertNode: 列表展开失败: %s", e)
            return df
