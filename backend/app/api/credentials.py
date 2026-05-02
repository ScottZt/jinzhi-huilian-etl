from fastapi import APIRouter
from typing import List, Optional
from pydantic import BaseModel
import uuid
import json

from app.persistence import sqlite_repo
from app.core.credential_manager import encrypt_credential, decrypt_credential, mask_sensitive


router = APIRouter()


class CredentialCreate(BaseModel):
    name: str
    type: str  # tushare_token | http_bearer | basic_auth | apikey
    config: dict  # sensitive fields encrypted on the frontend, plain dict here


class CredentialResponse(BaseModel):
    id: str
    name: str
    type: str
    config: dict  # masked in list, decrypted in detail
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# Supported credential types
CREDENTIAL_TYPES = {
    "tushare_token": {
        "label": "Tushare Token",
        "icon": "🔑",
        "fields": [
            {"key": "token", "label": "Token", "type": "textarea", "required": True,
             "placeholder": "填入你的 Tushare Pro Token"},
            {"key": "base_url", "label": "API 地址", "type": "text",
             "default": "http://api.tushare.pro",
             "placeholder": "默认: http://api.tushare.pro"}
        ]
    },
    "http_bearer": {
        "label": "HTTP Bearer Token",
        "icon": "🔐",
        "fields": [
            {"key": "header_key", "label": "Header Key", "type": "text", "default": "Authorization",
             "placeholder": "默认: Authorization"},
            {"key": "token", "label": "Token / Bearer String", "type": "textarea", "required": True,
             "placeholder": "Bearer xxxxxx 或直接填 token"}
        ]
    },
    "basic_auth": {
        "label": "Basic Auth",
        "icon": "🔑",
        "fields": [
            {"key": "username", "label": "用户名", "type": "text", "required": True},
            {"key": "password", "label": "密码", "type": "password", "required": True}
        ]
    },
    "apikey": {
        "label": "API Key + Secret",
        "icon": "🔑",
        "fields": [
            {"key": "key_name", "label": "Header Key", "type": "text", "default": "X-API-KEY"},
            {"key": "api_key", "label": "API Key", "type": "text", "required": True},
            {"key": "api_secret", "label": "API Secret（可选）", "type": "text", "required": False}
        ]
    }
}


@router.get("/types")
async def get_credential_types():
    """返回支持的凭证类型定义（前端渲染表单用）。"""
    return {
        k: {"label": v["label"], "icon": v["icon"], "fields": v["fields"]}
        for k, v in CREDENTIAL_TYPES.items()
    }


@router.get("/", response_model=List[dict])
async def list_all():
    """列表：敏感字段已遮蔽。"""
    return sqlite_repo.list_credentials()


@router.post("/")
async def create(body: CredentialCreate):
    cred_id = str(uuid.uuid4())
    # Encrypt sensitive config before storing
    encrypted_config = encrypt_credential(body.config)
    record = {
        "id": cred_id,
        "name": body.name,
        "type": body.type,
        "config": {"_encrypted": encrypted_config},
    }
    result = sqlite_repo.save_credential(record)
    # Return masked version
    result["config"] = mask_sensitive(body.config)
    return result


@router.get("/{credential_id}")
async def get_one(credential_id: str):
    """详情：返回解密后的完整配置。"""
    data = sqlite_repo.get_credential(credential_id)
    if not data:
        return {"error": "凭证不存在"}
    # Decrypt and return full config
    raw_cfg = data["config"]
    if isinstance(raw_cfg, dict) and "_encrypted" in raw_cfg:
        data["config"] = decrypt_credential(raw_cfg["_encrypted"])
    else:
        data["config"] = raw_cfg
    return data


@router.put("/{credential_id}")
async def update(credential_id: str, body: CredentialCreate):
    data = sqlite_repo.get_credential(credential_id)
    if not data:
        return {"error": "凭证不存在"}

    # Encrypt new config
    encrypted_config = encrypt_credential(body.config)
    record = {
        "id": credential_id,
        "name": body.name,
        "type": body.type,
        "config": {"_encrypted": encrypted_config},
    }
    result = sqlite_repo.save_credential(record)
    result["config"] = mask_sensitive(body.config)
    return result


