"""官方精选插件：停牌日填充。

A 股股票可能停牌，原始 K 线数据会出现 NaN 或缺失行。
本插件按 code 分组，用前值填充价格类列，成交量填 0，并打标「是否停牌日」。
"""
import pandas as pd
import numpy as np
from app.core.workflow_engine import BaseNode


class FillSuspendedNode(BaseNode):
    node_type = "fill_suspended"
    display_name = "停牌日填充"
    category = "数据处理"
    params_schema = {
        "code_column": "股票代码列（默认 'code'）",
        "date_column": "日期列（默认 'dt'）",
        "price_columns": "价格类列，逗号分隔（默认 'open,high,low,close'）",
        "volume_column": "成交量列（默认 'vol'，停牌日填 0）",
        "complete_dates": "可选，完整交易日序列（CSV 字符串），缺失的日期会补行",
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        code_col = params.get("code_column", "code")
        date_col = params.get("date_column", "dt")
        price_cols = [c.strip() for c in params.get("price_columns", "open,high,low,close").split(",") if c.strip()]
        vol_col = params.get("volume_column", "vol")
        complete_dates_str = params.get("complete_dates", "").strip()

        if code_col not in df.columns or date_col not in df.columns:
            return df

        work = df.copy()
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work = work.sort_values([code_col, date_col])

        # 如果提供了完整交易日序列，先按 code × dates 展开补行
        if complete_dates_str:
            all_dates = pd.to_datetime([d.strip() for d in complete_dates_str.split(",") if d.strip()])
            codes = work[code_col].unique()
            full_idx = pd.MultiIndex.from_product([codes, all_dates], names=[code_col, date_col])
            work = work.set_index([code_col, date_col]).reindex(full_idx).reset_index()

        # 按 code 分组做前值填充
        grouped = work.groupby(code_col, group_keys=False)
        for col in price_cols:
            if col in work.columns:
                work[col] = grouped[col].ffill()
        if vol_col in work.columns:
            work[vol_col] = grouped[vol_col].ffill().fillna(0)

        # 标记停牌日：原始数据缺失 + 经前值填充的 = 停牌
        suspended_flag = work[price_cols[0]].isna() if price_cols and price_cols[0] in work.columns else pd.Series(False, index=work.index)
        # 如果有原始 NaN 且被 ffill 填充，用原始 df 对比
        if not complete_dates_str:
            orig = df.set_index([code_col, date_col])
            cur = work.set_index([code_col, date_col])
            if price_cols and price_cols[0] in orig.columns:
                suspended_flag = cur[price_cols[0]].isna() & orig[price_cols[0]].isna()
                suspended_flag = suspended_flag.reindex(work.set_index([code_col, date_col]).index, fill_value=False).values
                work = work.reset_index(drop=True)
                suspended_flag = pd.Series(suspended_flag, index=work.index)

        work["is_suspended"] = suspended_flag.astype(int).values
        return work
