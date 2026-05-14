"""Tushare Pro 数据源适配器 — 处理 Tushare 特有的 fields + items (list of lists) 响应格式。"""
import pandas as pd
from datetime import datetime
from typing import Tuple
import json
import re

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


def _parse_request_template(config: dict):
    """统一解析 request_template，兼容 dict/JSON 字符串。"""
    req_tmpl = config.get("request_template", {})
    if isinstance(req_tmpl, dict):
        return req_tmpl
    if isinstance(req_tmpl, str):
        raw = req_tmpl.strip()
        if raw.startswith("{"):
            try:
                return json.loads(raw)
            except Exception:
                return {}
    return {}


def _is_tushare_sdk_mode(config: dict) -> bool:
    """判断是否启用 Tushare SDK 模式（request_template.call_mode=sdk）。"""
    req_tmpl = _parse_request_template(config)
    mode = str(req_tmpl.get("call_mode", "")).strip().lower()
    return mode == "sdk"


class HttpAdapter(KLineSourceAdapter):
    """通用 HTTP/REST API 适配器。用户自行配置 base_url、headers、请求模板。

    合规说明：工具不内置任何第三方数据源连接方案，大模型仅生成代码模板，
    数据源相关的接口、Token、密钥均需用户自行填写。
    """

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        config = normalize_config(config)
        # SDK 模式下不做 HTTP 探测，改为 tushare SDK 可用性检查。
        if _is_tushare_sdk_mode(config):
            req_tmpl = _parse_request_template(config)
            token = str(req_tmpl.get("token", "")).strip()
            if (not token) or ("{" in token and "}" in token):
                return False, "Tushare SDK 模式缺少有效 token，请在 request_template.token 中填写真实值"
            try:
                import tushare as ts
            except Exception:
                return False, "Tushare SDK 模式需要安装 tushare 包（pip install tushare）"
            try:
                # 用最小查询验证 token 与网络可用性，避免仅导入成功导致误判。
                pro = ts.pro_api(token)
                now = datetime.now().strftime("%Y%m%d")
                _ = pro.query("trade_cal", start_date=now, end_date=now, fields="cal_date")
                return True, "Tushare SDK 连接成功"
            except Exception as e:
                return False, f"Tushare SDK 连接失败: {e}"

        try:
            import requests
        except Exception:
            return False, "requests 库不可用"

        base_url = config.get("base_url", "").strip()
        if not base_url:
            return False, "base_url 未配置"

        test_path = config.get("test_path", "")
        url = base_url.rstrip("/") + "/" + test_path.lstrip("/") if test_path else base_url
        headers = config.get("headers", {})
        timeout = int(config.get("timeout", 10))

        try:
            resp = requests.head(url, headers=headers, timeout=timeout)
            if resp.status_code < 500:
                return True, f"HTTP 连接成功 ({resp.status_code})"
            return False, f"服务器错误 ({resp.status_code})"
        except requests.exceptions.Timeout:
            return False, "连接超时，请检查 URL 和网络"
        except requests.exceptions.ConnectionError:
            return False, "连接失败，请检查 URL 是否正确"
        except Exception as e:
            return False, str(e)

    def fetch_kline(self, config: dict, codes: list, start_time: datetime,
                    end_time: datetime, interval: str = "1min") -> pd.DataFrame:
        config = normalize_config(config)
        # SDK 模式：通过 tushare Python 包直接请求，无需 HTTP base_url。
        if _is_tushare_sdk_mode(config):
            req_tmpl = _parse_request_template(config)
            start_str = start_time.strftime(config.get("date_format", "%Y%m%d"))
            end_str = end_time.strftime(config.get("date_format", "%Y%m%d"))
            codes_str = ",".join(codes) if codes else ""
            try:
                params_obj = req_tmpl.get("params", {})
                if not isinstance(params_obj, dict):
                    params_obj = {}
                params_obj = _format_template_value(
                    params_obj,
                    start_time=start_str,
                    end_time=end_str,
                    codes=codes_str,
                    interval=interval,
                )
                if ("ts_code" not in params_obj) and codes_str:
                    params_obj["ts_code"] = codes_str
                params_obj.setdefault("start_date", start_str)
                params_obj.setdefault("end_date", end_str)
                api_name = str(req_tmpl.get("api_name", "trade_cal")).strip()
                token = str(req_tmpl.get("token", "")).strip()
                fields = str(req_tmpl.get("fields", "")).strip()
                if (not token) or ("{" in token and "}" in token):
                    raise RuntimeError("Tushare SDK 模式缺少有效 token")
                import tushare as ts
                pro = ts.pro_api(token)
                # 优先走 query 通用调用，失败时回退到同名方法调用。
                try:
                    if fields:
                        df = pro.query(api_name, **params_obj, fields=fields)
                    else:
                        df = pro.query(api_name, **params_obj)
                except Exception:
                    fn = getattr(pro, api_name, None)
                    if not callable(fn):
                        raise
                    if fields:
                        df = fn(**params_obj, fields=fields)
                    else:
                        df = fn(**params_obj)
                if df is None:
                    return pd.DataFrame()
                if not isinstance(df, pd.DataFrame):
                    df = pd.DataFrame(df)
            except Exception as e:
                raise RuntimeError(f"Tushare SDK 请求失败: {e}")

            col_map_raw = config.get("column_mapping", "{}")
            try:
                col_map = json.loads(col_map_raw) if isinstance(col_map_raw, str) else col_map_raw
            except Exception:
                col_map = {}
            if col_map:
                df = df.rename(columns=col_map)
            dt_col = config.get("datetime_column", "datetime")
            if dt_col in df.columns:
                df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
            return df

        try:
            import requests
        except Exception:
            raise RuntimeError("requests 库不可用")

        base_url = config.get("base_url", "")
        method = config.get("method", "POST").upper()
        headers = config.get("headers", {})
        timeout = int(config.get("timeout", 30))

        req_tmpl = config.get("request_template", "{}")
        start_str = start_time.strftime(config.get("date_format", "%Y%m%d"))
        end_str = end_time.strftime(config.get("date_format", "%Y%m%d"))
        codes_str = ",".join(codes) if codes else ""

        try:
            # 先做递归变量替换，确保 JSON 对象模板中的 params.* 也能正确替换占位符。
            req_body = _format_template_value(
                req_tmpl,
                start_time=start_str,
                end_time=end_str,
                codes=codes_str,
                interval=interval,
            )
            # 若替换后仍是 JSON 字符串，再解析为对象，便于 requests 直接发送 json body。
            if isinstance(req_body, str):
                req_body = json.loads(req_body) if req_body.startswith("{") else req_body
        except Exception:
            req_body = req_tmpl

        # 二次防线：若仍有未替换占位符，直接阻断请求并返回明确错误。
        if _has_unresolved_placeholders(req_body):
            raise RuntimeError(
                "请求模板变量未正确替换：请检查 request_template.params 是否为对象，"
                "并确认占位符使用 {codes}/{start_time}/{end_time}/{interval}"
            )

        url = base_url.rstrip("/")
        if method == "GET":
            resp = requests.get(url, headers=headers, params=req_body if isinstance(req_body, dict) else None,
                              timeout=timeout)
        else:
            resp = requests.post(url, headers=headers, json=req_body, timeout=timeout)

        resp.raise_for_status()
        data = resp.json()
        # 原样透传 Tushare 上游业务错误（即使 HTTP 200 也可能 code!=0），便于前端直接展示 code/msg。
        if isinstance(data, dict) and ("code" in data):
            try:
                upstream_code = int(data.get("code", 0))
            except Exception:
                upstream_code = -1
            if upstream_code != 0:
                upstream_msg = str(data.get("msg", "")).strip() or "未知错误"
                raise RuntimeError(f"Tushare API 错误 code={upstream_code}, msg={upstream_msg}")

        data_path = config.get("response_data_path", "")
        if data_path:
            for key in data_path.split("."):
                if key:
                    data = data.get(key, []) if isinstance(data, dict) else []
        if not isinstance(data, list):
            data = data.get("data", data.get("result", [])) if isinstance(data, dict) else []
            if not isinstance(data, list):
                return pd.DataFrame()

        # Tushare Pro 特有格式：data 是 dict，包含 "fields" (列名列表) + "items" (行数据，list of lists)
        if isinstance(data, dict):
            raw_items = data.get("items", [])
            if raw_items and isinstance(raw_items, list) and len(raw_items) > 0:
                if isinstance(raw_items[0], list):
                    fields = data.get("fields", [f"col_{i}" for i in range(len(raw_items[0]))])
                    data = [dict(zip(fields, row)) for row in raw_items]

        col_map_raw = config.get("column_mapping", "{}")
        try:
            col_map = json.loads(col_map_raw) if isinstance(col_map_raw, str) else col_map_raw
        except Exception:
            col_map = {}

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        if col_map:
            df = df.rename(columns=col_map)

        dt_col = config.get("datetime_column", "datetime")
        if dt_col in df.columns:
            df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")

        return df

    def list_codes(self, config: dict) -> list:
        config = normalize_config(config)
        try:
            import requests
        except Exception:
            return []

        base_url = config.get("base_url", "")
        list_path = config.get("list_codes_path", "")
        if not base_url or not list_path:
            return []

        url = base_url.rstrip("/") + "/" + list_path.lstrip("/")
        headers = config.get("headers", {})

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            code_path = config.get("codes_path", "data")
            for key in code_path.split("."):
                if key:
                    data = data.get(key, []) if isinstance(data, dict) else []
            if isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], dict):
                    code_field = config.get("code_field", "code")
                    return [str(item.get(code_field, "")) for item in data if item.get(code_field)]
                return [str(item) for item in data]
        except Exception:
            pass
        return []
