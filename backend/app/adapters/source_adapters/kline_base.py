"""通用数据源适配器基类 — 合规设计：工具不内置任何第三方 SDK，所有连接由用户自行配置。"""
import abc
import json
import pandas as pd
from datetime import datetime
from typing import Tuple


def normalize_config(config: dict) -> dict:
    """将 config 中可能的 JSON 字符串字段解析为原生对象。

    保存时前端会尝试解析，但直接PUT或从旧记录读取时字段可能仍是字符串。
    涉及的字段：headers, request_template, column_mapping 等。
    """
    JSON_FIELDS = {"headers", "request_template", "column_mapping",
                   "subscribe_template", "ws_params"}
    result = dict(config)
    for key in JSON_FIELDS:
        if key in result and isinstance(result[key], str):
            try:
                result[key] = json.loads(result[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


class KLineSourceAdapter(abc.ABC):
    """Base class for all K-line data sources."""

    @abc.abstractmethod
    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        """Test if the connection is valid. Returns (success, message)."""

    @abc.abstractmethod
    def fetch_kline(self, config: dict, codes: list, start_time: datetime,
                    end_time: datetime, interval: str = "1min") -> pd.DataFrame:
        """Fetch K-line data. Returns standard DataFrame."""

    def list_codes(self, config: dict) -> list:
        """List available stock codes. Optional implementation."""
        return []

    @staticmethod
    def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """Resample 1-min data to other timeframes."""
        if 'dt' in df.columns:
            df = df.set_index('dt')
        agg_dict = {
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
            'vol': 'sum', 'amount': 'sum',
        }
        if 'code' in df.columns:
            agg_dict['code'] = 'first'
        resampled = df.resample(rule).agg(agg_dict).dropna()
        return resampled.reset_index()
