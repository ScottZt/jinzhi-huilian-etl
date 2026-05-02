"""数据源 API — 合规设计：通用 HTTP 连接，用户自行配置 API，无第三方 SDK 绑定。"""
from fastapi import APIRouter
from datetime import datetime, timedelta
from typing import List
from pydantic import BaseModel
import uuid
import json

from app.persistence import sqlite_repo
from app.models.connection import ConnectionConfig
from app.core.credential_manager import decrypt_credential, mask_sensitive

def _inject_credential(cfg: dict) -> dict:
    """If credential_id is set, merge credential config into cfg headers."""
    cred_id = cfg.get("credential_id")
    if not cred_id:
        return cfg
    cred = sqlite_repo.get_credential(cred_id)
    if not cred:
        return cfg
    raw_cfg = cred.get("config", {})
    if isinstance(raw_cfg, dict) and "_encrypted" in raw_cfg:
        cred_cfg = decrypt_credential(raw_cfg["_encrypted"])
    else:
        cred_cfg = raw_cfg
    cred_type = cred.get("type", "")

    # Build headers from credential
    headers = cfg.get("headers", {})
    if isinstance(headers, str):
        try:
            import json
            headers = json.loads(headers)
        except Exception:
            headers = {}

    if cred_type == "tushare_token":
        token = cred_cfg.get("token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
            # Also inject into request_template token
            req_tmpl = cfg.get("request_template", "{}")
            if isinstance(req_tmpl, dict):
                req_tmpl["token"] = token
                cfg["request_template"] = req_tmpl
            elif isinstance(req_tmpl, str):
                try:
                    import json
                    tmpl_obj = json.loads(req_tmpl)
                    tmpl_obj["token"] = token
                    cfg["request_template"] = json.dumps(tmpl_obj)
                except Exception:
                    pass
        # Inject base_url if credential has it
        base_url = cred_cfg.get("base_url", "")
        if base_url and not cfg.get("base_url"):
            cfg["base_url"] = base_url
    elif cred_type == "http_bearer":
        header_key = cred_cfg.get("header_key", "Authorization")
        token = cred_cfg.get("token", "")
        if token:
            if "Bearer" not in token and "bearer" not in token.lower():
                headers[header_key] = f"Bearer {token}"
            else:
                headers[header_key] = token
    elif cred_type == "basic_auth":
        import base64
        user = cred_cfg.get("username", "")
        pwd = cred_cfg.get("password", "")
        if user and pwd:
            auth_str = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_str}"
    elif cred_type == "apikey":
        key_name = cred_cfg.get("key_name", "X-API-KEY")
        api_key = cred_cfg.get("api_key", "")
        api_secret = cred_cfg.get("api_secret", "")
        if api_key:
            headers[key_name] = api_key
        if api_secret:
            headers[f"{key_name}-Secret"] = api_secret

    cfg["headers"] = headers
    return cfg

router = APIRouter()


class KLineSourceCreate(BaseModel):
    name: str
    type: str
    config: dict


class KLineSourceResponse(BaseModel):
    id: str
    name: str
    type: str
    config: dict


# 合规说明文案（嵌入所有数据源相关页面）
COMPLIANCE_NOTICE = (
    "⚠️ 合规提示：本工具不内置任何第三方数据源 SDK 或密钥。"
    "所有数据源的 API 地址、Token、密钥均由用户自行配置，用户需严格遵守"
    "对应数据源的用户协议与相关法律法规，承担全部合规责任。"
)


@router.get("/", response_model=List[dict])
async def get_all_sources():
    return sqlite_repo.list_kline_sources()


@router.get("/{source_id}")
async def get_source(source_id: str):
    data = sqlite_repo.get_kline_source(source_id)
    if not data:
        return {"error": "数据源不存在"}
    return data


@router.post("/")
async def create_source(body: KLineSourceCreate):
    source_id = str(uuid.uuid4())
    record = {
        "id": source_id,
        "name": body.name,
        "type": body.type,
        "credential_id": body.config.get("credential_id", ""),
        "config": {k: v for k, v in body.config.items() if k != "credential_id"},
    }
    result = sqlite_repo.save_kline_source(record)
    return {"id": source_id, **result}


@router.put("/{source_id}")
async def update_source(source_id: str, body: KLineSourceCreate):
    record = {
        "id": source_id,
        "name": body.name,
        "type": body.type,
        "credential_id": body.config.get("credential_id", ""),
        "config": {k: v for k, v in body.config.items() if k != "credential_id"},
    }
    result = sqlite_repo.save_kline_source(record)
    return result


@router.delete("/{source_id}")
async def delete_source(source_id: str):
    deleted = sqlite_repo.delete_kline_source(source_id)
    return {"deleted": deleted}


def _get_adapter_for_source(source_type: str, cfg: dict):
    """根据数据源类型选择合适的适配器。"""
    try:
        if source_type == "tushare":
            from app.adapters.source_adapters.tushare_adapter import HttpAdapter
        elif source_type == "akshare":
            from app.adapters.source_adapters.akshare_adapter import HttpAdapter
        elif source_type == "tdx":
            from app.adapters.source_adapters.tdx_adapter import TdxAdapter
            return TdxAdapter()
        elif source_type == "http":
            from app.adapters.source_adapters.tdx_adapter import HttpAdapter
        else:
            from app.adapters.source_adapters.tdx_adapter import HttpAdapter
        return HttpAdapter()
    except ImportError:
        from app.adapters.source_adapters.tdx_adapter import HttpAdapter
        return HttpAdapter()


