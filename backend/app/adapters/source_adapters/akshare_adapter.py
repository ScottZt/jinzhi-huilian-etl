"""AkShare 直连接口适配器：通过本地 Python akshare 包直接调用，不依赖 AKTools HTTP 网关。"""
import json
import re
import time
from datetime import datetime
from typing import Tuple

import pandas as pd

from app.adapters.source_adapters.kline_base import KLineSourceAdapter, normalize_config


def _format_template_value(value, **kwargs):
    """递归替换模板变量，兼容 str/dict/list 结构。"""
    if isinstance(value, str):
        try:
            return value.format(**kwargs)
        except Exception:
            return value
    if isinstance(value, dict):
        return {k: _format_template_value(v, **kwargs) for k, v in value.items()}
    if isinstance(value, list):
        return [_format_template_value(v, **kwargs) for v in value]
    return value


def _has_unresolved_placeholders(value) -> bool:
    """检测替换后是否仍残留关键占位符。"""
    pattern = re.compile(r"\{(codes|start_time|end_time|interval)\}")
    if isinstance(value, str):
        return bool(pattern.search(value))
    if isinstance(value, dict):
        return any(_has_unresolved_placeholders(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_unresolved_placeholders(v) for v in value)
    return False


def _parse_request_template(config: dict) -> dict:
    """统一把 request_template 解析为 dict，避免字符串模板导致调用失败。"""
    req_tmpl = config.get("request_template", {})
    if isinstance(req_tmpl, str):
        raw = req_tmpl.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return req_tmpl if isinstance(req_tmpl, dict) else {}


def _normalize_interval(interval: str) -> str:
    """把调度粒度映射到 AkShare 常用 period 值。"""
    val = str(interval or "").strip().lower()
    if val in {"d", "1d", "day", "daily"}:
        return "daily"
    if val in {"w", "1w", "week", "weekly"}:
        return "weekly"
    if val in {"m", "1m", "month", "monthly"}:
        return "monthly"
    return "daily"


def _normalize_akshare_df(df: pd.DataFrame) -> pd.DataFrame:
    """将 AkShare 常见中英文字段归一到系统通用字段。"""
    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()
    # 常见字段统一：保证后续流程能稳定识别时间和 OHLCV。
    rename_map = {
        "日期": "datetime",
        "交易日期": "datetime",
        "trade_date": "datetime",
        "date": "datetime",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "vol",
        "volume": "vol",
        "成交额": "amount",
        "股票代码": "code",
        "代码": "code",
        "symbol": "code",
        "ts_code": "code",
    }
    result = result.rename(columns={k: v for k, v in rename_map.items() if k in result.columns})
    if "datetime" in result.columns:
        result["datetime"] = pd.to_datetime(result["datetime"], errors="coerce")
    return result


class HttpAdapter(KLineSourceAdapter):
    """兼容历史命名的 AkShare 适配器（类名保留 HttpAdapter，内部改为本地 SDK 直连）。"""

    def _build_call(self, config: dict, codes: list, start_time: datetime, end_time: datetime, interval: str) -> tuple:
        """构建 AkShare 函数名和参数，支持模板占位符替换。"""
        req_tmpl = _parse_request_template(config)
        func_name = str(req_tmpl.get("func", "")).strip()
        if not func_name:
            raise RuntimeError("AkShare request_template.func 不能为空")

        date_format = config.get("date_format", "%Y%m%d")
        start_str = start_time.strftime(date_format)
        end_str = end_time.strftime(date_format)
        # 对 AkShare 默认使用单代码替换；批量场景由上层循环拆分。
        code_value = str(codes[0]) if codes else "000001"
        period_value = _normalize_interval(interval)
        payload = _format_template_value(
            req_tmpl,
            start_time=start_str,
            end_time=end_str,
            codes=code_value,
            interval=period_value,
        )
        if _has_unresolved_placeholders(payload):
            raise RuntimeError(
                "AkShare 模板变量未正确替换，请确认使用 {codes}/{start_time}/{end_time}/{interval}"
            )
        if not isinstance(payload, dict):
            raise RuntimeError("AkShare request_template 必须是 JSON 对象")
        # 仅透传模板中已有参数，避免给不支持 period 的函数误传参。
        kwargs = {k: v for k, v in payload.items() if k != "func" and v not in (None, "")}
        return func_name, kwargs

    def _call_akshare(self, func_name: str, kwargs: dict) -> pd.DataFrame:
        """调用指定 AkShare 函数并将返回值归一为 DataFrame。"""
        try:
            import akshare as ak
        except Exception as e:
            raise RuntimeError(f"akshare 库不可用: {e}") from e
        func = getattr(ak, func_name, None)
        if not callable(func):
            raise RuntimeError(f"AkShare 不存在函数: {func_name}")
        # 针对上游偶发断连做轻量重试，避免一次网络抖动就判定失败。
        last_error = None
        for idx in range(3):
            try:
                data = func(**kwargs)
                if isinstance(data, pd.DataFrame):
                    return data
                if isinstance(data, list):
                    return pd.DataFrame(data)
                if isinstance(data, dict):
                    return pd.DataFrame([data])
                return pd.DataFrame()
            except Exception as e:
                last_error = e
                if idx < 2:
                    time.sleep(0.6 * (idx + 1))
                    continue
                raise RuntimeError(f"AkShare 调用失败: {e}") from e
        raise RuntimeError(f"AkShare 调用失败: {last_error}")

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        """测试 AkShare 连通性：优先验证当前模板函数可调用。"""
        config = normalize_config(config)
        try:
            # 优先按当前模板函数做一次最小调用，确保“函数+参数”都可用。
            now = datetime.now()
            func_name, kwargs = self._build_call(
                config=config,
                codes=["000001"],
                # 连通性探测使用近 30 天窗口，减少历史全量查询导致的偶发失败。
                start_time=now - pd.Timedelta(days=30),
                end_time=now,
                interval="daily",
            )
            df = self._call_akshare(func_name, kwargs)
            return True, f"AkShare 本地直连成功: func={func_name}, rows={len(df)}"
        except Exception as e:
            return False, f"AkShare 本地直连失败: {e}"

    def fetch_kline(self, config: dict, codes: list, start_time: datetime,
                    end_time: datetime, interval: str = "1min") -> pd.DataFrame:
        """拉取 AkShare 数据并标准化字段，供预览与流水线复用。"""
        config = normalize_config(config)
        target_codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
        if not target_codes:
            target_codes = ["000001"]

        merged = []
        for code in target_codes:
            # 按代码拆分调用，兼容仅支持单标的参数的 AkShare 接口。
            func_name, kwargs = self._build_call(config, [code], start_time, end_time, interval)
            df = self._call_akshare(func_name, kwargs)
            if df is None or df.empty:
                continue
            # 若接口返回中缺少代码列，则补齐当前请求代码，方便后续分组处理。
            if "代码" not in df.columns and "股票代码" not in df.columns and "code" not in df.columns:
                df["code"] = code
            merged.append(df)

        if not merged:
            return pd.DataFrame()
        result = pd.concat(merged, ignore_index=True)
        result = _normalize_akshare_df(result)

        # 保留用户自定义列映射能力，便于兼容历史配置。
        col_map_raw = config.get("column_mapping", "{}")
        try:
            col_map = json.loads(col_map_raw) if isinstance(col_map_raw, str) else col_map_raw
        except Exception:
            col_map = {}
        if isinstance(col_map, dict) and col_map:
            result = result.rename(columns=col_map)
        return result

    def list_codes(self, config: dict) -> list:
        """获取股票代码列表，优先使用 AkShare 实时行情接口。"""
        _ = normalize_config(config)
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return []
            for col in ("代码", "股票代码", "code", "symbol", "ts_code"):
                if col in df.columns:
                    return [str(v).strip() for v in df[col].tolist() if str(v).strip()]
            return []
        except Exception:
            return []
