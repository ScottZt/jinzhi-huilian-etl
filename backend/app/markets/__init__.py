"""国内期货品种规格注册表。

覆盖六大交易所全品种，提供：
- 品种代码 → 交易所/中文名/合约乘数/保证金率 等规格
- 合约代码 → 品种前缀提取、规格解析
- 全品种前缀列表查询

数据来源：各交易所官网合约规格公告。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


_PRODUCT_SPECS: Dict[str, Dict[str, Any]] = {
    # ── 中金所 CFFEX ──
    "IF": {"exchange": "CFFEX", "name": "沪深300股指", "multiplier": 300, "margin_rate": 0.12, "tick_size": 0.2},
    "IC": {"exchange": "CFFEX", "name": "中证500股指", "multiplier": 200, "margin_rate": 0.14, "tick_size": 0.2},
    "IH": {"exchange": "CFFEX", "name": "上证50股指", "multiplier": 300, "margin_rate": 0.12, "tick_size": 0.2},
    "IM": {"exchange": "CFFEX", "name": "中证1000股指", "multiplier": 200, "margin_rate": 0.16, "tick_size": 0.2},
    "T":  {"exchange": "CFFEX", "name": "10年期国债", "multiplier": 10000, "margin_rate": 0.02, "tick_size": 0.005},
    "TF": {"exchange": "CFFEX", "name": "5年期国债", "multiplier": 10000, "margin_rate": 0.02, "tick_size": 0.005},
    "TS": {"exchange": "CFFEX", "name": "2年期国债", "multiplier": 20000, "margin_rate": 0.01, "tick_size": 0.005},
    "TL": {"exchange": "CFFEX", "name": "30年期国债", "multiplier": 10000, "margin_rate": 0.03, "tick_size": 0.01},
    # ── 上期所 SHFE ──
    "RB": {"exchange": "SHFE", "name": "螺纹钢", "multiplier": 10, "margin_rate": 0.09, "tick_size": 1.0},
    "HC": {"exchange": "SHFE", "name": "热轧卷板", "multiplier": 10, "margin_rate": 0.09, "tick_size": 1.0},
    "CU": {"exchange": "SHFE", "name": "铜", "multiplier": 5, "margin_rate": 0.09, "tick_size": 10.0},
    "AL": {"exchange": "SHFE", "name": "铝", "multiplier": 5, "margin_rate": 0.09, "tick_size": 5.0},
    "ZN": {"exchange": "SHFE", "name": "锌", "multiplier": 5, "margin_rate": 0.09, "tick_size": 5.0},
    "PB": {"exchange": "SHFE", "name": "铅", "multiplier": 5, "margin_rate": 0.09, "tick_size": 5.0},
    "NI": {"exchange": "SHFE", "name": "镍", "multiplier": 1, "margin_rate": 0.09, "tick_size": 10.0},
    "SN": {"exchange": "SHFE", "name": "锡", "multiplier": 1, "margin_rate": 0.09, "tick_size": 10.0},
    "SS": {"exchange": "SHFE", "name": "不锈钢", "multiplier": 5, "margin_rate": 0.09, "tick_size": 5.0},
    "AU": {"exchange": "SHFE", "name": "黄金", "multiplier": 1000, "margin_rate": 0.08, "tick_size": 0.02},
    "AG": {"exchange": "SHFE", "name": "白银", "multiplier": 15, "margin_rate": 0.10, "tick_size": 1.0},
    "RU": {"exchange": "SHFE", "name": "橡胶", "multiplier": 10, "margin_rate": 0.09, "tick_size": 5.0},
    "FU": {"exchange": "SHFE", "name": "燃料油", "multiplier": 10, "margin_rate": 0.10, "tick_size": 1.0},
    "BU": {"exchange": "SHFE", "name": "石油沥青", "multiplier": 10, "margin_rate": 0.10, "tick_size": 2.0},
    "SP": {"exchange": "SHFE", "name": "纸浆", "multiplier": 10, "margin_rate": 0.09, "tick_size": 2.0},
    "AO": {"exchange": "SHFE", "name": "氧化铝", "multiplier": 20, "margin_rate": 0.09, "tick_size": 1.0},
    # ── 大商所 DCE ──
    "A":  {"exchange": "DCE", "name": "豆一", "multiplier": 10, "margin_rate": 0.07, "tick_size": 1.0},
    "M":  {"exchange": "DCE", "name": "豆粕", "multiplier": 10, "margin_rate": 0.08, "tick_size": 1.0},
    "Y":  {"exchange": "DCE", "name": "豆油", "multiplier": 10, "margin_rate": 0.08, "tick_size": 2.0},
    "P":  {"exchange": "DCE", "name": "棕榈油", "multiplier": 10, "margin_rate": 0.08, "tick_size": 2.0},
    "C":  {"exchange": "DCE", "name": "玉米", "multiplier": 10, "margin_rate": 0.07, "tick_size": 1.0},
    "CS": {"exchange": "DCE", "name": "玉米淀粉", "multiplier": 10, "margin_rate": 0.07, "tick_size": 1.0},
    "JD": {"exchange": "DCE", "name": "鸡蛋", "multiplier": 5, "margin_rate": 0.07, "tick_size": 1.0},
    "L":  {"exchange": "DCE", "name": "塑料(LLDPE)", "multiplier": 5, "margin_rate": 0.08, "tick_size": 1.0},
    "V":  {"exchange": "DCE", "name": "PVC", "multiplier": 5, "margin_rate": 0.08, "tick_size": 1.0},
    "PP": {"exchange": "DCE", "name": "聚丙烯", "multiplier": 5, "margin_rate": 0.08, "tick_size": 1.0},
    "J":  {"exchange": "DCE", "name": "焦炭", "multiplier": 100, "margin_rate": 0.13, "tick_size": 0.5},
    "JM": {"exchange": "DCE", "name": "焦煤", "multiplier": 60, "margin_rate": 0.13, "tick_size": 0.5},
    "I":  {"exchange": "DCE", "name": "铁矿石", "multiplier": 100, "margin_rate": 0.13, "tick_size": 0.5},
    "EG": {"exchange": "DCE", "name": "乙二醇", "multiplier": 10, "margin_rate": 0.08, "tick_size": 1.0},
    "EB": {"exchange": "DCE", "name": "苯乙烯", "multiplier": 5, "margin_rate": 0.08, "tick_size": 1.0},
    "PG": {"exchange": "DCE", "name": "液化石油气", "multiplier": 20, "margin_rate": 0.09, "tick_size": 1.0},
    "LH": {"exchange": "DCE", "name": "生猪", "multiplier": 16, "margin_rate": 0.09, "tick_size": 5.0},
    # ── 郑商所 CZCE ──
    "SR": {"exchange": "CZCE", "name": "白糖", "multiplier": 10, "margin_rate": 0.07, "tick_size": 1.0},
    "CF": {"exchange": "CZCE", "name": "棉花", "multiplier": 5, "margin_rate": 0.07, "tick_size": 5.0},
    "CY": {"exchange": "CZCE", "name": "棉纱", "multiplier": 5, "margin_rate": 0.07, "tick_size": 5.0},
    "TA": {"exchange": "CZCE", "name": "PTA", "multiplier": 5, "margin_rate": 0.07, "tick_size": 2.0},
    "MA": {"exchange": "CZCE", "name": "甲醇", "multiplier": 10, "margin_rate": 0.07, "tick_size": 1.0},
    "OI": {"exchange": "CZCE", "name": "菜籽油", "multiplier": 10, "margin_rate": 0.08, "tick_size": 1.0},
    "RM": {"exchange": "CZCE", "name": "菜粕", "multiplier": 10, "margin_rate": 0.07, "tick_size": 1.0},
    "FG": {"exchange": "CZCE", "name": "玻璃", "multiplier": 20, "margin_rate": 0.09, "tick_size": 1.0},
    "SA": {"exchange": "CZCE", "name": "纯碱", "multiplier": 20, "margin_rate": 0.09, "tick_size": 1.0},
    "UR": {"exchange": "CZCE", "name": "尿素", "multiplier": 20, "margin_rate": 0.08, "tick_size": 1.0},
    "AP": {"exchange": "CZCE", "name": "苹果", "multiplier": 10, "margin_rate": 0.08, "tick_size": 1.0},
    "CJ": {"exchange": "CZCE", "name": "红枣", "multiplier": 5, "margin_rate": 0.07, "tick_size": 5.0},
    "SF": {"exchange": "CZCE", "name": "硅铁", "multiplier": 5, "margin_rate": 0.09, "tick_size": 2.0},
    "SM": {"exchange": "CZCE", "name": "锰硅", "multiplier": 5, "margin_rate": 0.09, "tick_size": 2.0},
    "PK": {"exchange": "CZCE", "name": "花生", "multiplier": 5, "margin_rate": 0.07, "tick_size": 2.0},
    "PF": {"exchange": "CZCE", "name": "涤纶短纤", "multiplier": 5, "margin_rate": 0.07, "tick_size": 2.0},
    "SH": {"exchange": "CZCE", "name": "烧碱", "multiplier": 10, "margin_rate": 0.08, "tick_size": 1.0},
    "PX": {"exchange": "CZCE", "name": "对二甲苯", "multiplier": 5, "margin_rate": 0.08, "tick_size": 2.0},
    # ── 能源中心 INE ──
    "SC": {"exchange": "INE", "name": "原油", "multiplier": 1000, "margin_rate": 0.10, "tick_size": 0.1},
    "NR": {"exchange": "INE", "name": "20号胶", "multiplier": 10, "margin_rate": 0.09, "tick_size": 5.0},
    "LU": {"exchange": "INE", "name": "低硫燃料油", "multiplier": 10, "margin_rate": 0.10, "tick_size": 1.0},
    "BC": {"exchange": "INE", "name": "国际铜", "multiplier": 5, "margin_rate": 0.09, "tick_size": 10.0},
    "EC": {"exchange": "INE", "name": "集运指数(欧线)", "multiplier": 50, "margin_rate": 0.12, "tick_size": 0.1},
    # ── 广期所 GFEX ──
    "SI": {"exchange": "GFEX", "name": "工业硅", "multiplier": 5, "margin_rate": 0.09, "tick_size": 5.0},
    "LC": {"exchange": "GFEX", "name": "碳酸锂", "multiplier": 1, "margin_rate": 0.09, "tick_size": 50.0},
}

# 天勤品种代码大小写映射（品种前缀 → 天勤格式）
_TQ_VARIETY_CASE: Dict[str, str] = {
    "IF": "IF", "IC": "IC", "IH": "IH", "IM": "IM",
    "T": "T", "TF": "TF", "TS": "TS", "TL": "TL",
    "RB": "rb", "CU": "cu", "AL": "al", "ZN": "zn",
    "PB": "pb", "NI": "ni", "SN": "sn", "AU": "au",
    "AG": "ag", "RU": "ru", "FU": "fu", "BU": "bu",
    "HC": "hc", "SS": "ss", "SP": "sp", "AO": "ao",
    "A": "a", "M": "m", "Y": "y", "C": "c",
    "CS": "cs", "JD": "jd", "P": "p", "L": "l",
    "V": "v", "PP": "pp", "J": "j", "JM": "jm",
    "I": "i", "EG": "eg", "EB": "eb", "PG": "pg", "LH": "lh",
    "SR": "SR", "CF": "CF", "CY": "CY", "TA": "TA",
    "MA": "MA", "OI": "OI", "RM": "RM", "FG": "FG",
    "SA": "SA", "UR": "UR", "AP": "AP", "CJ": "CJ",
    "SF": "SF", "SM": "SM", "PK": "PK", "PF": "PF",
    "SH": "SH", "PX": "PX",
    "SC": "sc", "NR": "nr", "LU": "lu", "BC": "bc", "EC": "ec",
    "SI": "si", "LC": "lc",
}


@dataclass(frozen=True)
class ProductSpec:
    """品种规格。"""
    symbol_prefix: str
    exchange: str = ""
    name: str = ""
    multiplier: float = 1.0
    margin_rate: float = 0.0
    tick_size: float = 0.01


def _normalize(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _extract_prefix(symbol: str) -> str:
    """从合约代码中提取品种前缀（大写）。"""
    sym = _normalize(symbol)
    if not sym:
        return ""
    if sym in _PRODUCT_SPECS:
        return sym
    prefix = ""
    for ch in sym:
        if ch.isalpha():
            prefix += ch
        else:
            break
    return prefix.upper()


def get_all_prefixes() -> list[str]:
    """获取所有已注册的品种前缀（大写）。"""
    return list(_PRODUCT_SPECS.keys())


def get_all_specs() -> Dict[str, Dict[str, Any]]:
    """获取全品种规格表（原始 dict 格式）。"""
    return dict(_PRODUCT_SPECS)


def get_tq_variety_case() -> Dict[str, str]:
    """获取品种代码 → 天勤格式映射。"""
    return dict(_TQ_VARIETY_CASE)


def get_exchanges() -> list[str]:
    """获取所有已注册的交易所列表。"""
    return sorted(set(v["exchange"] for v in _PRODUCT_SPECS.values()))


def has_spec(symbol: str) -> bool:
    """检查合约是否有已知规格定义。"""
    return _extract_prefix(symbol) in _PRODUCT_SPECS


def get_product_name(symbol: str) -> str:
    """获取品种中文名。"""
    raw = _PRODUCT_SPECS.get(_extract_prefix(symbol))
    return str(raw.get("name", "")) if raw else ""


def resolve(symbol: str) -> ProductSpec:
    """根据合约代码解析品种规格，无匹配时返回默认规格。"""
    sym = _normalize(symbol)
    prefix = _extract_prefix(sym)
    raw = _PRODUCT_SPECS.get(prefix)
    if raw is not None:
        return ProductSpec(
            symbol_prefix=prefix,
            exchange=raw["exchange"],
            name=raw["name"],
            multiplier=float(raw["multiplier"]),
            margin_rate=float(raw["margin_rate"]),
            tick_size=float(raw["tick_size"]),
        )
    return ProductSpec(symbol_prefix=prefix, exchange="CN_FUT")
