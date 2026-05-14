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
from pathlib import Path

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

# 记录字节数：标准 .day / .1min / .5min 均为 32 字节/条
RECORD_SIZE = 32


class TdxAdapter(KLineSourceAdapter):
    """通达信本地数据文件解析适配器。

    合规说明：仅读取用户本地的通达信数据文件，不连接任何远程服务器。
    """

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        """检查本地数据目录是否存在且可读。"""
        data_dir = config.get("data_dir", "")
        if not data_dir:
            return False, "未配置本地数据目录"
        if not os.path.isdir(data_dir):
            return False, f"本地数据目录不存在: {data_dir}"
        # 扫描所有通达信标准文件
        file_count = 0
        for ext in TDX_EXTENSIONS:
            files = glob.glob(os.path.join(data_dir, f"**/*{ext}"), recursive=True)
            file_count += len(files)
        if file_count == 0:
            return False, f"在 {data_dir} 及其子目录中未找到通达信数据文件（.day / .1min / .5min 等）"
        return True, f"找到 {file_count} 个通达信数据文件"

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
                    continue  # 跳过无效记录
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
        except Exception as e:
            pass  # 返回已读取的部数据
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def _scan_tdx_files(self, data_dir: str) -> dict:
        """递归扫描所有通达信数据文件，按股票代码分组。"""
        files_by_code = {}
        for ext in TDX_EXTENSIONS:
            for fpath in glob.glob(os.path.join(data_dir, f"**/*{ext}"), recursive=True):
                fname = os.path.basename(fpath).lower()
                # 去掉扩展名，保留代码部分（如 sh000001, sz000001）
                for e in TDX_EXTENSIONS:
                    if fname.endswith(e):
                        code = fname[:-len(e)]
                        break
                else:
                    continue
                files_by_code.setdefault(code, []).append(fpath)
        return files_by_code

    def fetch_kline(self, config: dict, codes: list, start_time: datetime,
                    end_time: datetime, interval: str = "1min") -> pd.DataFrame:
        """从本地数据文件读取 K 线数据。

        仅读取用户本地的通达信数据文件，不连接任何远程服务器。
        """
        data_dir = config.get("data_dir", "")
        if not data_dir or not os.path.isdir(data_dir):
            raise ValueError(f"本地数据目录不存在或不可访问: {data_dir}")

        files_by_code = self._scan_tdx_files(data_dir)

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
                # 尝试纯代码名（不带市场前缀）
                if code_lower in files_by_code:
                    matched = files_by_code[code_lower]
            if not matched:
                continue

            for fpath in sorted(matched):
                df = self._parse_day_file(fpath)
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

        files_by_code = self._scan_tdx_files(data_dir)
        codes = []
        for code, fpaths in files_by_code.items():
            codes.append({
                "code": code.replace("sh", "").replace("sz", "").replace("bj", ""),
                "name": code,
                "market": 1 if code.startswith("sh") else (2 if code.startswith("bj") else 0),
                "file_count": len(fpaths),
            })
        return codes
