"""通达信本地数据文件适配器。

本适配器读取用户本地已通过通达信官方客户端自行下载的行情数据文件。
支持 .day（日线）、.1min（1分钟线）、.5min（5分钟线）等标准通达信文件格式。
本工具不直连接、不访问、不爬取通达信官方行情服务器。
"""
import os
import struct
import glob
import pandas as pd
from datetime import datetime
from typing import Tuple, List

from app.adapters.source_adapters.kline_base import KLineSourceAdapter, normalize_config

# 通达信标准文件扩展名
TDX_EXTENSIONS = [
    '.day',    # 日线
    '.1min',   # 1分钟
    '.5min',   # 5分钟
    '.15min',  # 15分钟
    '.30min',  # 30分钟
    '.lc',     # 旧版日线
    '.dat',    # 旧版
]

# 周期 -> 文件扩展名映射
_INTERVAL_TO_EXTENSIONS = {
    "D": [".day", ".lc"],
    "1min": [".1min", ".01", ".lc1"],
    "5min": [".5min", ".5", ".lc5"],
    "15min": [".15min", ".15"],
    "30min": [".30min", ".30"],
    "60min": [".60min", ".60"],
}

# 记录字节数：所有通达信K线文件均为 32 字节/条
RECORD_SIZE = 32


