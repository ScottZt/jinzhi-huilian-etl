"""文件读写节点 — 读取和写入 CSV/Excel/JSON/Parquet 文件。"""
import logging
import os
import pandas as pd
from pathlib import Path
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class FileReadNode(BaseNode):
    node_type = "file_read"
    display_name = "读取文件"
    category = "数据接入"
    params_schema = {
        "file_path": {
            "type": "text",
            "label": "文件路径",
            "default": "",
            "placeholder": "D:/data/file.csv 或相对路径"
        },
        "file_type": {
            "type": "select",
            "label": "文件类型",
            "options": ["auto", "csv", "excel", "json", "parquet", "txt"],
            "default": "auto",
            "placeholder": "文件格式（auto=根据扩展名自动识别）"
        },
        "encoding": {
            "type": "text",
            "label": "编码",
            "default": "utf-8",
            "placeholder": "文件编码（utf-8/gbk/gb2312等）"
        },
        "sep": {
            "type": "text",
            "label": "分隔符",
            "default": ",",
            "placeholder": "CSV 文件的分隔符"
        },
        "sheet_name": {
            "type": "text",
            "label": "工作表名",
            "default": "",
            "placeholder": "Excel 文件的工作表名（留空=第一个）"
        },
        "json_orient": {
            "type": "select",
            "label": "JSON 格式",
            "options": ["records", "columns", "index", "values", "split"],
            "default": "records",
            "placeholder": "JSON 文件的格式"
        },
        "skip_rows": {
            "type": "number",
            "label": "跳过行数",
            "default": 0,
            "placeholder": "从文件开头跳过多少行"
        },
        "max_rows": {
            "type": "number",
            "label": "最大行数",
            "default": 0,
            "placeholder": "最多读取多少行（0=不限）"
        },
    }

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> pd.DataFrame:
        """
        读取文件并返回 DataFrame。
        """
        file_path = params.get("file_path", "").strip()
        file_type = params.get("file_type", "auto").strip()
        encoding = params.get("encoding", "utf-8").strip()
        skip_rows = int(params.get("skip_rows", 0))
        max_rows = int(params.get("max_rows", 0))

        if not file_path:
            logger.error("FileReadNode: 文件路径不能为空")
            return pd.DataFrame({"error": ["文件路径不能为空"]})

        # 解析路径（支持环境变量）
        file_path = os.path.expandvars(os.path.expanduser(file_path))

        if not os.path.exists(file_path):
            logger.error("FileReadNode: 文件不存在: %s", file_path)
            return pd.DataFrame({"error": [f"文件不存在: {file_path}"]})

        # 自动检测文件类型
        if file_type == "auto":
            ext = Path(file_path).suffix.lower()
            type_map = {
                ".csv": "csv",
                ".tsv": "csv",
                ".txt": "txt",
                ".xlsx": "excel",
                ".xls": "excel",
                ".json": "json",
                ".parquet": "parquet",
                ".pq": "parquet",
            }
            file_type = type_map.get(ext, "csv")

        try:
            sep = params.get("sep", ",").strip()

            if file_type == "csv" or file_type == "txt":
                result = pd.read_csv(
                    file_path,
                    sep=sep,
                    encoding=encoding,
                    skiprows=skip_rows if skip_rows > 0 else None,
                    nrows=max_rows if max_rows > 0 else None,
                )

            elif file_type == "excel":
                sheet_name = params.get("sheet_name", "").strip() or 0
                result = pd.read_excel(
                    file_path,
                    sheet_name=sheet_name,
                    skiprows=skip_rows if skip_rows > 0 else None,
                    nrows=max_rows if max_rows > 0 else None,
                )

            elif file_type == "json":
                json_orient = params.get("json_orient", "records").strip()
                if json_orient == "records":
                    result = pd.read_json(file_path, orient="records", encoding=encoding)
                else:
                    result = pd.read_json(file_path, orient=json_orient, encoding=encoding)
                if max_rows > 0:
                    result = result.head(max_rows)

            elif file_type == "parquet":
                result = pd.read_parquet(file_path)
                if skip_rows > 0 or max_rows > 0:
                    end = (skip_rows + max_rows) if max_rows > 0 else None
                    result = result.iloc[skip_rows:end]

            else:
                logger.error("FileReadNode: 不支持的文件类型 '%s'", file_type)
                return pd.DataFrame({"error": [f"不支持的文件类型: {file_type}"]})

            logger.info("FileReadNode: 读取文件成功，%d 行 x %d 列", len(result), len(result.columns))
            return result

        except Exception as e:
            logger.error("FileReadNode: 读取文件失败: %s", e)
            return pd.DataFrame({"error": [str(e)]})


