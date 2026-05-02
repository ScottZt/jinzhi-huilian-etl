from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import uuid

from app.persistence import sqlite_repo
from app.core.credential_manager import encrypt_credential, decrypt_credential

router = APIRouter()


class LLMConfigCreate(BaseModel):
    name: str = "default"
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = "gpt-4o-mini"
    system_prompt: str = ""
    enabled: int = 0


@router.get("/")
async def list_all():
    return sqlite_repo.list_ll_configs()


@router.post("/")
async def create(body: LLMConfigCreate):
    cfg_id = str(uuid.uuid4())
    result = sqlite_repo.save_llm_config({
        "id": cfg_id, "name": body.name, "provider": body.provider,
        "base_url": body.base_url, "api_key": body.api_key,
        "model": body.model, "system_prompt": body.system_prompt,
        "enabled": body.enabled,
    })
    return {"id": cfg_id, **result}


@router.put("/{cfg_id}")
async def update(cfg_id: str, body: LLMConfigCreate):
    result = sqlite_repo.save_llm_config({
        "id": cfg_id, "name": body.name, "provider": body.provider,
        "base_url": body.base_url, "api_key": body.api_key,
        "model": body.model, "system_prompt": body.system_prompt,
        "enabled": body.enabled,
    })
    return result


@router.get("/{cfg_id}")
async def get_one(cfg_id: str):
    data = sqlite_repo.get_llm_config(cfg_id)
    if not data:
        return {"error": "LLM 配置不存在"}
    return data


@router.delete("/{cfg_id}")
async def delete(cfg_id: str):
    deleted = sqlite_repo.delete_llm_config(cfg_id)
    return {"deleted": deleted}


@router.post("/chat")
async def chat(body: dict):
    """Send a message to the configured LLM."""
    cfg = sqlite_repo.get_llm_config(body.get("config_id", "default"))
    if not cfg:
        return {"error": "请先配置大模型"}
    if not cfg.get("api_key"):
        return {"error": "请先填入 API Key"}
    if not cfg.get("base_url"):
        return {"error": "请先填入 base_url"}

    import httpx
    api_key = cfg["api_key"]
    base_url = cfg["base_url"].rstrip("/")
    model = cfg.get("model", "gpt-4o-mini")
    system_prompt = cfg.get("system_prompt", "") or "你是一个量化交易 ETL 系统的技术顾问。"

    messages = [{"role": "system", "content": system_prompt}]
    if body.get("messages"):
        messages.extend(body["messages"])
    else:
        messages.append({"role": "user", "content": body.get("message", "")})

    try:
        timeout = httpx.Timeout(60.0, connect=10.0)
        resp = httpx.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.7,
            },
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"content": data["choices"][0]["message"]["content"]}
        else:
            return {"error": f"LLM 返回错误：HTTP {resp.status_code} - {resp.text[:500]}"}
    except httpx.TimeoutException:
        return {"error": "请求超时，请检查网络连接"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/troubleshoot")
async def troubleshoot(body: dict):
    """AI 辅助排查错误。"""
    error = body.get("error", "")
    context = body.get("context", "")
    cfg = sqlite_repo.get_llm_config(body.get("config_id", "default"))
    if not cfg or not cfg.get("api_key") or not cfg.get("base_url"):
        return {"error": "请先配置大模型（设置 API Key 和 base_url）"}

    import httpx
    api_key = cfg["api_key"]
    base_url = cfg["base_url"].rstrip("/")
    model = cfg.get("model", "gpt-4o-mini")

    system_prompt = f"""你是一个量化交易 ETL 系统的技术顾问。用户遇到了数据源配置或连接问题。
请分析错误信息，给出排查步骤和解决方案。回答要简洁、有针对性。
"""
    user_msg = f"## 错误信息\n{error}\n\n## 上下文\n{context}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    try:
        timeout = httpx.Timeout(60.0, connect=10.0)
        resp = httpx.post(
            f"{base_url}/chat/completions",
            json={"model": model, "messages": messages, "temperature": 0.3},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"advice": data["choices"][0]["message"]["content"]}
        else:
            return {"error": f"LLM 返回错误：HTTP {resp.status_code} - {resp.text[:300]}"}
    except Exception as e:
        return {"error": str(e)}
