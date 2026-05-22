"""Binance 加密货币数据源适配器 — 公共行情接口，无需 API Key。

使用 requests 直接调用 Binance REST API，避免 python-binance 对镜像域名支持不好的问题。
国内默认使用 data-api.binance.vision 镜像。
"""
import time
import requests
import pandas as pd
from datetime import datetime
from typing import Tuple

from app.adapters.source_adapters.kline_base import KLineSourceAdapter, normalize_config

_INTERVAL_TO_BINANCE = {
    "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m",
    "60min": "1h", "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "d": "1d", "1d": "1d", "day": "1d", "daily": "1d",
    "D": "1d", "1w": "1w", "w": "1w", "weekly": "1w",
}

_DEFAULT_BASE_URL = "https://data-api.binance.vision"


def _normalize_interval(interval: str) -> str:
    val = str(interval or "1m").strip().lower()
    return _INTERVAL_TO_BINANCE.get(val, "1m")


class BinanceAdapter(KLineSourceAdapter):
    """Binance 公共行情适配器，通过 REST API 直接调用，国内镜像可用。"""

    def _request(self, path: str, params: dict, config: dict) -> dict:
        """发送 GET 请求到 Binance API。"""
        base_url = str(config.get("base_url", "")).strip() or _DEFAULT_BASE_URL
        url = f"{base_url}/{path}"
        timeout = int(config.get("timeout", 15))
        headers = {}
        api_key = str(config.get("api_key", "")).strip()
        if api_key:
            headers["X-MBX-APIKEY"] = api_key
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        config = normalize_config(config)
        try:
            data = self._request("api/v3/ping", {}, config)
            # ping 成功，再拉少量数据验证
            klines = self._request("api/v3/klines", {
                "symbol": "BTCUSDT", "interval": "1d", "limit": 5,
            }, config)
            if klines and len(klines) > 0:
                return True, f"Binance 连接成功，BTCUSDT 返回 {len(klines)} 条K线"
            return False, "Binance 连接成功但返回空数据"
        except Exception as e:
            return False, f"Binance 连接失败: {e}"

    def fetch_kline(self, config: dict, codes: list, start_time: datetime,
                    end_time: datetime, interval: str = "1min") -> pd.DataFrame:
        config = normalize_config(config)
        binance_interval = _normalize_interval(interval)

        codes_list = [str(c).strip() for c in (codes or []) if str(c).strip()]
        if not codes_list:
            codes_list = ["BTCUSDT"]

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        merged = []
        for symbol in codes_list:
            try:
                all_klines = []
                current_start = start_ms
                while current_start <= end_ms:
                    params = {
                        "symbol": symbol,
                        "interval": binance_interval,
                        "startTime": current_start,
                        "endTime": end_ms,
                        "limit": 1000,
                    }
                    klines = self._request("api/v3/klines", params, config)
                    if not klines:
                        break
                    all_klines.extend(klines)
                    # 如果返回少于1000条，说明已到上限
                    if len(klines) < 1000:
                        break
                    # 下一批从最后一条之后开始
                    current_start = klines[-1][0] + 1
                    # 避免请求过快触发频率限制
                    time.sleep(0.1)

                if not all_klines:
                    continue

                df = pd.DataFrame(all_klines, columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "trades", "taker_buy_base",
                    "taker_buy_quote", "ignore"
                ])
                df["dt"] = pd.to_datetime(df["open_time"], unit="ms")
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df["code"] = symbol
                keep = ["code", "dt", "open", "high", "low", "close", "volume"]
                df = df[[c for c in keep if c in df.columns]]
                df = df.rename(columns={"volume": "vol"})
                merged.append(df)
            except Exception:
                continue

        if not merged:
            return pd.DataFrame()
        result = pd.concat(merged, ignore_index=True)
        result = result.sort_values(["code", "dt"]).drop_duplicates(subset=["code", "dt"], keep="last")
        return result.reset_index(drop=True)

    def list_codes(self, config: dict) -> list:
        config = normalize_config(config)
        try:
            data = self._request("api/v3/exchangeInfo", {}, config)
            results = []
            for sym in data.get("symbols", []):
                if sym.get("status") == "TRADING":
                    results.append({
                        "code": sym["symbol"],
                        "name": f'{sym.get("baseAsset","")}/{sym.get("quoteAsset","")}',
                        "baseAsset": sym.get("baseAsset", ""),
                        "quoteAsset": sym.get("quoteAsset", ""),
                    })
            return results
        except Exception:
            return []
