"""示例自定义插件 — 数据标准化。
将该文件放入 plugins/ 目录，重启服务后自动加载。
"""
import pandas as pd
from app.core.workflow_engine import BaseNode


class DataNormalizerNode(BaseNode):
    node_type = "normalize"
    display_name = "数据标准化"
    category = "数据处理"

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df
        columns = params.get("columns", "").split(",")
        method = params.get("method", "minmax")
        if not columns or not columns[0]:
            return df
        work = df.copy()
        for col in columns:
            col = col.strip()
            if col not in work.columns:
                continue
            if method == "minmax":
                mn, mx = work[col].min(), work[col].max()
                if mx > mn:
                    work[col] = (work[col] - mn) / (mx - mn)
            elif method == "zscore":
                mean = work[col].mean()
                std = work[col].std()
                if std > 0:
                    work[col] = (work[col] - mean) / std
        return work