@router.delete("/{credential_id}")
async def delete(credential_id: str):
    deleted = sqlite_repo.delete_credential(credential_id)
    return {"deleted": deleted}


@router.get("/for-select/")
async def for_select():
    """供下拉选择用的简化列表（id + name + type）。"""
    return sqlite_repo.list_credentials_for_select()


@router.post("/{credential_id}/test")
async def test_credential(credential_id: str):
    """测试凭证连通性。"""
    data = sqlite_repo.get_credential(credential_id)
    if not data:
        return {"success": False, "message": "凭证不存在"}
    raw_cfg = data["config"]
    if isinstance(raw_cfg, dict) and "_encrypted" in raw_cfg:
        cfg = decrypt_credential(raw_cfg["_encrypted"])
    else:
        cfg = raw_cfg
    cred_type = data.get("type", "")

    try:
        import httpx
        base_url = cfg.get("base_url", "")
        timeout = httpx.Timeout(10.0, connect=5.0)

        if cred_type == "tushare_token":
            token = cfg.get("token", "")
            if not base_url:
                base_url = "http://api.tushare.pro"
            # Test with stock_basic (lightweight call)
            body = {"api_name": "stock_basic", "token": token, "params": {"list_status": "L"}, "fields": "ts_code,symbol,name"}
            headers = {"Content-Type": "application/json"}
            resp = httpx.post(base_url, json=body, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                j = resp.json()
                if j.get("code") == 0:
                    return {"success": True, "message": f"✅ Token 有效，接口返回 {len(j.get('data', {}).get('items', []))} 条记录"}
                else:
                    return {"success": False, "message": f"❌ Token 无效：{j.get('msg', resp.text)}"}
            else:
                return {"success": False, "message": f"❌ HTTP {resp.status_code}：{resp.text[:200]}"}
        elif cred_type == "http_bearer":
            header_key = cfg.get("header_key", "Authorization")
            token = cfg.get("token", "")
            if "Bearer" not in token and "bearer" not in token.lower():
                token = f"Bearer {token}"
            headers = {header_key: token}
            if base_url:
                resp = httpx.get(base_url, headers=headers, timeout=timeout)
                return {"success": resp.status_code < 400, "message": f"✅ 状态码 {resp.status_code}" if resp.status_code < 400 else f"❌ HTTP {resp.status_code}"}
            else:
                return {"success": False, "message": "❌ 未配置 base_url"}
        elif cred_type == "basic_auth":
            user = cfg.get("username", "")
            pwd = cfg.get("password", "")
            if base_url:
                resp = httpx.get(base_url, auth=(user, pwd), timeout=timeout)
                return {"success": resp.status_code < 400, "message": f"✅ 状态码 {resp.status_code}" if resp.status_code < 400 else f"❌ HTTP {resp.status_code}"}
            else:
                return {"success": False, "message": "❌ 未配置 base_url"}
        elif cred_type == "apikey":
            key_name = cfg.get("key_name", "X-API-KEY")
            api_key = cfg.get("api_key", "")
            headers = {key_name: api_key}
            if base_url:
                resp = httpx.get(base_url, headers=headers, timeout=timeout)
                return {"success": resp.status_code < 400, "message": f"✅ 状态码 {resp.status_code}" if resp.status_code < 400 else f"❌ HTTP {resp.status_code}"}
            else:
                return {"success": False, "message": "❌ 未配置 base_url"}
        else:
            return {"success": False, "message": f"❌ 未知凭证类型：{cred_type}"}
    except httpx.TimeoutException:
        return {"success": False, "message": "❌ 连接超时，请检查 base_url 是否正确、网络是否可达"}
    except Exception as e:
        return {"success": False, "message": f"❌ {str(e)}"}