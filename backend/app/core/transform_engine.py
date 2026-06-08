"""
Data transformation engine supporting:
- Field mapping (rename, merge, split)
- Python expression transformations
- SQL expression transformations (via DuckDB)
- Built-in function library
- Custom Python functions
"""
import re
import math
import operator
from typing import Dict, Any, List, Callable, Optional, Union
from datetime import datetime, timedelta
from enum import Enum
import pandas as pd
import numpy as np


# ---- Built-in function registry ----

class BuiltinFuncs:
    """Library of built-in transformation functions."""

    # --- Date functions ---
    @staticmethod
    def parse_date(value, fmt: str = "%Y-%m-%d") -> Optional[str]:
        if pd.isna(value):
            return None
        try:
            if isinstance(value, datetime):
                return value.strftime(fmt)
            return pd.to_datetime(value).strftime(fmt)
        except Exception:
            return None

    @staticmethod
    def format_date(value, fmt: str = "%Y-%m-%d") -> Optional[str]:
        return BuiltinFuncs.parse_date(value, fmt)

    @staticmethod
    def add_days(value, days: int) -> Optional[str]:
        if pd.isna(value):
            return None
        try:
            d = pd.to_datetime(value)
            return (d + timedelta(days=days)).strftime("%Y-%m-%d")
        except Exception:
            return None

    @staticmethod
    def date_diff(start, end) -> Optional[float]:
        if pd.isna(start) or pd.isna(end):
            return None
        try:
            d1 = pd.to_datetime(start)
            d2 = pd.to_datetime(end)
            return (d2 - d1).days
        except Exception:
            return None

    @staticmethod
    def year(value) -> Optional[int]:
        if pd.isna(value):
            return None
        try:
            return pd.to_datetime(value).year
        except Exception:
            return None

    @staticmethod
    def month(value) -> Optional[int]:
        if pd.isna(value):
            return None
        try:
            return pd.to_datetime(value).month
        except Exception:
            return None

    @staticmethod
    def day(value) -> Optional[int]:
        if pd.isna(value):
            return None
        try:
            return pd.to_datetime(value).day
        except Exception:
            return None

    @staticmethod
    def weekday(value) -> Optional[int]:
        if pd.isna(value):
            return None
        try:
            return pd.to_datetime(value).weekday()
        except Exception:
            return None

    # --- String functions ---
    @staticmethod
    def upper(value) -> Optional[str]:
        if pd.isna(value):
            return None
        return str(value).upper()

    @staticmethod
    def lower(value) -> Optional[str]:
        if pd.isna(value):
            return None
        return str(value).lower()

    @staticmethod
    def trim(value) -> Optional[str]:
        if pd.isna(value):
            return None
        return str(value).strip()

    @staticmethod
    def substring(value, start: int, length: int = None) -> Optional[str]:
        if pd.isna(value):
            return None
        s = str(value)
        if length is None:
            return s[start:]
        return s[start:start + length]

    @staticmethod
    def replace(value, old: str, new: str) -> Optional[str]:
        if pd.isna(value):
            return None
        return str(value).replace(old, new)

    @staticmethod
    def concat(*args) -> str:
        return "".join(str(a) if not pd.isna(a) else "" for a in args)

    @staticmethod
    def split_col(value, sep: str = ",") -> List[str]:
        if pd.isna(value):
            return []
        return str(value).split(sep)

    @staticmethod
    def split_first(value, sep: str = ",") -> Optional[str]:
        parts = BuiltinFuncs.split_col(value, sep)
        return parts[0] if parts else None

    @staticmethod
    def split_last(value, sep: str = ",") -> Optional[str]:
        parts = BuiltinFuncs.split_col(value, sep)
        return parts[-1] if parts else None

    @staticmethod
    def length(value) -> Optional[int]:
        if pd.isna(value):
            return None
        return len(str(value))

    @staticmethod
    def contains(value, substr: str) -> bool:
        if pd.isna(value):
            return False
        return substr in str(value)

    # --- Numeric functions ---
    @staticmethod
    def round(value, decimals: int = 0) -> Optional[float]:
        if pd.isna(value):
            return None
        try:
            return round(float(value), decimals)
        except Exception:
            return None

    @staticmethod
    def abs(value) -> Optional[float]:
        if pd.isna(value):
            return None
        try:
            return abs(float(value))
        except Exception:
            return None

    @staticmethod
    def ceil(value) -> Optional[float]:
        if pd.isna(value):
            return None
        try:
            return math.ceil(float(value))
        except Exception:
            return None

    @staticmethod
    def floor(value) -> Optional[float]:
        if pd.isna(value):
            return None
        try:
            return math.floor(float(value))
        except Exception:
            return None

    @staticmethod
    def pow(value, exponent: float) -> Optional[float]:
        if pd.isna(value):
            return None
        try:
            return math.pow(float(value), exponent)
        except Exception:
            return None

    @staticmethod
    def multiply(value, factor: float) -> Optional[float]:
        if pd.isna(value):
            return None
        try:
            return float(value) * factor
        except Exception:
            return None

    @staticmethod
    def divide(value, divisor: float) -> Optional[float]:
        if pd.isna(value):
            return None
        try:
            return float(value) / divisor if divisor != 0 else None
        except Exception:
            return None

    # --- Conditional functions ---
    @staticmethod
    def if_null(value, default) -> Any:
        return default if pd.isna(value) else value

    @staticmethod
    def coalesce(*args) -> Any:
        for a in args:
            if not pd.isna(a):
                return a
        return None

    @staticmethod
    def if_then(condition, true_val, false_val) -> Any:
        return true_val if bool(condition) else false_val

    @staticmethod
    def case_when(mappings: List[Dict], default=None) -> Any:
        """mappings: [{"condition": "value > 0", "value": "positive"}]"""
        return default

    # --- Type conversion ---
    @staticmethod
    def to_int(value) -> Optional[int]:
        if pd.isna(value):
            return None
        try:
            return int(float(value))
        except Exception:
            return None

    @staticmethod
    def to_float(value) -> Optional[float]:
        if pd.isna(value):
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def to_str(value) -> Optional[str]:
        if pd.isna(value):
            return None
        return str(value)