class TdxAdapter(KLineSourceAdapter):
    """通达信本地数据解析适配器。

    合规说明：仅读取用户本地的通达信数据文件，不连接任何远程服务器。
    """

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        """检查本地数据目录是否存在且可读。"""
        data_dir = config.get("data_dir", "")
        if not data_dir:
            return False, "未配置本地数据目录"
        if not os.path.isdir(data_dir):
            return False, f"本地数据目录不存在: {data_dir}"
        # 按 interval 分类统计
        files_by_interval = self._count_files_by_interval(data_dir)
        total = sum(files_by_interval.values())
        if total == 0:
            return False, f"在 {data_dir} 及其子目录中未找到通达信数据文件"
        parts = []
        label_map = {"D": "日线", "1min": "1分钟", "5min": "5分钟",
                     "15min": "15分钟", "30min": "30分钟", "60min": "60分钟"}
        for interval in ["D", "1min", "5min", "15min", "30min", "60min"]:
            cnt = files_by_interval.get(interval, 0)
            if cnt > 0:
                parts.append(f"{cnt}个{label_map.get(interval, interval)}")
        return True, f"找到 {total} 个通达信数据文件（{', '.join(parts)}）"

    def _count_files_by_interval(self, data_dir: str) -> dict:
        """统计各 interval 对应的文件数量。"""
        counts = {}
        for interval, exts in _INTERVAL_TO_EXTENSIONS.items():
            cnt = 0
            for ext in exts:
                files = glob.glob(os.path.join(data_dir, f"**/*{ext}"), recursive=True)
                cnt += len(files)
            if cnt > 0:
                counts[interval] = cnt
        return counts

    def _parse_day_file(self, filepath: str) -> pd.DataFrame:
        """解析通达信 .day 日线数据文件。

        每条 32 字节，全部为 uint32 小端序：
        - date (4 bytes): YYYYMMDD
        - open (4 bytes): 价格*100
        - high (4 bytes): 价格*100
        - low (4 bytes): 价格*100
        - close (4 bytes): 价格*100
        - amount (4 bytes): 成交额
        - vol (4 bytes): 成交量
        - reserved (4 bytes): 保留字段
        """
        rows = []
        file_size = os.path.getsize(filepath)
        if file_size % RECORD_SIZE != 0:
            return pd.DataFrame()
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            for i in range(0, len(data), RECORD_SIZE):
                rec = data[i:i+RECORD_SIZE]
                date_int, open_p, high_p, low_p, close_p, amount, vol, _ = struct.unpack("<8I", rec)
                if date_int < 19900101 or date_int > 20991231:
                    continue
                year = date_int // 10000
                month = (date_int // 100) % 100
                day = date_int % 100
                if month < 1 or month > 12 or day < 1 or day > 31:
                    continue
                rows.append({
                    "datetime": datetime(year, month, day),
                    "open": open_p / 100.0,
                    "high": high_p / 100.0,
                    "low": low_p / 100.0,
                    "close": close_p / 100.0,
                    "volume": vol,
                    "amount": amount,
                })
        except Exception:
            pass
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def _parse_minute_file(self, filepath: str) -> pd.DataFrame:
        """解析通达信分钟线数据文件。

        支持两种格式（均为 32 字节/条，9 个字段）：
        - .01 / .5 / .15 / .30 / .60（整数价格）：`<HHIIIIfII`
          价格存储为 实际值*100 的整数
        - .lc1 / .lc5 / .lc15 / .lc30 / .lc60（float价格）：`<HHfffffII`
          价格直接为 float 值
        """
        rows = []
        file_size = os.path.getsize(filepath)
        ext = os.path.splitext(filepath)[1].lower()
        is_lc = ext.startswith(".lc")

        rec_size = 32  # 两种格式都是 32 字节
        if file_size % rec_size != 0:
            return pd.DataFrame()

        try:
            with open(filepath, "rb") as f:
                data = f.read()

            if is_lc:
                # .lc1 / .lc5 等格式：价格直接 float
                fmt = "<HHfffffII"
                for i in range(0, len(data), rec_size):
                    rec = data[i:i+rec_size]
                    date_int, time_int, open_p, high_p, low_p, close_p, amount, vol, _ = struct.unpack(fmt, rec)
                    dt = self._parse_datetime(date_int, time_int)
                    if dt is None:
                        continue
                    rows.append({
                        "datetime": dt,
                        "open": open_p,
                        "high": high_p,
                        "low": low_p,
                        "close": close_p,
                        "volume": vol,
                        "amount": amount,
                    })
            else:
                # .01 / .5 等格式：价格*100 的整数
                fmt = "<HHIIIIfII"
                for i in range(0, len(data), rec_size):
                    rec = data[i:i+rec_size]
                    date_int, time_int, open_p, high_p, low_p, close_p, amount, vol, _ = struct.unpack(fmt, rec)
                    dt = self._parse_datetime(date_int, time_int)
                    if dt is None:
                        continue
                    rows.append({
                        "datetime": dt,
                        "open": open_p / 100.0,
                        "high": high_p / 100.0,
                        "low": low_p / 100.0,
                        "close": close_p / 100.0,
                        "volume": vol,
                        "amount": amount,
                    })
        except Exception:
            pass
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    @staticmethod
    def _parse_datetime(date_int: int, time_int: int) -> datetime:
        """将通达信分钟线文件的日期和时间字段转为 datetime。

        使用与 tdxpy 一致的公式：
        date_int: year = num//2048+2004, month = (num%2048)//100, day = (num%2048)%100
        time_int: hour = num//60, minute = num%60
        """
        try:
            year = date_int // 2048 + 2004
            month = (date_int % 2048) // 100
            day = (date_int % 2048) % 100
            hour = time_int // 60
            minute = time_int % 60

            if year < 1990 or year > 2099 or month < 1 or month > 12 or day < 1 or day > 31:
                return None
            if hour > 23 or minute > 59:
                return None
            return datetime(year, month, day, hour, minute)
        except Exception:
            return None

    def _scan_tdx_files(self, data_dir: str, interval: str = "D") -> dict:
        """递归扫描通达信数据文件，按股票代码分组。

        根据 interval 参数只匹配对应的文件扩展名。
        """
        exts = _INTERVAL_TO_EXTENSIONS.get(interval, _INTERVAL_TO_EXTENSIONS["D"])
        files_by_code = {}
        for ext in exts:
            for fpath in glob.glob(os.path.join(data_dir, f"**/*{ext}"), recursive=True):
                fname = os.path.basename(fpath).lower()
                # 去掉扩展名，保留代码部分（如 sh000001, sz000001）
                code = fname[:-len(ext)]
                files_by_code.setdefault(code, []).append(fpath)
        return files_by_code

    def fetch_kline(self, config: dict, codes: list, start_time: datetime,
                    end_time: datetime, interval: str = "D") -> pd.DataFrame:
        """从本地数据文件读取 K 线数据。

        仅读取用户本地的通达信数据文件，不连接任何远程服务器。
        根据 interval 参数选择对应格式的文件并正确解析。
        """
        data_dir = config.get("data_dir", "")
        if not data_dir or not os.path.isdir(data_dir):
            raise ValueError(f"本地数据目录不存在或不可访问: {data_dir}")

        # 兼容 interval 别名
        interval_map = {"1m": "1min", "5m": "5min", "15m": "15min",
                        "30m": "30min", "60m": "60min", "1h": "60min",
                        "daily": "D", "day": "D"}
        interval = interval_map.get(interval, interval)

        files_by_code = self._scan_tdx_files(data_dir, interval)

        all_rows = []
        for code in codes:
            code_lower = code.lower()
            # 匹配：先试带前缀的，再试纯代码
            matched = []
            for prefix in ["sh", "sz", "bj"]:
                key = f"{prefix}{code_lower}"
                if key in files_by_code:
                    matched = files_by_code[key]
                    break
            if not matched:
                if code_lower in files_by_code:
                    matched = files_by_code[code_lower]
            if not matched:
                continue

            for fpath in sorted(matched):
                ext = os.path.splitext(fpath)[1].lower()
                if ext in (".day", ".lc", ".dat"):
                    df = self._parse_day_file(fpath)
                else:
                    df = self._parse_minute_file(fpath)
                if df.empty:
                    continue
                df["code"] = code_lower
                if start_time and end_time:
                    df = df[(df["datetime"] >= start_time) & (df["datetime"] <= end_time)]
                all_rows.append(df)

        if not all_rows:
            return pd.DataFrame()

        result = pd.concat(all_rows, ignore_index=True)
        result.sort_values("datetime", inplace=True)
        result.reset_index(drop=True, inplace=True)
        return result

    def list_codes(self, config: dict) -> list:
        """从本地数据文件扫描股票代码列表。"""
        data_dir = config.get("data_dir", "")
        if not data_dir or not os.path.isdir(data_dir):
            return []

        # 扫描所有 interval 类型
        files_by_code = {}
        for interval, exts in _INTERVAL_TO_EXTENSIONS.items():
            for ext in exts:
                for fpath in glob.glob(os.path.join(data_dir, f"**/*{ext}"), recursive=True):
                    fname = os.path.basename(fpath).lower()
                    code = fname[:-len(ext)]
                    files_by_code.setdefault(code, []).append(fpath)

        codes = []
        for code, fpaths in files_by_code.items():
            # 统计各类型文件数量
            ext_counts = {}
            for fp in fpaths:
                ext = os.path.splitext(fp)[1].lower()
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
            codes.append({
                "code": code.replace("sh", "").replace("sz", "").replace("bj", ""),
                "name": code,
                "market": 1 if code.startswith("sh") else (2 if code.startswith("bj") else 0),
                "file_count": len(fpaths),
                "intervals": list(ext_counts.keys()),
            })
        return codes
