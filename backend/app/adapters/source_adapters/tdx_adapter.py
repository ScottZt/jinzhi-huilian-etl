"""通达信行情 TCP 适配器 — 使用 pytdx 直连行情服务器（端口 7709）。"""
import pandas as pd
from datetime import datetime
from typing import Tuple
import socket

from app.adapters.source_adapters.kline_base import KLineSourceAdapter, normalize_config

# 常见通达信行情服务器列表（公开免费）
TDX_SERVERS = [
    ("119.147.212.81", 7709),
    ("114.80.63.12", 7709),
    ("218.75.126.9", 7709),
    ("124.74.234.130", 7709),
    ("180.153.18.17", 7709),
    ("61.152.107.141", 7709),
    ("221.231.159.216", 7709),
    ("218.9.148.108", 7709),
]


def _parse_server_addr(config: dict) -> tuple:
    """Parse server address from config. Returns (host, port)."""
    addr = config.get("tdx_server", "")
    if addr == "custom":
        addr = config.get("tdx_custom", "")
    if not addr:
        # Default
        addr = "119.147.212.81:7709"
    if ":" in addr:
        host, port = addr.rsplit(":", 1)
        return host, int(port)
    return addr, 7709


class TdxAdapter(KLineSourceAdapter):
    """通达信行情 TCP 适配器，使用 pytdx SDK 直连。

    不需要凭证/Token，行情服务器为公开免费服务。
    """

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        host, port = _parse_server_addr(config)
        timeout = int(config.get("timeout", 10))

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True, f"TCP 连接成功 ({host}:{port})"
            return False, f"端口 {port} 不可达 ({host})，请尝试其他服务器"
        except socket.timeout:
            return False, f"连接超时 ({host}:{port})"
        except socket.gaierror:
            return False, f"DNS 解析失败 ({host})"
        except Exception as e:
            return False, f"{e}"

    def _get_api(self):
        """Lazy import pytdx."""
        try:
            from pytdx.hq import TdxHq_API
            return TdxHq_API
        except ImportError:
            raise RuntimeError("pytdx 库未安装，请运行: pip install pytdx")

    def _code_to_tdx(self, code: str) -> tuple:
        """Convert stock code to TDX market/code format.
        Returns (market, code_str).
        Market: 0=深圳, 1=上海
        """
        code_str = str(code).strip()
        if code_str.startswith("6"):
            return 1, code_str  # 上海
        return 0, code_str  # 深圳

    def fetch_kline(self, config: dict, codes: list, start_time: datetime,
                    end_time: datetime, interval: str = "1min") -> pd.DataFrame:
        TdxHq_API = self._get_api()
        host, port = _parse_server_addr(config)
        timeout = int(config.get("timeout", 30))

        # Map interval to TDX category
        # 0=5分钟, 1=15分钟, 2=30分钟, 3=1小时, 4=日线, 5=周线, 6=月线, 7=1分钟, 8=1分钟(精确)
        interval_map = {
            "1min": 8, "5min": 0, "15min": 1, "30min": 2,
            "60min": 3, "1h": 3, "D": 4, "W": 5, "M": 6,
            "daily": 4, "weekly": 5, "monthly": 6,
        }
        category = interval_map.get(interval, 4)

        rows = []
        with TdxHq_API(raise_exception=False) as api:
            if not api.connect(host, port, time_out=timeout):
                raise RuntimeError(f"无法连接到行情服务器 {host}:{port}")

            for code in codes:
                market, code_str = self._code_to_tdx(code)
                # TDX get_security_bars returns max 800 bars per call
                # We need to paginate if date range is large
                all_bars = []
                pos = 0
                while True:
                    data = api.get_security_bars(category, market, code_str, pos, 800)
                    if not data:
                        break
                    all_bars.extend(data)
                    if len(data) < 800:
                        break
                    pos += 800
                    if pos > 100:  # Safety limit
                        break

                # Filter by date range
                for bar in all_bars:
                    dt = bar.get("datetime")
                    if dt and start_time <= dt <= end_time:
                        rows.append({
                            "datetime": dt,
                            "open": bar.get("open"),
                            "high": bar.get("high"),
                            "low": bar.get("low"),
                            "close": bar.get("close"),
                            "volume": bar.get("vol", bar.get("volume", 0)),
                            "amount": bar.get("amount", 0),
                            "code": code_str,
                        })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        return df

    def list_codes(self, config: dict) -> list:
        TdxHq_API = self._get_api()
        host, port = _parse_server_addr(config)
        timeout = int(config.get("timeout", 15))

        codes = []
        with TdxHq_API(raise_exception=False) as api:
            if not api.connect(host, port, time_out=timeout):
                return []

            # Get stock list for both markets
            for market in [0, 1]:
                data = api.get_security_list(market, 0)
                if data:
                    for item in data:
                        codes.append({
                            "code": item.get("code", ""),
                            "name": item.get("name", ""),
                            "market": market,
                        })
        return codes
