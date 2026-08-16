"""因子计算节点 — 统一的基础因子计算引擎。

支持多种因子计算类型，输出统一格式的因子数据：
- code: 股票代码
- dt: 日期
- factor_value: 因子值（主输出列）
- 其他辅助列（如 MACD 的 dif/dea/signal）

因子计算后，下游 factor_write 节点会将 factor_value 写入因子库。
"""
import json
import numpy as np
import pandas as pd
from app.core.workflow_engine import BaseNode


class FactorComputeNode(BaseNode):
    node_type = "factor_compute"
    display_name = "因子计算"
    category = "因子库"
    params_schema = {
        "factor_id": {
            "type": "text",
            "label": "因子ID",
            "default": "ma_5",
        },
        "compute_type": {
            "type": "select",
            "label": "计算类型",
            "options": [
                "ma",        # 移动平均
                "ema",       # 指数移动平均
                "macd",      # MACD
                "rsi",       # RSI
                "boll",      # 布林带
                "return",    # 收益率
                "volatility",# 波动率
                "atr",       # ATR 真实波幅
                "bias",      # BIAS 乖离率
            ],
            "default": "ma",
        },
        "params_json": {
            "type": "text",
            "label": "参数JSON（如 {\"window\": 5}）",
            "default": '{"window": 5}',
        },
        "source_column": {
            "type": "text",
            "label": "源字段",
            "default": "close",
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
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df

        factor_id = params.get("factor_id", "factor")
        compute_type = params.get("compute_type", "ma")
        source_col = params.get("source_column", "close")
        code_col = params.get("code_column", "code")
        date_col = params.get("date_column", "dt")

        # 解析参数 JSON
        params_json = params.get("params_json", "{}")
        try:
            calc_params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except Exception:
            calc_params = {}

        if source_col not in df.columns:
            raise ValueError(f"源字段 '{source_col}' 不存在于数据中")

        work = df.copy()

        # 按股票代码分组计算（支持多股票批量）
        if code_col in work.columns:
            results = []
            for code, group in work.groupby(code_col):
                group = group.sort_values(date_col).copy()
                group = self._compute(group, compute_type, source_col, calc_params)
                results.append(group)
            work = pd.concat(results, ignore_index=True)
        else:
            work = work.sort_values(date_col).copy()
            work = self._compute(work, compute_type, source_col, calc_params)

        # 输出统一格式：保留 code, dt, factor_value, 以及辅助列
        output_cols = [code_col, date_col, "factor_value"]
        # 添加辅助列（如 macd 的 dif, dea 等）
        for col in work.columns:
            if col.startswith("_factor_") and col not in output_cols:
                output_cols.append(col)

        # 只保留存在的列
        output_cols = [c for c in output_cols if c in work.columns]
        return work[output_cols].copy()

    def _compute(self, df: pd.DataFrame, compute_type: str, source_col: str, params: dict) -> pd.DataFrame:
        """执行具体的因子计算。"""
        s = df[source_col].astype(float)

        if compute_type == "ma":
            window = int(params.get("window", 5))
            df["factor_value"] = s.rolling(window=window).mean()

        elif compute_type == "ema":
            span = int(params.get("span", params.get("window", 5)))
            df["factor_value"] = s.ewm(span=span, adjust=False).mean()

        elif compute_type == "macd":
            fast = int(params.get("fast", 12))
            slow = int(params.get("slow", 26))
            signal = int(params.get("signal", 9))
            exp_fast = s.ewm(span=fast, adjust=False).mean()
            exp_slow = s.ewm(span=slow, adjust=False).mean()
            df["_factor_dif"] = exp_fast - exp_slow
            df["_factor_dea"] = df["_factor_dif"].ewm(span=signal, adjust=False).mean()
            df["factor_value"] = (df["_factor_dif"] - df["_factor_dea"]) * 2  # MACD 柱

        elif compute_type == "rsi":
            window = int(params.get("window", 14))
            delta = s.diff()
            gain = delta.where(delta > 0, 0.0).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=window).mean()
            rs = gain / loss.replace(0, np.nan)
            df["factor_value"] = 100 - (100 / (1 + rs))

        elif compute_type == "boll":
            window = int(params.get("window", 20))
            std_mult = float(params.get("std_mult", 2))
            mid = s.rolling(window=window).mean()
            std = s.rolling(window=window).std()
            df["_factor_boll_mid"] = mid
            df["_factor_boll_upper"] = mid + std_mult * std
            df["_factor_boll_lower"] = mid - std_mult * std
            df["factor_value"] = mid  # 默认输出中轨

        elif compute_type == "return":
            # 收益率
            window = int(params.get("window", 1))
            df["factor_value"] = s.pct_change(periods=window)

        elif compute_type == "volatility":
            # 波动率（年化）
            window = int(params.get("window", 20))
            ret = s.pct_change()
            df["factor_value"] = ret.rolling(window=window).std() * np.sqrt(252)

        elif compute_type == "atr":
            # ATR 真实波幅
            window = int(params.get("window", 14))
            high = df.get("high", s).astype(float)
            low = df.get("low", s).astype(float)
            prev_close = s.shift(1)
            tr = pd.concat([
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs()
            ], axis=1).max(axis=1)
            df["factor_value"] = tr.rolling(window=window).mean()

        elif compute_type == "bias":
            # BIAS 乖离率
            window = int(params.get("window", 6))
            ma = s.rolling(window=window).mean()
            df["factor_value"] = (s - ma) / ma * 100

        else:
            raise ValueError(f"不支持的计算类型: {compute_type}")

        return df
