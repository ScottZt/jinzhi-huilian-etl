"""Yahoo Finance 数据源适配器 — 免费，覆盖美股/外汇/期货/加密货币/指数。"""
import pandas as pd
from datetime import datetime
from typing import Tuple

from app.adapters.source_adapters.kline_base import KLineSourceAdapter, normalize_config

_INTERVAL_TO_YFINANCE = {
    "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m",
    "60min": "1h", "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "d": "1d", "1d": "1d", "day": "1d", "daily": "1d",
    "D": "1d", "1w": "1wk", "w": "1wk", "weekly": "1wk",
    "1M": "1mo", "monthly": "1mo",
}


def _normalize_interval(interval: str) -> str:
    val = str(interval or "1d").strip()
    return _INTERVAL_TO_YFINANCE.get(val, "1d")


class YfinanceAdapter(KLineSourceAdapter):
    """Yahoo Finance 数据适配器，免费且无需 API Key。

    Symbol 格式参考:
    - 美股: "AAPL", "MSFT"
    - 外汇: "EURUSD=X", "GBPUSD=X"
    - 加密货币: "BTC-USD", "ETH-USD"
    - 期货: "GC=F", "CL=F"
    - 指数: "^GSPC", "^DJI"
    """

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        config = normalize_config(config)
        try:
            import yfinance as yf
        except Exception as e:
            return False, f"yfinance 库不可用: {e}"
        try:
            ticker = yf.Ticker("AAPL")
            df = ticker.history(period="5d")
            if df is not None and not df.empty:
                return True, f"Yahoo Finance 连接成功，AAPL 返回 {len(df)} 条记录"
            return False, "Yahoo Finance 连接成功但返回空数据"
        except Exception as e:
            return False, f"Yahoo Finance 连接失败: {e}"

    def fetch_kline(self, config: dict, codes: list, start_time: datetime,
                    end_time: datetime, interval: str = "1min") -> pd.DataFrame:
        config = normalize_config(config)
        try:
            import yfinance as yf
        except Exception as e:
            raise RuntimeError(f"yfinance 库不可用: {e}")

        yf_interval = _normalize_interval(interval)
        codes_list = [str(c).strip() for c in (codes or []) if str(c).strip()]
        if not codes_list:
            codes_list = ["AAPL"]

        merged = []
        for symbol in codes_list:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(
                    start=start_time.strftime("%Y-%m-%d"),
                    end=(end_time + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                    interval=yf_interval,
                )
                if df is None or df.empty:
                    continue
                df = df.copy()
                df.index = pd.to_datetime(df.index)
                df = df.rename(columns={
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Volume": "vol",
                })
                df["dt"] = df.index
                df["code"] = symbol
                keep = ["code", "dt", "open", "high", "low", "close", "vol"]
                if "amount" in df.columns:
                    keep.append("amount")
                df = df[[c for c in keep if c in df.columns]]
                merged.append(df)
            except Exception:
                continue

        if not merged:
            return pd.DataFrame()
        result = pd.concat(merged, ignore_index=True)
        result = result.sort_values(["code", "dt"]).drop_duplicates(subset=["code", "dt"], keep="last")
        return result.reset_index(drop=True)

    def list_codes(self, config: dict) -> list:
        """yfinance 不支持列出所有股票代码。"""
        return []
