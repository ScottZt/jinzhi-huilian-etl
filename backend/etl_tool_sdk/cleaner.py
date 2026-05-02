"""
数据清洗接口 — 合规设计：封装工具自身数据处理逻辑，不涉及任何第三方数据源。
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Union, Callable
from datetime import datetime, timedelta

from etl_tool_sdk.license import LicenseManager


class DataCleaner:
    """
    数据清洗器 — 提供数据去重、空值处理、类型转换、字段映射、分块处理等能力。

    合规说明：仅封装工具自身数据处理接口，不涉及任何第三方数据源。

    使用示例：
        cleaner = DataCleaner()

        # 去重
        df = cleaner.drop_duplicates(df, subset=["id"])

        # 空值处理
        df = cleaner.fillna(df, {"price": 0, "name": "N/A"})
        df = cleaner.dropna(df, thresh=3)

        # 字段映射
        df = cleaner.map_columns(df, {"旧列名": "新列名"})

        # 数据类型转换
        df = cleaner.cast_types(df, {"price": "float64", "quantity": "int64"})

        # 过滤行
        df = cleaner.filter_rows(df, "price > 100")

        # 数据校验
        report = cleaner.profile(df)
        print(report)
    """

    def __init__(self):
        self._lm = LicenseManager()

    # ---- 去重 ----

    def drop_duplicates(
        self,
        df: pd.DataFrame,
        subset: Optional[List[str]] = None,
        keep: str = "first",
    ) -> pd.DataFrame:
        """删除重复行。

        Args:
            df: 输入 DataFrame
            subset: 用于判断重复的列（None 表示全部列）
            keep: 保留策略（'first'/'last'/False）
        Returns:
            去重后的 DataFrame
        """
        if df.empty:
            return df
        return df.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)

    # ---- 空值处理 ----

    def fillna(
        self,
        df: pd.DataFrame,
        fill_values: Dict[str, Any],
        strategy: str = "value",
    ) -> pd.DataFrame:
        """
        填充空值。

        Args:
            df: 输入 DataFrame
            fill_values: 列名 → 填充值的映射
                - value 策略：直接填入指定值
                - "mean"/"median"/"mode"/"ffill"/"bfill" 策略：填入统计值
            strategy: "value" | "mean" | "median" | "mode" | "ffill" | "bfill"
        Returns:
            填充后的 DataFrame
        """
        result = df.copy()
        for col, val in fill_values.items():
            if col not in result.columns:
                continue
            if strategy == "value":
                result[col] = result[col].fillna(val)
            elif strategy == "mean":
                result[col] = result[col].fillna(result[col].mean())
            elif strategy == "median":
                result[col] = result[col].fillna(result[col].median())
            elif strategy == "mode":
                mode_val = result[col].mode()
                result[col] = result[col].fillna(mode_val.iloc[0] if len(mode_val) else val)
            elif strategy == "ffill":
                result[col] = result[col].fillna(method="ffill")
            elif strategy == "bfill":
                result[col] = result[col].fillna(method="bfill")
        return result

    def dropna(
        self,
        df: pd.DataFrame,
        axis: int = 0,
        thresh: Optional[int] = None,
        subset: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        删除含空值的行/列。

        Args:
            thresh: 删除非空值少于 thresh 的行/列
            subset: 仅检查指定列的空值
        """
        return df.dropna(axis=axis, thresh=thresh, subset=subset)

    # ---- 字段操作 ----

    def map_columns(self, df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
        """重命名列（字段映射）。

        Args:
            mapping: {旧列名: 新列名}
        """
        return df.rename(columns=mapping)

    def split_column(
        self,
        df: pd.DataFrame,
        column: str,
        sep: str,
        new_columns: List[str],
    ) -> pd.DataFrame:
        """按分隔符拆分一列为多列。

        Args:
            column: 要拆分的列名
            sep: 分隔符
            new_columns: 新列名列表
        """
        if column not in df.columns:
            return df
        temp = df[column].str.split(sep, expand=True)
        for i, name in enumerate(new_columns):
            if i < temp.shape[1]:
                df[name] = temp[i]
        return df

    def merge_columns(
        self,
        df: pd.DataFrame,
        columns: List[str],
        new_column: str,
        sep: str = "",
    ) -> pd.DataFrame:
        """合并多列为新列。

        Args:
            columns: 要合并的列名列表
            new_column: 新列名
            sep: 连接符
        """
        existing = [c for c in columns if c in df.columns]
        if not existing:
            return df
        df[new_column] = df[existing].astype(str).agg(sep.join, axis=1)
        return df

    def cast_types(self, df: pd.DataFrame, type_map: Dict[str, str]) -> pd.DataFrame:
        """
        类型转换。

        Args:
            type_map: {列名: 类型名}，类型名支持：
                "int64", "float64", "string", "datetime", "bool"
        """
        result = df.copy()
        for col, dtype in type_map.items():
            if col not in result.columns:
                continue
            try:
                if dtype == "datetime":
                    result[col] = pd.to_datetime(result[col], errors="coerce")
                elif dtype == "int64":
                    result[col] = pd.to_numeric(result[col], errors="coerce").astype("Int64")
                elif dtype == "float64":
                    result[col] = pd.to_numeric(result[col], errors="coerce")
                elif dtype == "bool":
                    result[col] = result[col].astype(bool)
                else:
                    result[col] = result[col].astype(dtype)
            except Exception:
                pass
        return result

    # ---- 过滤与排序 ----

    def filter_rows(
        self,
        df: pd.DataFrame,
        condition: str,
    ) -> pd.DataFrame:
        """
        按条件过滤行。使用 Python 表达式语法。

        Args:
            condition: 过滤条件，如 "price > 100", "name.str.contains('test')"
        Returns:
            过滤后的 DataFrame
        """
        try:
            return df.query(condition).reset_index(drop=True)
        except Exception as e:
            print(f"Filter error: {e}")
            return df

    def sort_rows(
        self,
        df: pd.DataFrame,
        by: List[str],
        ascending: Union[bool, List[bool]] = True,
    ) -> pd.DataFrame:
        """排序。"""
        return df.sort_values(by=by, ascending=ascending).reset_index(drop=True)

    # ---- 数据转换 ----

    def apply_transform(
        self,
        df: pd.DataFrame,
        column: str,
        func: Callable,
        new_column: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        对指定列应用转换函数。

        Args:
            column: 列名
            func: 转换函数（单值 → 单值）
            new_column: 新列名（None 表示覆盖原列）
        """
        result = df.copy()
        target = new_column or column
        result[target] = df[column].apply(func)
        return result

    def add_formula_column(
        self,
        df: pd.DataFrame,
        expression: str,
        new_column: str,
    ) -> pd.DataFrame:
        """
        使用表达式添加计算列。

        Args:
            expression: Python 表达式，如 "price * quantity"
            new_column: 新列名
        """
        result = df.copy()
        try:
            result[new_column] = result.eval(expression)
        except Exception as e:
            print(f"Formula error: {e}")
        return result

    def resample_timeframe(
        self,
        df: pd.DataFrame,
        freq: str,
        datetime_column: str = "datetime",
    ) -> pd.DataFrame:
        """
        按时间维度重采样（K线数据用）。

        Args:
            freq: 重采样频率，如 "1H", "1D", "W", "5T"（T=分钟）
            datetime_column: 时间列名
        """
        if df.empty or datetime_column not in df.columns:
            return df

        result = df.set_index(datetime_column)

        agg_cols = {}
        for col in result.columns:
            if col == datetime_column:
                continue
            if result[col].dtype in ["float64", "int64", "Int64"]:
                agg_cols[col] = "last"
            else:
                agg_cols[col] = "first"

        ohcv_cols = {"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum"}
        for k, v in ohcv_cols.items():
            if k in result.columns:
                agg_cols[k] = v

        resampled = result.resample(freq).agg(agg_cols).dropna()
        return resampled.reset_index()

    # ---- 哈希与校验 ----

    def add_hash_column(
        self,
        df: pd.DataFrame,
        columns: List[str],
        hash_column: str = "_row_hash",
        algorithm: str = "md5",
    ) -> pd.DataFrame:
        """为指定列生成哈希值（用于差异比对）。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("advanced_script")

        import hashlib
        result = df.copy()
        vals = result[columns].astype(str).agg("|".join, axis=1)
        if algorithm == "md5":
            result[hash_column] = vals.apply(lambda x: hashlib.md5(x.encode()).hexdigest())
        else:
            result[hash_column] = vals.apply(lambda x: hashlib.sha256(x.encode()).hexdigest())
        return result

    def diff_compare(
        self,
        old_df: pd.DataFrame,
        new_df: pd.DataFrame,
        key_columns: List[str],
    ) -> Dict[str, pd.DataFrame]:
        """
        比对新旧数据集差异。

        Returns:
            {"added": 新增行, "removed": 删除行, "changed": 变更行}
        """
        self._lm.check_feature_or_raise("advanced_script")

        key_set = set(key_columns)
        old_keys = set(old_df[key_columns].astype(str).agg("|".join, axis=1))
        new_keys = set(new_df[key_columns].astype(str).agg("|".join, axis=1))

        added_keys = new_keys - old_keys
        removed_keys = old_keys - new_keys

        added = new_df[
            new_df[key_columns].astype(str).agg("|".join, axis=1).isin(added_keys)
        ]
        removed = old_df[
            old_df[key_columns].astype(str).agg("|".join, axis=1).isin(removed_keys)
        ]

        common_keys = old_keys & new_keys
        old_common = old_df[
            old_df[key_columns].astype(str).agg("|".join, axis=1).isin(common_keys)
        ].set_index(key_columns)
        new_common = new_df[
            new_df[key_columns].astype(str).agg("|".join, axis=1).isin(common_keys)
        ].set_index(key_columns)

        changed = new_common.compare(old_common).dropna()
        changed.columns = ["new", "old"]

        return {
            "added": added.reset_index(drop=True),
            "removed": removed.reset_index(drop=True),
            "changed": changed.reset_index(),
        }

    # ---- 数据质量报告 ----

    def profile(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        生成数据质量报告。

        Returns:
            {
                "row_count": int,
                "column_count": int,
                "null_counts": {col: count},
                "dtypes": {col: dtype},
                "numeric_stats": {col: {mean, std, min, max, median}},
            }
        """
        report = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "null_counts": {},
            "dtypes": {},
            "numeric_stats": {},
        }

        for col in df.columns:
            report["null_counts"][col] = int(df[col].isna().sum())
            report["dtypes"][col] = str(df[col].dtype)

            if pd.api.types.is_numeric_dtype(df[col]):
                stats = df[col].describe()
                report["numeric_stats"][col] = {
                    "mean": float(stats.get("mean", 0)),
                    "std": float(stats.get("std", 0)),
                    "min": float(stats.get("min", 0)),
                    "max": float(stats.get("max", 0)),
                    "median": float(stats.get("50%", 0)),
                }

        return report

    # ---- 分块处理 ----

    def process_in_chunks(
        self,
        df: pd.DataFrame,
        func: Callable[[pd.DataFrame], pd.DataFrame],
        chunk_size: int = 10000,
    ) -> pd.DataFrame:
        """
        分块处理大数据 DataFrame。

        Args:
            func: 处理函数，输入 DataFrame chunk，返回处理后的 DataFrame chunk
            chunk_size: 块大小
        """
        if len(df) <= chunk_size:
            return func(df)

        chunks = []
        for start in range(0, len(df), chunk_size):
            chunk = df.iloc[start:start + chunk_size]
            processed = func(chunk)
            chunks.append(processed)
        return pd.concat(chunks, ignore_index=True)