class FileWriteNode(BaseNode):
    node_type = "file_write"
    display_name = "写入文件"
    category = "数据输出"
    params_schema = {
        "file_path": {
            "type": "text",
            "label": "文件路径",
            "default": "",
            "placeholder": "D:/data/output.csv 或相对路径"
        },
        "file_type": {
            "type": "select",
            "label": "文件类型",
            "options": ["auto", "csv", "excel", "json", "parquet"],
            "default": "auto",
            "placeholder": "文件格式（auto=根据扩展名自动识别）"
        },
        "encoding": {
            "type": "text",
            "label": "编码",
            "default": "utf-8",
            "placeholder": "文件编码（utf-8/gbk/gb2312等）"
        },
        "sep": {
            "type": "text",
            "label": "分隔符",
            "default": ",",
            "placeholder": "CSV 文件的分隔符"
        },
        "index": {
            "type": "checkbox",
            "label": "写入索引",
            "default": False
        },
        "sheet_name": {
            "type": "text",
            "label": "工作表名",
            "default": "Sheet1",
            "placeholder": "Excel 文件的工作表名"
        },
        "json_orient": {
            "type": "select",
            "label": "JSON 格式",
            "options": ["records", "columns", "index", "values", "split"],
            "default": "records",
            "placeholder": "JSON 文件的格式"
        },
        "create_dir": {
            "type": "checkbox",
            "label": "自动创建目录",
            "default": True
        },
    }

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> pd.DataFrame:
        """
        将 DataFrame 写入文件。
        """
        file_path = params.get("file_path", "").strip()
        file_type = params.get("file_type", "auto").strip()
        encoding = params.get("encoding", "utf-8").strip()
        create_dir = params.get("create_dir", True)

        if not file_path:
            logger.error("FileWriteNode: 文件路径不能为空")
            return self._add_status(df, "error", "文件路径不能为空")

        # 解析路径
        file_path = os.path.expandvars(os.path.expanduser(file_path))

        # 自动创建目录
        if create_dir:
            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    logger.info("FileWriteNode: 创建目录: %s", dir_path)
                except Exception as e:
                    logger.error("FileWriteNode: 创建目录失败: %s", e)
                    return self._add_status(df, "error", f"创建目录失败: {e}")

        # 自动检测文件类型
        if file_type == "auto":
            ext = Path(file_path).suffix.lower()
            type_map = {
                ".csv": "csv",
                ".tsv": "csv",
                ".xlsx": "excel",
                ".xls": "excel",
                ".json": "json",
                ".parquet": "parquet",
                ".pq": "parquet",
            }
            file_type = type_map.get(ext, "csv")

        try:
            index = params.get("index", False)
            sep = params.get("sep", ",").strip()

            if file_type == "csv":
                df.to_csv(file_path, index=index, sep=sep, encoding=encoding)

            elif file_type == "excel":
                sheet_name = params.get("sheet_name", "Sheet1").strip()
                df.to_excel(file_path, index=index, sheet_name=sheet_name)

            elif file_type == "json":
                json_orient = params.get("json_orient", "records").strip()
                df.to_json(file_path, orient=json_orient, force_ascii=False, indent=2)

            elif file_type == "parquet":
                df.to_parquet(file_path, index=index)

            else:
                logger.error("FileWriteNode: 不支持的文件类型 '%s'", file_type)
                return self._add_status(df, "error", f"不支持的文件类型: {file_type}")

            logger.info("FileWriteNode: 写入文件成功: %s (%d 行)", file_path, len(df))
            return self._add_status(df, "status", f"写入成功: {file_path}")

        except Exception as e:
            logger.error("FileWriteNode: 写入文件失败: %s", e)
            return self._add_status(df, "error", str(e))

    def _add_status(self, df: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
        """添加状态列。"""
        if df.empty:
            return pd.DataFrame({column: [value]})
        df[column] = value
        return df
