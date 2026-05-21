"""Mootdx 在线行情适配器。

当前以分钟 K 线为主，同时兼容日线抓取，供预览与数据流同步复用。
"""

from datetime import datetime
from typing import List, Tuple

import pandas as pd

from app.adapters.source_adapters.kline_base import KLineSourceAdapter, normalize_config


# Mootdx 的频率枚举兼容字符串与整数两种形式，这里统一做系统粒度映射。
_INTERVAL_TO_FREQUENCY = {
    "1min": 8,
    "5min": "5m",
    "15min": "15m",
    "30min": "30m",
    "60min": "1h",
    "1m": 8,
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "60m": "1h",
    "1h": "1h",
    "d": 9,
    "1d": 9,
    "day": 9,
    "daily": 9,
}


def _normalize_interval(interval: str):
    """把系统中的粒度值映射为 Mootdx 可识别的频率参数。"""
    normalized = str(interval or "1min").strip().lower()
    return _INTERVAL_TO_FREQUENCY.get(normalized, 8)


def _normalize_codes(codes: list) -> List[str]:
    """清洗股票代码输入，保证后续请求只处理有效 6 位代码。"""
    clean_codes = []
    for code in codes or []:
        normalized = str(code or "").strip()
        if normalized:
            clean_codes.append(normalized)
    return clean_codes


def _build_client(config: dict):
    """按配置构造 Mootdx 客户端，支持自动选优与手工指定服务器。"""
    try:
        from mootdx.quotes import Quotes
    except Exception as e:
        raise RuntimeError(f"mootdx 库不可用: {e}") from e

    timeout = int(config.get("timeout", 15) or 15)
    server_host = str(config.get("server_host", "")).strip()
    server_port_raw = str(config.get("server_port", "")).strip()
    use_bestip = str(config.get("use_bestip", "false")).strip().lower() in {"true", "1", "yes"}
    # 默认关闭 bestip：服务器自动选优需数十秒，阻塞 API 调用。
    # 用户如需启用，显式设 use_bestip=true 即可。

    kwargs = {
        "market": "std",
        "timeout": timeout,
        "bestip": use_bestip,
        # 关闭额外心跳，避免预览类请求在短连接场景下引入额外复杂度。
        "heartbeat": False,
    }
    if server_host and server_port_raw:
        kwargs["server"] = (server_host, int(server_port_raw))

    return Quotes.factory(**kwargs)


def _normalize_quote_df(df: pd.DataFrame, code: str, start_time: datetime, end_time: datetime) -> pd.DataFrame:
    """把 Mootdx 返回结果统一整理成系统内部的标准字段。"""
    if df is None or df.empty:
        return pd.DataFrame()

    result = df.copy()
    if "datetime" not in result.columns:
        # Mootdx 某些返回结构会把时间放在索引中，这里统一转为列。
        result["datetime"] = result.index

    result["dt"] = pd.to_datetime(result["datetime"], errors="coerce")
    result = result.dropna(subset=["dt"])

    # 统一成交量字段，后续同步流程默认消费 vol。
    if ("vol" not in result.columns) and ("volume" in result.columns):
        result["vol"] = result["volume"]
    if "amount" not in result.columns:
        result["amount"] = None

    result["code"] = str(code or "").strip()
    keep_columns = ["code", "dt", "open", "high", "low", "close", "vol", "amount"]
    result = result[[col for col in keep_columns if col in result.columns]]
    result = result[(result["dt"] >= start_time) & (result["dt"] <= end_time)]
    result = result.sort_values("dt").drop_duplicates(subset=["code", "dt"], keep="last")
    result = result.reset_index(drop=True)
    return result


class MootdxAdapter(KLineSourceAdapter):
    """Mootdx 在线行情适配器。"""

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        """测试 Mootdx 连通性，默认拉取一只股票的少量分钟线。"""
        config = normalize_config(config)
        client = None
        try:
            client = _build_client(config)
            probe_code = str(config.get("preview_codes", "000001")).split(",")[0].strip() or "000001"
            probe_interval = _normalize_interval(str(config.get("interval", "1min")))
            probe_df = client.bars(symbol=probe_code, frequency=probe_interval, start=0, offset=5)
            if probe_df is None or probe_df.empty:
                return False, "Mootdx 连接成功，但未返回分钟 K 线数据"
            return True, f"Mootdx 连接成功，返回 {len(probe_df)} 条记录"
        except Exception as e:
            return False, f"Mootdx 连接失败: {e}"
        finally:
            if client is not None:
                client.close()

    def fetch_kline(
        self,
        config: dict,
        codes: list,
        start_time: datetime,
        end_time: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        """按时间范围分页抓取 Mootdx K 线，并转换为标准结构。"""
        config = normalize_config(config)
        target_codes = _normalize_codes(codes)
        if not target_codes:
            target_codes = ["000001"]

        page_size = min(int(config.get("page_size", 800) or 800), 800)
        max_pages = max(int(config.get("max_pages", 12) or 12), 1)
        frequency = _normalize_interval(interval or config.get("interval", "1min"))

        client = None
        merged_frames = []
        try:
            client = _build_client(config)
            for code in target_codes:
                start = 0
                page_count = 0
                while page_count < max_pages:
                    page_count += 1
                    raw_df = client.bars(symbol=code, frequency=frequency, start=start, offset=page_size)
                    normalized_df = _normalize_quote_df(raw_df, code, start_time, end_time)
                    if normalized_df.empty:
                        break

                    merged_frames.append(normalized_df)
                    # 若当前页已覆盖目标起始时间，则无需继续向更早历史翻页。
                    if normalized_df["dt"].min() <= start_time:
                        break
                    if len(raw_df) < page_size:
                        break
                    start += page_size

            if not merged_frames:
                return pd.DataFrame()

            result = pd.concat(merged_frames, ignore_index=True)
            result = result.sort_values(["code", "dt"]).drop_duplicates(subset=["code", "dt"], keep="last")
            result = result.reset_index(drop=True)
            return result
        finally:
            if client is not None:
                client.close()

    def list_codes(self, config: dict) -> list:
        """读取沪深股票列表，供前端代码候选预览使用。"""
        config = normalize_config(config)
        client = None
        try:
            client = _build_client(config)
            df = client.stock_all()
            if df is None or df.empty:
                return []

            results = []
            for _, row in df.iterrows():
                code = str(row.get("code", "")).strip()
                if not code:
                    continue
                results.append(
                    {
                        "code": code,
                        "name": str(row.get("name", "")).strip(),
                        "market": row.get("market"),
                    }
                )
            return results
        except Exception:
            return []
        finally:
            if client is not None:
                client.close()
