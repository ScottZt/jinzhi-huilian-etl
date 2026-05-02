"""Tushare Pro 数据源适配器 — 处理 Tushare 特有的 fields + items (list of lists) 响应格式。"""
import pandas as pd
from datetime import datetime
from typing import Tuple
import json

from app.adapters.source_adapters.kline_base import KLineSourceAdapter, normalize_config


class HttpAdapter(KLineSourceAdapter):
    """通用 HTTP/REST API 适配器。用户自行配置 base_url、headers、请求模板。

    合规说明：工具不内置任何第三方数据源连接方案，大模型仅生成代码模板，
    数据源相关的接口、Token、密钥均需用户自行填写。
    """

    def check_connectivity(self, config: dict) -> Tuple[bool, str]:
        config = normalize_config(config)
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
            req_body = req_tmpl.format(
                start_time=start_str,
                end_time=end_str,
                codes=codes_str,
                interval=interval,
            )
            req_body = json.loads(req_body) if req_body.startswith("{") else req_body
        except Exception:
            req_body = req_tmpl

        url = base_url.rstrip("/")
        if method == "GET":
            resp = requests.get(url, headers=headers, params=req_body if isinstance(req_body, dict) else None,
                              timeout=timeout)
        else:
            resp = requests.post(url, headers=headers, json=req_body, timeout=timeout)

        resp.raise_for_status()
        data = resp.json()

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