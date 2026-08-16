"""官方插件 · 停牌日填充（A 股缺失数据处理）。

节点：
  - suspended_fill    补齐停牌/缺失交易日，支持 ffill / interpolate / zero 三种填充方式
"""
import numpy as np
import pandas as pd
from app.core.workflow_engine import BaseNode


class SuspendedFillNode(BaseNode):
    node_type = "suspended_fill"
    display_name = "停牌日填充"
    category = "官方插件"
    params_schema = {
        "date_column":    {"type": "string", "label": "日期列", "default": "date"},
        "symbol_column":  {"type": "string", "label": "股票代码列（可选，按股票分组补齐）"},
        "fill_method":    {"type": "select", "label": "填充方式",
                           "options": ["ffill", "interpolate", "zero"], "default": "ffill"},
        "fill_columns":   {"type": "string", "label": "需填充的列（逗号分隔，留空=所有数值列）"},
        "add_status_col": {"type": "bool",   "label": "新增停牌状态列", "default": True},
    }

    def process(self, df: pd.DataFrame, params: dict, context=None) -> pd.DataFrame:
        if df.empty:
            return df
        date_col = params.get("date_column", "date")
        sym_col = (params.get("symbol_column") or "").strip()
        method = params.get("fill_method", "ffill")
        fill_cols_raw = (params.get("fill_columns") or "").strip()
        add_status = bool(params.get("add_status_col", True))

        if date_col not in df.columns:
            return df

        work = df.copy()
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work = work.dropna(subset=[date_col])

        # 确定填充列
        if fill_cols_raw:
            fill_cols = [c.strip() for c in fill_cols_raw.split(",") if c.strip() and c.strip() in work.columns]
        else:
            fill_cols = [c for c in work.select_dtypes(include=[np.number]).columns if c != date_col]

        # 构造完整交易日索引（基于整体数据的最小/最大日期）
        dmin, dmax = work[date_col].min(), work[date_col].max()
        if pd.isna(dmin) or pd.isna(dmax):
            return df
        full_dates = pd.date_range(dmin, dmax, freq="B")  # 工作日（未剔节假日，节假日保留空值）

        def _fill_one(sub: pd.DataFrame) -> pd.DataFrame:
            sub = sub.set_index(date_col)
            sub = sub[~sub.index.duplicated(keep="first")]
            sub = sub.reindex(full_dates)
            sub.index.name = date_col
            if method == "ffill":
                sub[fill_cols] = sub[fill_cols].ffill()
            elif method == "interpolate":
                sub[fill_cols] = sub[fill_cols].interpolate(method="time")
            else:  # zero
                sub[fill_cols] = sub[fill_cols].fillna(0)
            return sub.reset_index()

        if sym_col and sym_col in work.columns:
            parts = []
            for _, g in work.groupby(sym_col):
                filled = _fill_one(g)
                filled[sym_col] = g[sym_col].iloc[0]
                parts.append(filled)
            out = pd.concat(parts, ignore_index=True)
        else:
            out = _fill_one(work)

        if add_status:
            # 标记停牌：原本不存在于原始数据的行
            orig_keys = set(
                (df[date_col].astype(str) + "|" + df[sym_col].astype(str)).values
                if sym_col and sym_col in df.columns
                else df[date_col].astype(str).values
            )
            if sym_col and sym_col in out.columns:
                key = out[date_col].astype(str) + "|" + out[sym_col].astype(str)
            else:
                key = out[date_col].astype(str)
            out["is_suspended"] = ~key.isin(orig_keys)
        return out
