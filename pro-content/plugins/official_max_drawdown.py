"""官方精选插件：最大回撤与回测指标。

基于净值序列（或收盘价序列）计算策略回测核心指标：
  - 最大回撤 max_drawdown
  - 回撤起止日期 drawdown_start / drawdown_end
  - 年化收益率 annual_return
  - 年化波动率 annual_volatility
  - 夏普比率 sharpe（需要无风险利率）
  - 胜率 win_rate（基于日收益率正负）

输出为：每一行附加当前滚动指标；最后 N 行（窗口足够时）即为最终回测结果。
"""
import pandas as pd
import numpy as np
from app.core.workflow_engine import BaseNode


class MaxDrawdownNode(BaseNode):
    node_type = "max_drawdown"
    display_name = "最大回撤与回测指标"
    category = "指标计算"
    params_schema = {
        "net_value_column": "净值/收盘价序列列（默认 'close'）",
        "risk_free_rate": "年化无风险利率（默认 0.02，即 2%）",
        "trading_days_per_year": "年化交易日数（默认 252）",
        "output_prefix": "输出列前缀（默认 'backtest'）",
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        src = params.get("net_value_column", "close")
        rf = float(params.get("risk_free_rate", 0.02))
        days = int(params.get("trading_days_per_year", 252))
        prefix = params.get("output_prefix", "backtest")

        if src not in df.columns:
            return df

        work = df.copy()
        nv = work[src].astype(float)
        if nv.isna().all() or (nv <= 0).any():
            return work

        # 日收益率
        ret = nv.pct_change()

        # 累计净值、滚动最高点
        cum_max = nv.cummax()
        drawdown = (nv - cum_max) / cum_max

        # 最大回撤（全局）
        mdd = drawdown.min()

        # 最大回撤起止（找第一次触底和之前的高点）
        trough_idx = drawdown.idxmin()
        peak_idx = nv.loc[:trough_idx].idxmax() if trough_idx is not None else None

        # 年化收益 / 波动 / 夏普（基于全样本）
        total_days = len(nv.dropna())
        total_return = (nv.iloc[-1] / nv.iloc[0]) - 1 if total_days > 1 and nv.iloc[0] > 0 else 0.0
        years = total_days / days
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0
        annual_vol = ret.std() * np.sqrt(days)
        sharpe = (annual_return - rf) / annual_vol if annual_vol > 0 else 0.0

        # 胜率
        valid_ret = ret.dropna()
        win_rate = (valid_ret > 0).mean() if len(valid_ret) > 0 else 0.0

        # 输出（全局标量广播到每一行，便于下游节点/写入）
        work[f"{prefix}_drawdown"] = drawdown
        work[f"{prefix}_max_drawdown"] = mdd
        work[f"{prefix}_annual_return"] = annual_return
        work[f"{prefix}_annual_volatility"] = annual_vol
        work[f"{prefix}_sharpe"] = sharpe
        work[f"{prefix}_win_rate"] = win_rate
        work[f"{prefix}_total_return"] = total_return
        if peak_idx is not None and "dt" in work.columns:
            peak_date = work.loc[peak_idx, "dt"] if peak_idx in work.index else None
            trough_date = work.loc[trough_idx, "dt"] if trough_idx in work.index else None
            work[f"{prefix}_peak_date"] = str(peak_date) if peak_date is not None else ""
            work[f"{prefix}_trough_date"] = str(trough_date) if trough_date is not None else ""
        return work
