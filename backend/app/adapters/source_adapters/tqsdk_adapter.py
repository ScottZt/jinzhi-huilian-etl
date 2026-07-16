"""天勤量化 TqSdk 全市场数据源适配器。

支持市场：
- 期货：中金所(CFFEX)、上期所(SHFE)、大商所(DCE)、郑商所(CZCE)、能源中心(INE)
- A股：上交所(SSE)、深交所(SZSE)
- 基金：ETF/LOF
- 指数：大盘指数
- 期权：天勤自动识别的期权合约

前提：
- 需要天勤账号（免费注册 https://www.shinnytech.com）
- 通过凭证系统(tqsdk_auth)或直接配置 tqsdk_user/tqsdk_password 提供账号

符号约定：
  期货：IF0(主力连续)、IF2506(具体合约)、KQ.m@CFFEX.IF(天勤格式)
  股票：000001(平安银行)、600000(浦发银行)
  指数：000001(上证指数，通过 market_type=index 区分)
  基金：510050(50ETF)
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime
from typing import Tuple

import pandas as pd

from app.adapters.source_adapters.kline_base import KLineSourceAdapter, normalize_config

logger = logging.getLogger("TqsdkAdapter")

# ── 期货品种代码 → 交易所前缀 ──────────────────────────────────────────

_TQ_EXCHANGE_PREFIX = {
    # 中金所 CFFEX
    "IF": "CFFEX.", "IC": "CFFEX.", "IH": "CFFEX.", "IM": "CFFEX.",
    "T":  "CFFEX.", "TF": "CFFEX.", "TS": "CFFEX.",
    # 上期所 SHFE
    "rb": "SHFE.", "RB": "SHFE.", "cu": "SHFE.", "CU": "SHFE.",
    "al": "SHFE.", "AL": "SHFE.", "zn": "SHFE.", "ZN": "SHFE.",
    "pb": "SHFE.", "PB": "SHFE.", "ni": "SHFE.", "NI": "SHFE.",
    "sn": "SHFE.", "SN": "SHFE.", "au": "SHFE.", "AU": "SHFE.",
    "ag": "SHFE.", "AG": "SHFE.", "ru": "SHFE.", "RU": "SHFE.",
    "fu": "SHFE.", "FU": "SHFE.", "bu": "SHFE.", "BU": "SHFE.",
    "hc": "SHFE.", "HC": "SHFE.", "ss": "SHFE.", "SS": "SHFE.",
    "sp": "SHFE.", "SP": "SHFE.", "ao": "SHFE.", "AO": "SHFE.",
    # 大商所 DCE
    "m":  "DCE.",  "M":  "DCE.",  "y":  "DCE.",  "Y":  "DCE.",
    "a":  "DCE.",  "A":  "DCE.",  "c":  "DCE.",  "C":  "DCE.",
    "cs": "DCE.",  "CS": "DCE.",  "jd": "DCE.",  "JD": "DCE.",
    "p":  "DCE.",  "P":  "DCE.",  "l":  "DCE.",  "L":  "DCE.",
    "v":  "DCE.",  "V":  "DCE.",  "pp": "DCE.",  "PP": "DCE.",
    "j":  "DCE.",  "J":  "DCE.",  "jm": "DCE.",  "JM": "DCE.",
    "i":  "DCE.",  "I":  "DCE.",  "eg": "DCE.",  "EG": "DCE.",
    "eb": "DCE.",  "EB": "DCE.",  "pg": "DCE.",  "PG": "DCE.",
    "lh": "DCE.",  "LH": "DCE.",
    # 郑商所 CZCE
    "SR": "CZCE.", "sr": "CZCE.", "CF": "CZCE.", "cf": "CZCE.",
    "CY": "CZCE.", "cy": "CZCE.", "TA": "CZCE.", "ta": "CZCE.",
    "MA": "CZCE.", "ma": "CZCE.", "OI": "CZCE.", "oi": "CZCE.",
    "RM": "CZCE.", "rm": "CZCE.", "FG": "CZCE.", "fg": "CZCE.",
    "SA": "CZCE.", "sa": "CZCE.", "UR": "CZCE.", "ur": "CZCE.",
    "AP": "CZCE.", "ap": "CZCE.", "CJ": "CZCE.", "cj": "CZCE.",
    "SF": "CZCE.", "sf": "CZCE.", "SM": "CZCE.", "sm": "CZCE.",
    "PK": "CZCE.", "pk": "CZCE.", "PF": "CZCE.", "pf": "CZCE.",
    "SH": "CZCE.", "sh": "CZCE.", "PX": "CZCE.", "px": "CZCE.",
    # 能源中心 INE
    "sc": "INE.",  "SC": "INE.",  "nr": "INE.",  "NR": "INE.",
    "lu": "INE.",  "LU": "INE.",  "bc": "INE.",  "BC": "INE.",
    "ec": "INE.",  "EC": "INE.",
}

# 品种代码 → 天勤规范大小写
_TQ_VARIETY_CASE = {
    # CFFEX - 全大写
    "IF": "IF", "IC": "IC", "IH": "IH", "IM": "IM",
    "T": "T", "TF": "TF", "TS": "TS",
    # SHFE - 全小写
    "RB": "rb", "CU": "cu", "AL": "al", "ZN": "zn",
    "PB": "pb", "NI": "ni", "SN": "sn", "AU": "au",
    "AG": "ag", "RU": "ru", "FU": "fu", "BU": "bu",
    "HC": "hc", "SS": "ss", "SP": "sp", "AO": "ao",
    # DCE - 全小写
    "A": "a", "M": "m", "Y": "y", "C": "c",
    "CS": "cs", "JD": "jd", "P": "p", "L": "l",
    "V": "v", "PP": "pp", "J": "j", "JM": "jm",
    "I": "i", "EG": "eg", "EB": "eb", "PG": "pg",
    "LH": "lh",
    # CZCE - 全大写
    "SR": "SR", "CF": "CF", "CY": "CY", "TA": "TA",
    "MA": "MA", "OI": "OI", "RM": "RM", "FG": "FG",
    "SA": "SA", "UR": "UR", "AP": "AP", "CJ": "CJ",
    "SF": "SF", "SM": "SM", "PK": "PK", "PF": "PF",
    "SH": "SH", "PX": "PX",
    # INE - 全小写
    "SC": "sc", "NR": "nr", "LU": "lu", "BC": "bc",
    "EC": "ec",
}

# K线周期（秒）
_TQ_DURATION = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "60min": 3600,
}


# ── 符号转换 ─────────────────────────────────────────────────────────────

def _extract_variety(code: str) -> str:
    """提取合约代码中的品种字母前缀。"""
    prefix = ""
    for ch in code:
        if ch.isalpha():
            prefix += ch
        else:
            break
    return prefix.lower()


def _is_stock_code(code: str) -> bool:
    """判断是否为 A 股 6 位数字代码。"""
    code = str(code).strip()
    return bool(re.match(r"^\d{6}$", code))


def _normalize_stock_symbol(code: str) -> str:
    """
    将 A 股代码转换为天勤格式。

    600xxx/601xxx/603xxx/688xxx → SSE.xxx（上交所）
    000xxx/001xxx/002xxx/003xxx/300xxx/301xxx → SZSE.xxx（深交所）
    """
    code = str(code).strip()
    if code.startswith(("6",)):
        return f"SSE.{code}"
    if code.startswith(("0", "3")):
        return f"SZSE.{code}"
    if code.startswith(("5", "1")):
        # ETF/基金：51xxxx 上交所，15xxxx/16xxxx 深交所
        if code.startswith("5"):
            return f"SSE.{code}"
        return f"SZSE.{code}"
    raise ValueError(f"无法识别 A 股代码交易所归属: {code}")


def _normalize_to_tqsdk_symbol(code: str, market_type: str = "auto") -> str:
    """
    将系统合约代码转换为天勤格式。

    支持期货和股票市场。market_type 为 auto 时自动识别。
    """
    code = str(code or "").strip()
    if not code:
        raise ValueError("空合约代码")

    # 已经是天勤格式（SSE.xxx / SZSE.xxx / KQ.m@xxx）直接返回
    if code.upper().startswith(("SSE.", "SZSE.")):
        return code
    if code.upper().startswith(("KQ.M@", "KQ.S@")):
        return code

    # 按市场类型分发
    if market_type == "stock":
        return _normalize_stock_symbol(code)

    if market_type == "index":
        return _normalize_stock_symbol(code)

    if market_type == "fund":
        return _normalize_stock_symbol(code)

    if market_type == "option":
        # 期权代码通常以天勤格式传入，如 CFFEX.IO2404-C-4000
        if "." in code:
            return code
        raise ValueError(f"期权代码请使用天勤格式，如 CFFEX.IO2404-C-4000: {code}")

    # auto 模式：尝试自动识别
    # 纯数字6位 → A股
    if _is_stock_code(code):
        return _normalize_stock_symbol(code)

    # 期货相关处理
    return _normalize_futures_symbol(code)


def _normalize_futures_symbol(code: str) -> str:
    """将期货合约代码转换为天勤格式。"""
    code = str(code or "").strip()
    if not code:
        raise ValueError("空合约代码")

    # 已经是天勤格式，直接放行
    if code.upper().startswith(("KQ.M@", "KQ.S@")):
        return code

    # 去掉系统交易所后缀
    for ex in ("CFF", "CFFEX", "SHFE", "DCE", "CZCE", "INE", "GFEX", "GFE"):
        suffix = f".{ex}"
        if code.upper().endswith(suffix):
            code = code[:-len(suffix)]
            break

    code_upper = code.upper()
    variety = _extract_variety(code_upper)
    if not variety:
        raise ValueError(f"无法解析合约代码: {code}")

    tail = code_upper[len(variety):]

    # 确定天勤交易所前缀
    tq_prefix = ""
    for key, prefix in _TQ_EXCHANGE_PREFIX.items():
        if code.startswith(key):
            tq_prefix = prefix
            break
    if not tq_prefix:
        for key, prefix in _TQ_EXCHANGE_PREFIX.items():
            if code_upper.startswith(key.upper()):
                tq_prefix = prefix
                break

    if not tq_prefix:
        raise ValueError(f"无法确定交易所: {code}")

    tq_variety = _TQ_VARIETY_CASE.get(variety.upper(), variety)

    # 主力连续合约
    if not tail or tail in ("0", "000", "0000", "888", "999"):
        return f"KQ.m@{tq_prefix}{tq_variety}"

    return f"{tq_prefix}{tq_variety}{tail}"


# ── 适配器 ───────────────────────────────────────────────────────────────

class TqsdkAdapter(KLineSourceAdapter):
    """天勤量化 TqSdk 全市场数据源适配器。"""

    def __init__(self):
        self._api = None
        self._api_lock = threading.Lock()
        self._last_error = ""

    def _get_credentials(self, config: dict) -> Tuple[str, str]:
        """从配置或凭证中提取天勤账号。"""
        user = str(config.get("tqsdk_user", "") or "").strip()
        password = str(config.get("tqsdk_password", "") or "").strip()
        return user, password

    def _ensure_api(self, config: dict) -> bool:
        """确保 TqSdk API 已连接。带线程超时保护，避免阻塞。"""
        # 屏蔽天勤 SDK 的冗余日志
        import logging
        logging.getLogger("tqsdk").setLevel(logging.WARNING)

        with self._api_lock:
            if self._api is not None:
                return True

            user, password = self._get_credentials(config)
            if not user or not password:
                self._last_error = "天勤账号未配置（请通过凭证系统或直接配置 tqsdk_user/tqsdk_password）"
                return False

            try:
                from tqsdk import TqApi, TqAuth

                api_holder = [None]
                error_holder = [None]

                def _connect():
                    try:
                        api_holder[0] = TqApi(auth=TqAuth(user, password))
                    except Exception as e:
                        error_holder[0] = e

                timeout = int(config.get("timeout", 15) or 15)
                thread = threading.Thread(target=_connect, daemon=True)
                thread.start()
                thread.join(timeout=timeout)

                if thread.is_alive():
                    self._last_error = f"天勤连接超时（{timeout}秒）"
                    return False

                if error_holder[0] is not None:
                    self._last_error = f"天勤连接失败: {error_holder[0]}"
                    return False

                self._api = api_holder[0]
                return self._api is not None

            except Exception as e:
                self._last_error = f"天勤连接异常: {e}"
                return False

    def _close_api(self):
        """关闭天勤连接。"""
        with self._api_lock:
            if self._api is not None:
                try:
                    self._api.close()
                except Exception:
                    pass
                self._api = None

    def _normalize_df(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """将天勤 kline DataFrame 标准化为系统统一格式。"""
        if df is None or (hasattr(df, "empty") and bool(df.empty)):
            return pd.DataFrame()

        work = pd.DataFrame(df).copy()
        if work.empty:
            return pd.DataFrame()

        # 字段映射：天勤 → 系统标准
        col_mapping = {}
        for src, dst in [
            ("datetime", "dt"), ("date", "dt"), ("trade_time", "dt"),
            ("open", "open"), ("high", "high"), ("low", "low"),
            ("close", "close"), ("volume", "vol"), ("amount", "amount"),
        ]:
            if src in work.columns and dst not in work.columns:
                col_mapping[src] = dst
        work = work.rename(columns=col_mapping)

        if "code" not in work.columns:
            work["code"] = str(code).strip()
        if "amount" not in work.columns:
            work["amount"] = 0.0
        if "vol" not in work.columns:
            work["vol"] = 0.0

        for c in ["open", "high", "low", "close", "vol", "amount"]:
            if c in work.columns:
                work[c] = pd.to_numeric(work[c], errors="coerce")

        if "dt" in work.columns:
            work["dt"] = pd.to_datetime(work["dt"], errors="coerce")

        required = ["code", "dt", "open", "high", "low", "close", "vol", "amount"]
        available = [c for c in required if c in work.columns]
        work = work[available].dropna(subset=["dt", "open", "high", "low", "close"])
        work = work.sort_values("dt").drop_duplicates(subset=["dt"]).reset_index(drop=True)
        return work

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        """测试天勤连通性。"""
        config = normalize_config(config)
        user, password = self._get_credentials(config)
        if not user or not password:
            return False, "天勤账号未配置（请通过凭证系统或直接配置 tqsdk_user/tqsdk_password）"

        try:
            from tqsdk import TqApi, TqAuth
        except ImportError:
            return False, "tqsdk 库未安装，请执行: pip install tqsdk"

        # 根据市场类型选择探测合约
        market_type = str(config.get("market_type", "auto")).strip().lower()
        if market_type in ("stock", "index", "fund"):
            probe_symbol = "SSE.000001"  # 上证指数
        else:
            probe_symbol = "KQ.m@CFFEX.IF"  # 股指期货主力

        start = time.perf_counter()
        api = None
        try:
            api = TqApi(auth=TqAuth(user, password))
            klines = api.get_kline_serial(probe_symbol, 60, data_length=5)
            deadline = time.time() + 10
            while True:
                if not klines.empty and pd.notna(klines.iloc[-1].get("datetime")):
                    break
                if not api.wait_update(deadline=deadline):
                    break

            df = self._normalize_df(klines.copy(), probe_symbol)
            elapsed = time.perf_counter() - start

            if not df.empty:
                return True, f"天勤连接成功 [{probe_symbol}]，返回 {len(df)} 条数据，耗时 {elapsed:.2f}s"
            return False, f"天勤连接成功但数据为空 [{probe_symbol}]"

        except Exception as e:
            return False, f"天勤连接失败: {e}"
        finally:
            if api is not None:
                try:
                    api.close()
                except Exception:
                    pass

    def fetch_kline(
        self,
        config: dict,
        codes: list,
        start_time: datetime,
        end_time: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        """拉取 K 线数据。"""
        config = normalize_config(config)
        target_codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
        if not target_codes:
            return pd.DataFrame()

        market_type = str(config.get("market_type", "auto")).strip().lower()
        is_daily = str(interval).strip().lower() in ("d", "1d", "day", "daily")

        if not self._ensure_api(config):
            logger.warning("天勤 API 初始化失败: %s", self._last_error)
            return pd.DataFrame()

        # 计算请求数据量
        duration = _TQ_DURATION.get(str(interval).strip().lower(), 60)
        if is_daily:
            duration = 86400
        try:
            total_seconds = (end_time - start_time).total_seconds()
            data_length = max(200, int(total_seconds / duration) + 100)
        except Exception:
            data_length = 2000
        data_length = min(data_length, int(config.get("data_length", 8000) or 8000))

        merged_frames = []
        try:
            for code in target_codes:
                try:
                    tq_sym = _normalize_to_tqsdk_symbol(code, market_type)
                except ValueError as e:
                    logger.warning("合约符号不识别 %s: %s", code, e)
                    continue

                try:
                    klines = self._api.get_kline_serial(tq_sym, duration, data_length=data_length)

                    # 等待数据就绪
                    deadline = time.time() + 30
                    while True:
                        if not klines.empty and pd.notna(klines.iloc[-1].get("datetime")):
                            break
                        if not self._api.wait_update(deadline=deadline):
                            break

                    df = self._normalize_df(klines.copy(), code)
                    if df.empty:
                        continue

                    # 按时间范围过滤
                    df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
                    df = df.dropna(subset=["dt"])
                    df = df[(df["dt"] >= start_time) & (df["dt"] <= end_time)]

                    if not df.empty:
                        merged_frames.append(df)

                except Exception as e:
                    logger.warning("天勤获取 %s 失败: %s", tq_sym, e)
                    continue

            if not merged_frames:
                return pd.DataFrame()

            result = pd.concat(merged_frames, ignore_index=True)
            result = result.sort_values(["code", "dt"]).drop_duplicates(
                subset=["code", "dt"], keep="last"
            ).reset_index(drop=True)
            return result

        except Exception as e:
            self._last_error = f"天勤获取K线失败: {e}"
            logger.error("天勤批量获取异常: %s", e)
            return pd.DataFrame()

    def list_codes(self, config: dict) -> list:
        """返回常用合约代码列表（期货主力 + 热门股票）。"""
        config = normalize_config(config)
        market_type = str(config.get("market_type", "auto")).strip().lower()

        codes = []
        if market_type in ("futures", "auto"):
            # 常见期货主力合约
            futures_codes = [
                {"code": "IF0", "name": "沪深300主力", "market": "CFFEX"},
                {"code": "IC0", "name": "中证500主力", "market": "CFFEX"},
                {"code": "IH0", "name": "上证50主力", "market": "CFFEX"},
                {"code": "IM0", "name": "中证1000主力", "market": "CFFEX"},
                {"code": "T0", "name": "10年国债主力", "market": "CFFEX"},
                {"code": "TF0", "name": "5年国债主力", "market": "CFFEX"},
                {"code": "TS0", "name": "2年国债主力", "market": "CFFEX"},
                {"code": "rb0", "name": "螺纹钢主力", "market": "SHFE"},
                {"code": "cu0", "name": "铜主力", "market": "SHFE"},
                {"code": "al0", "name": "铝主力", "market": "SHFE"},
                {"code": "zn0", "name": "锌主力", "market": "SHFE"},
                {"code": "au0", "name": "黄金主力", "market": "SHFE"},
                {"code": "ag0", "name": "白银主力", "market": "SHFE"},
                {"code": "hc0", "name": "热轧卷板主力", "market": "SHFE"},
                {"code": "ni0", "name": "镍主力", "market": "SHFE"},
                {"code": "ru0", "name": "橡胶主力", "market": "SHFE"},
                {"code": "fu0", "name": "燃料油主力", "market": "SHFE"},
                {"code": "bu0", "name": "沥青主力", "market": "SHFE"},
                {"code": "sp0", "name": "纸浆主力", "market": "SHFE"},
                {"code": "ss0", "name": "不锈钢主力", "market": "SHFE"},
                {"code": "a0", "name": "豆一主力", "market": "DCE"},
                {"code": "m0", "name": "豆粕主力", "market": "DCE"},
                {"code": "y0", "name": "豆油主力", "market": "DCE"},
                {"code": "p0", "name": "棕榈油主力", "market": "DCE"},
                {"code": "c0", "name": "玉米主力", "market": "DCE"},
                {"code": "jd0", "name": "鸡蛋主力", "market": "DCE"},
                {"code": "l0", "name": "塑料主力", "market": "DCE"},
                {"code": "v0", "name": "PVC主力", "market": "DCE"},
                {"code": "pp0", "name": "聚丙烯主力", "market": "DCE"},
                {"code": "j0", "name": "焦炭主力", "market": "DCE"},
                {"code": "jm0", "name": "焦煤主力", "market": "DCE"},
                {"code": "i0", "name": "铁矿石主力", "market": "DCE"},
                {"code": "eg0", "name": "乙二醇主力", "market": "DCE"},
                {"code": "eb0", "name": "苯乙烯主力", "market": "DCE"},
                {"code": "pg0", "name": "液化石油气主力", "market": "DCE"},
                {"code": "lh0", "name": "生猪主力", "market": "DCE"},
                {"code": "SR0", "name": "白糖主力", "market": "CZCE"},
                {"code": "CF0", "name": "棉花主力", "market": "CZCE"},
                {"code": "TA0", "name": "PTA主力", "market": "CZCE"},
                {"code": "MA0", "name": "甲醇主力", "market": "CZCE"},
                {"code": "OI0", "name": "菜油主力", "market": "CZCE"},
                {"code": "RM0", "name": "菜粕主力", "market": "CZCE"},
                {"code": "FG0", "name": "玻璃主力", "market": "CZCE"},
                {"code": "SA0", "name": "纯碱主力", "market": "CZCE"},
                {"code": "UR0", "name": "尿素主力", "market": "CZCE"},
                {"code": "AP0", "name": "苹果主力", "market": "CZCE"},
                {"code": "sc0", "name": "原油主力", "market": "INE"},
                {"code": "nr0", "name": "20号胶主力", "market": "INE"},
                {"code": "lu0", "name": "低硫燃料油主力", "market": "INE"},
            ]
            codes.extend(futures_codes)

        if market_type in ("stock", "auto"):
            # 热门 A 股
            stock_codes = [
                {"code": "000001", "name": "平安银行", "market": "SZSE"},
                {"code": "000002", "name": "万科A", "market": "SZSE"},
                {"code": "000858", "name": "五粮液", "market": "SZSE"},
                {"code": "002594", "name": "比亚迪", "market": "SZSE"},
                {"code": "300750", "name": "宁德时代", "market": "SZSE"},
                {"code": "600000", "name": "浦发银行", "market": "SSE"},
                {"code": "600036", "name": "招商银行", "market": "SSE"},
                {"code": "600519", "name": "贵州茅台", "market": "SSE"},
                {"code": "601318", "name": "中国平安", "market": "SSE"},
                {"code": "601899", "name": "紫金矿业", "market": "SSE"},
                {"code": "688981", "name": "中芯国际", "market": "SSE"},
            ]
            codes.extend(stock_codes)

        if market_type in ("index", "auto"):
            index_codes = [
                {"code": "SSE.000001", "name": "上证指数", "market": "SSE"},
                {"code": "SZSE.399001", "name": "深证成指", "market": "SZSE"},
                {"code": "SZSE.399006", "name": "创业板指", "market": "SZSE"},
                {"code": "SSE.000300", "name": "沪深300指数", "market": "SSE"},
                {"code": "SSE.000905", "name": "中证500指数", "market": "SSE"},
                {"code": "SSE.000852", "name": "中证1000指数", "market": "SSE"},
            ]
            codes.extend(index_codes)

        if market_type in ("fund", "auto"):
            fund_codes = [
                {"code": "510050", "name": "50ETF", "market": "SSE"},
                {"code": "510300", "name": "300ETF", "market": "SSE"},
                {"code": "510500", "name": "500ETF", "market": "SSE"},
                {"code": "159919", "name": "沪深300ETF", "market": "SZSE"},
                {"code": "159915", "name": "创业板ETF", "market": "SZSE"},
            ]
            codes.extend(fund_codes)

        return codes