@router.post("/{source_id}/test")
async def test_source(source_id: str):
    """测试 HTTP 数据源连接。"""
    data = sqlite_repo.get_kline_source(source_id)
    if not data:
        return {"error": "数据源不存在", "success": False}

    cfg = data.get("config", {})
    source_type = data.get("type", "http")
    # Inject credential_id from parent record if present
    cfg["credential_id"] = data.get("credential_id", "")

    try:
        from app.adapters.source_adapters.kline_base import normalize_config
        # Inject credential if set
        cfg = _inject_credential(cfg)
        cfg = normalize_config(cfg)
        adapter = _get_adapter_for_source(source_type, cfg)
        success, message = adapter.check_connectivity(cfg)
        notice = COMPLIANCE_NOTICE
        return {"success": success, "message": f"{message}\n\n{notice}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/{source_id}/codes")
async def list_source_codes(source_id: str):
    """通过配置的 HTTP API 获取代码列表。"""
    data = sqlite_repo.get_kline_source(source_id)
    if not data:
        return {"error": "数据源不存在"}

    cfg = data.get("config", {})
    source_type = data.get("type", "http")
    cfg["credential_id"] = data.get("credential_id", "")

    try:
        from app.adapters.source_adapters.kline_base import normalize_config
        cfg = _inject_credential(cfg)
        cfg = normalize_config(cfg)
        adapter = _get_adapter_for_source(source_type, cfg)
        codes = adapter.list_codes(cfg)
        return {"codes": codes, "count": len(codes)}
    except Exception as e:
        return {"error": str(e)}


@router.get("/{source_id}/preview")
async def preview_source_data(source_id: str):
    """从配置的 HTTP API 拉取少量样例数据，用于预览。

    合规说明：工具仅提供 HTTP 请求转发能力，不存储任何数据源 Token 或密钥。
    """
    data = sqlite_repo.get_kline_source(source_id)
    if not data:
        return {"error": "数据源不存在"}

    cfg = data.get("config", {})
    source_type = data.get("type", "http")
    cfg["credential_id"] = data.get("credential_id", "")

    try:
        from app.adapters.source_adapters.kline_base import normalize_config
        cfg = _inject_credential(cfg)
        cfg = normalize_config(cfg)
        adapter = _get_adapter_for_source(source_type, cfg)

        end_time = datetime.now()
        start_time = end_time - timedelta(days=3)
        preview_codes_raw = cfg.get("preview_codes", "000001")
        if isinstance(preview_codes_raw, list):
            codes = [str(c) for c in preview_codes_raw[:3]]
        elif isinstance(preview_codes_raw, str):
            codes = [c.strip() for c in preview_codes_raw.split(",") if c.strip()][:3]
        else:
            codes = ["000001"]
        interval = cfg.get("interval", "1min")

        # Capture debug info
        base_url = cfg.get("base_url", "")
        method = cfg.get("method", "POST")
        req_tmpl = cfg.get("request_template", {})
        start_str = start_time.strftime("%Y%m%d")
        end_str = end_time.strftime("%Y%m%d")
        codes_str = ",".join(codes)

        debug_request_body = {}
        if isinstance(req_tmpl, dict):
            try:
                debug_request_body = {
                    k: v.format(start_time=start_str, end_time=end_str, codes=codes_str, interval=interval)
                    if isinstance(v, str) else v
                    for k, v in req_tmpl.items()
                }
            except Exception:
                debug_request_body = req_tmpl

        debug_request_body_str = json.dumps(debug_request_body, ensure_ascii=False, indent=2) if isinstance(debug_request_body, dict) else str(debug_request_body)

        df = adapter.fetch_kline(cfg, codes, start_time, end_time, interval)

        if df.empty:
            start_time = end_time - timedelta(days=30)
            df = adapter.fetch_kline(cfg, codes, start_time, end_time, "D")

        rows = df.head(20).to_dict("records")
        serialized = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            clean = {}
            for k, v in row.items():
                if v is None:
                    clean[k] = None
                elif hasattr(v, 'isoformat'):
                    clean[k] = v.isoformat()
                elif hasattr(v, 'tolist'):
                    clean[k] = v.tolist()
                elif hasattr(v, 'item'):
                    clean[k] = v.item()
                elif isinstance(v, (list, dict)):
                    clean[k] = json.dumps(v, ensure_ascii=False, default=str)
                else:
                    clean[k] = v
            if clean:
                serialized.append(clean)

        # 推断字段类型
        field_types = {}
        if not df.empty:
            for col in df.columns:
                sample = df[col].dropna().head(10)
                if len(sample) == 0:
                    field_types[col] = "string"
                elif pd.api.types.is_datetime64_any_dtype(df[col]):
                    field_types[col] = "datetime"
                elif pd.api.types.is_integer_dtype(df[col]):
                    field_types[col] = "integer"
                elif pd.api.types.is_float_dtype(df[col]):
                    field_types[col] = "float"
                else:
                    field_types[col] = "string"

        # Response sample (first 2 lines of raw data)
        response_sample = ""
        if serialized:
            response_sample = json.dumps(serialized[:2], ensure_ascii=False, indent=2)

        return {
            "source_name": data["name"],
            "source_type": data.get("type", "http"),
            "total_rows": len(df),
            "columns": list(df.columns) if not df.empty else [],
            "field_types": field_types,
            "data": serialized,
            "compliance_notice": COMPLIANCE_NOTICE,
            # Debug info
            "request_url": base_url,
            "request_method": method,
            "request_body": debug_request_body_str,
            "http_status": 200 if not df.empty else None,
            "response_sample": response_sample,
        }
    except Exception as e:
        return {
            "error": str(e),
            "source_name": data["name"],
            "source_type": data.get("type", "http"),
            "request_url": cfg.get("base_url", ""),
            "request_method": cfg.get("method", "POST"),
            "total_rows": 0,
            "columns": [],
            "data": [],
        }


# 导入 pandas 用于类型推断
import pandas as pd