from app.core.secure_exec import safe_eval as _safe_engine_eval


# ---- Transform rule types ----

class TransformType(str, Enum):
    RENAME = "rename"
    MAP = "map"
    EXPRESSION_PYTHON = "python"
    EXPRESSION_SQL = "sql"
    SPLIT = "split"
    MERGE = "merge"
    CUSTOM = "custom"


# ---- Transform engine ----

class TransformEngine:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._custom_funcs: Dict[str, Callable] = {}
            cls._instance._builtin_names = cls._build_builtin_names()
        return cls._instance

    @staticmethod
    def _build_builtin_names() -> Dict[str, Callable]:
        return {
            name: getattr(BuiltinFuncs, name)
            for name in dir(BuiltinFuncs)
            if not name.startswith("_") and callable(getattr(BuiltinFuncs, name))
        }

    def register_custom_func(self, name: str, func: Callable):
        """Register a custom Python transformation function."""
        self._custom_funcs[name] = func
        self._builtin_names[name] = func

    def unregister_custom_func(self, name: str):
        self._custom_funcs.pop(name, None)
        if name in self._builtin_names and name not in dir(BuiltinFuncs):
            del self._builtin_names[name]

    def transform(self, df: pd.DataFrame, rules: List[Dict]) -> pd.DataFrame:
        """
        Apply transformation rules to a DataFrame.
        Each rule: {
            "type": "map|python|sql|rename|split|merge|custom",
            "source_field": "...",
            "target_field": "...",
            "expression": "...",
            "func_name": "...",
            "func_args": [...],
        }
        """
        df = df.copy()
        for rule in rules:
            rule_type = rule.get("type", "map")
            if rule_type == TransformType.MAP or rule_type == "map":
                df = self._apply_map(df, rule)
            elif rule_type == TransformType.EXPRESSION_PYTHON or rule_type == "python":
                df = self._apply_python_expr(df, rule)
            elif rule_type == TransformType.EXPRESSION_SQL or rule_type == "sql":
                df = self._apply_sql_expr(df, rule)
            elif rule_type == TransformType.RENAME or rule_type == "rename":
                df = self._apply_rename(df, rule)
            elif rule_type == TransformType.SPLIT or rule_type == "split":
                df = self._apply_split(df, rule)
            elif rule_type == TransformType.MERGE or rule_type == "merge":
                df = self._apply_merge(df, rule)
            elif rule_type == TransformType.CUSTOM or rule_type == "custom":
                df = self._apply_custom(df, rule)
        return df

    def _apply_map(self, df: pd.DataFrame, rule: Dict) -> pd.DataFrame:
        """Simple field mapping."""
        src = rule.get("source_field")
        tgt = rule.get("target_field")
        if src and tgt and src in df.columns:
            df[tgt] = df[src]
        return df

    def _apply_rename(self, df: pd.DataFrame, rule: Dict) -> pd.DataFrame:
        src = rule.get("source_field")
        tgt = rule.get("target_field")
        if src in df.columns:
            df.rename(columns={src: tgt}, inplace=True)
        elif tgt:
            df[tgt] = None
        return df

    def _apply_python_expr(self, df: pd.DataFrame, rule: Dict) -> pd.DataFrame:
        """Apply a Python expression to create a new column."""
        expr = rule.get("expression", "")
        tgt = rule.get("target_field")
        if not tgt or not expr:
            return df

        # Build context with all columns and built-in functions
        ctx = {col: df[col] for col in df.columns}
        ctx.update(self._builtin_names)

        try:
            df[tgt] = df.eval(expr, engine="python")
        except Exception:
            # Fallback: try safe eval
            try:
                result = self._safe_eval(expr, df)
                df[tgt] = result
            except Exception as e:
                df[tgt] = None
        return df

    def _safe_eval(self, expr: str, df: pd.DataFrame) -> pd.Series:
        """Safe evaluation of Python expressions using column references."""
        ctx = {col: df[col].values for col in df.columns}
        ctx.update({name: func for name, func in self._builtin_names.items() if callable(func)})

        # Convert expr to use .values for numpy arrays
        safe_expr = expr
        for col in df.columns:
            safe_expr = re.sub(rf'\b{re.escape(col)}\b', f'{repr(col)}', safe_expr)

        result = []
        for i in range(len(df)):
            local_ctx = {col: ctx[col][i] for col in df.columns}
            local_ctx.update({name: func for name, func in self._builtin_names.items() if callable(func)})
            ok, val = _safe_engine_eval(safe_expr, {"__builtins__": {}}, local_ctx, label="transform_safe_eval")
            result.append(val if ok else None)
        return pd.Series(result, index=df.index)

    def _apply_sql_expr(self, df: pd.DataFrame, rule: Dict) -> pd.DataFrame:
        """Apply a SQL expression using DuckDB."""
        import duckdb
        expr = rule.get("expression", "")
        tgt = rule.get("target_field")
        if not tgt or not expr:
            return df

        try:
            conn = duckdb.connect(":memory:")
            conn.execute("CREATE TABLE src AS SELECT * FROM df")
            result = conn.execute(f"SELECT {expr} AS {tgt} FROM src").fetchdf()
            df[tgt] = result[tgt].values
            conn.close()
        except Exception:
            df[tgt] = None
        return df

    def _apply_split(self, df: pd.DataFrame, rule: Dict) -> pd.DataFrame:
        """Split a column into multiple target columns."""
        src = rule.get("source_field")
        sep = rule.get("separator", ",")
        targets = rule.get("target_fields", [])
        if not src or not targets or src not in df.columns:
            return df

        for i, tgt in enumerate(targets):
            df[tgt] = df[src].apply(
                lambda v: str(v).split(sep)[i] if pd.notna(v) and len(str(v).split(sep)) > i else None
            )
        return df

    def _apply_merge(self, df: pd.DataFrame, rule: Dict) -> pd.DataFrame:
        """Merge multiple source columns into one target."""
        sources = rule.get("source_fields", [])
        tgt = rule.get("target_field")
        sep = rule.get("separator", "")
        if not sources or not tgt:
            return df

        existing = [s for s in sources if s in df.columns]
        if existing:
            df[tgt] = df[existing].astype(str).agg(sep.join, axis=1)
        else:
            df[tgt] = None
        return df

    def _apply_custom(self, df: pd.DataFrame, rule: Dict) -> pd.DataFrame:
        """Apply a registered custom function."""
        func_name = rule.get("func_name")
        tgt = rule.get("target_field")
        args = rule.get("func_args", [])
        if not func_name or not tgt:
            return df

        func = self._builtin_names.get(func_name)
        if not func:
            func = self._custom_funcs.get(func_name)

        if func:
            try:
                src_args = [df.get(arg, arg if isinstance(arg, (int, float, str)) else None) for arg in args]
                if len(src_args) == 1:
                    df[tgt] = df[args[0]].apply(func)
                else:
                    df[tgt] = df.apply(
                        lambda row: func(*[row.get(a, a) if isinstance(a, str) else a for a in args]), axis=1
                    )
            except Exception:
                df[tgt] = None
        return df

    def apply_field_mappings(self, df: pd.DataFrame, mappings: List[Dict]) -> pd.DataFrame:
        """
        Apply a list of field mappings with optional transforms.
        Each mapping: {
            "source_field": "...",
            "target_field": "...",
            "transform_expression": "...",
            "transform_type": "python|sql",
            "transform_func": "upper|round|...",
            "transform_args": [],
        }
        """
        df = df.copy()
        for mapping in mappings:
            src = mapping.get("source_field")
            tgt = mapping.get("target_field", src)
            expr = mapping.get("transform_expression")
            expr_type = mapping.get("transform_type")
            func_name = mapping.get("transform_func")

            if src and src not in df.columns:
                continue

            if func_name:
                func = self._builtin_names.get(func_name)
                if func and src:
                    try:
                        args = mapping.get("transform_args", [])
                        if args:
                            df[tgt] = df[src].apply(lambda v: func(v, *args))
                        else:
                            df[tgt] = df[src].apply(func)
                    except Exception:
                        df[tgt] = df[src] if src else None
                elif src:
                    df[tgt] = df[src]
            elif expr:
                rule = {"expression": expr, "target_field": tgt, "source_field": src,
                        "type": expr_type or "python"}
                if expr_type == "sql":
                    df = self._apply_sql_expr(df, rule)
                else:
                    df = self._apply_python_expr(df, rule)
            elif src:
                df = self._apply_map(df, {"source_field": src, "target_field": tgt})

        return df

    def validate_expression(self, expr: str, expr_type: str = "python", df_sample: pd.DataFrame = None) -> tuple[bool, str]:
        """Validate an expression before applying it."""
        try:
            if expr_type == "python":
                if df_sample is not None:
                    df_sample.eval(expr, engine="python")
                return True, "Expression is valid"
            elif expr_type == "sql":
                import duckdb
                conn = duckdb.connect(":memory:")
                if df_sample is not None:
                    conn.execute("CREATE TABLE src AS SELECT * FROM df_sample")
                    conn.execute(f"SELECT {expr} FROM src LIMIT 1").fetchall()
                conn.close()
                return True, "SQL expression is valid"
        except Exception as e:
            return False, str(e)
        return True, "OK"

    def list_builtin_funcs(self) -> Dict[str, str]:
        """List all available built-in functions with descriptions."""
        return {
            # Date
            "parse_date": "parse_date(value, fmt='%Y-%m-%d') — 解析日期为字符串",
            "format_date": "format_date(value, fmt='%Y-%m-%d') — 格式化日期",
            "add_days": "add_days(value, days) — 日期加减天数",
            "date_diff": "date_diff(start, end) — 计算日期间隔天数",
            "year": "year(value) — 提取年份",
            "month": "month(value) — 提取月份",
            "day": "day(value) — 提取日",
            "weekday": "weekday(value) — 提取星期几(0-6)",
            # String
            "upper": "upper(value) — 转大写",
            "lower": "lower(value) — 转小写",
            "trim": "trim(value) — 去除首尾空格",
            "substring": "substring(value, start, length=None) — 字符串截取",
            "replace": "replace(value, old, new) — 字符串替换",
            "concat": "concat(*args) — 拼接多个值",
            "split_col": "split_col(value, sep=',') — 分割为列表",
            "split_first": "split_first(value, sep=',') — 取分割后第一个",
            "split_last": "split_last(value, sep=',') — 取分割后最后一个",
            "length": "length(value) — 字符串长度",
            "contains": "contains(value, substr) — 是否包含子串",
            # Numeric
            "round": "round(value, decimals=0) — 四舍五入",
            "abs": "abs(value) — 绝对值",
            "ceil": "ceil(value) — 向上取整",
            "floor": "floor(value) — 向下取整",
            "pow": "pow(value, exponent) — 幂运算",
            "multiply": "multiply(value, factor) — 乘以系数",
            "divide": "divide(value, divisor) — 除以系数",
            # Conditional
            "if_null": "if_null(value, default) — NULL时取默认值",
            "coalesce": "coalesce(*args) — 返回第一个非NULL值",
            "if_then": "if_then(condition, true_val, false_val) — 条件取值",
            # Type conversion
            "to_int": "to_int(value) — 转为整数",
            "to_float": "to_float(value) — 转为浮点数",
            "to_str": "to_str(value) — 转为字符串",
        }


_engine = TransformEngine()


def get_transform_engine() -> TransformEngine:
    return _engine
