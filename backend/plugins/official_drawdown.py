"""官方插件 · 最大回撤与回测三大指标。

节点：
  - backtest_metrics    根据净值 / 权益曲线计算：
      - 最大回撤 max_drawdown (%)
      - 最大回撤持续天数 max_drawdown_duration
      - 年化夏普比率 sharpe_ratio
      - 索提诺比率 sortino_ratio
      - 卡尔玛比率 calmar_ratio
"""
import numpy as np
import pandas as pd
from app.core.workflow_engine import BaseNode


class BacktestMetricsNode(BaseNode):
    node_type = "backtest_metrics"
    display_name = "最大回撤与回测指标"
    category = "官方插件"
    params_schema = {
        "equity_column":  {"type": "string", "label": "净值 / 权益列", "default": "equity"},
        "symbol_column":  {"type": "string", "label": "股票代码列（可选）"},
        "risk_free_rate": {"type": "number", "label": "年化无风险利率（%）", "default": 2.0},
        "periods_per_year": {"type": "number", "label": "年化周期（日=252，周=52，月=12）", "default": 252},
        "out_prefix":     {"type": "string", "label": "输出列前缀", "default": "bt_"},
    }

    def process(self, df: pd.DataFrame, params: dict, context=None) -> pd.DataFrame:
        if df.empty:
            return df
        eq_col = params.get("equity_column", "equity")
        sym_col = (params.get("symbol_column") or "").strip()
        rf_year = float(params.get("risk_free_rate", 2.0)) / 100.0
        periods = max(1, int(params.get("periods_per_year", 252)))
        prefix = params.get("out_prefix", "bt_") or "bt_"

        if eq_col not in df.columns:
            return df

        rf_per_period = (1 + rf_year) ** (1 / periods) - 1

        def _metrics(series: pd.Series) -> dict:
            s = series.astype(float).replace([np.inf, -np.inf], np.nan).dropna()
            n = len(s)
            out = {
                "max_drawdown": np.nan,
                "max_drawdown_duration": np.nan,
                "sharpe_ratio": np.nan,
                "sortino_ratio": np.nan,
                "calmar_ratio": np.nan,
            }
            if n < 2:
                return out

            # 最大回撤
            cummax = s.cummax()
            drawdown = (s - cummax) / cummax.replace(0, np.nan)
            mdd = drawdown.min()
            out["max_drawdown"] = float(mdd)

            # 最大回撤持续天数
            underwater = drawdown < 0
            if underwater.any():
                changes = underwater.astype(int).diff().fillna(underwater.iloc[0].astype(int))
                starts = underwater.index[changes == 1].tolist()
                if underwater.iloc[0]:
                    starts = [underwater.index[0]] + starts
                ends = underwater.index[changes == -1].tolist()
                if underwater.iloc[-1]:
                    ends = ends + [underwater.index[-1]]
                durations = [
                    (ends[i] if i < len(ends) else underwater.index[-1]) - starts[i]
                    for i in range(len(starts))
                ]
                out["max_drawdown_duration"] = float(max(durations)) if durations else 0
            else:
                out["max_drawdown_duration"] = 0

            # 收益率序列
            ret = s.pct_change().dropna()
            if ret.empty:
                return out
            excess = ret - rf_per_period
            mu = excess.mean()
            std = ret.std()
            down_std = ret[ret < 0].std()
            ann_ret = (1 + ret.mean()) ** periods - 1
            total_ret = (s.iloc[-1] / s.iloc[0]) - 1 if s.iloc[0] != 0 else 0

            if std and std > 0:
                out["sharpe_ratio"] = float(mu / std * np.sqrt(periods))
            if down_std and down_std > 0:
                out["sortino_ratio"] = float(mu / down_std * np.sqrt(periods))
            mdd_abs = abs(mdd) if mdd and mdd != 0 else np.nan
            if not np.isnan(mdd_abs) and mdd_abs > 0:
                out["calmar_ratio"] = float(ann_ret / mdd_abs)
            return out

        def _apply(sub: pd.DataFrame) -> pd.DataFrame:
            m = _metrics(sub[eq_col])
            sub = sub.copy()
            for k, v in m.items():
                sub[prefix + k] = v
            return sub

        if sym_col and sym_col in df.columns:
            return df.groupby(sym_col, group_keys=False).apply(_apply)
        return _apply(df)
