"""AI 脚本生成 API — 合规设计：仅用于生成数据同步相关脚本。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from app.core import license_manager as lm
from app.core.ai_script_generator import AiScriptGenerator, COMPLIANCE_WARNING

router = APIRouter()

_gen = AiScriptGenerator()


class GenerateRequest(BaseModel):
    prompt: str
    context: Optional[dict] = None


class OptimizeRequest(BaseModel):
    script: str
    instruction: str


class LLMConfigRequest(BaseModel):
    endpoint: str
    api_key: str
    model: str = "gpt-4o-mini"


@router.get("/status")
async def get_generation_status():
    """获取 AI 生成状态（剩余次数、LLM 配置状态）。"""
    try:
        info = lm.get_license_info()
        tier = info.get("tier", "free") if info.get("activated") else "free"
        remaining = lm.get_ai_daily_remaining() if tier == "free" else -1
        cfg = _gen.load_llm_config()
        llm_configured = bool(cfg and cfg.get("endpoint") and cfg.get("api_key"))
        return {
            "tier": tier,
            "remaining_today": remaining,
            "unlimited": tier != "free",
            "llm_configured": llm_configured,
            "llm_model": cfg.get("model") if llm_configured else None,
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/generate")
async def generate_script(body: GenerateRequest):
    """
    生成数据同步 Python 脚本。

    合规说明：仅生成数据同步相关脚本，禁止生成交易、破解、逆向等违规代码。
    """
    try:
        info = lm.get_license_info()
        tier = info.get("tier", "free") if info.get("activated") else "free"

        script, err, remaining = _gen.generate(body.prompt, tier, body.context or {})

        if err:
            return {
                "success": False,
                "error": err,
                "remaining_today": remaining,
                "compliance_notice": COMPLIANCE_WARNING,
            }

        return {
            "success": True,
            "script": script,
            "remaining_today": remaining if tier == "free" else -1,
            "unlimited": tier != "free",
            "compliance_notice": COMPLIANCE_WARNING,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/optimize")
async def optimize_script(body: OptimizeRequest):
    """
    优化已有脚本（需 LLM 配置）。

    合规说明：用户需自行审核优化后的脚本合规性。
    """
    try:
        info = lm.get_license_info()
        tier = info.get("tier", "free") if info.get("activated") else "free"

        if tier not in ("personal", "professional"):
            return {
                "success": False,
                "error": "脚本优化功能需要 Personal 或 Professional 授权。",
            }

        optimized, err = _gen.optimize_script(body.script, body.instruction)

        if err:
            return {"success": False, "error": err}

        return {
            "success": True,
            "script": optimized,
            "compliance_notice": COMPLIANCE_WARNING,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/configure")
async def configure_llm(body: LLMConfigRequest):
    """配置 LLM API（OpenAI 兼容接口）。"""
    try:
        _gen.configure_llm(body.endpoint, body.api_key, body.model)
        return {"success": True, "message": "LLM 配置已保存"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/configure")
async def get_llm_config():
    """获取 LLM 配置状态（不返回 api_key 明文）。"""
    cfg = _gen.load_llm_config()
    if cfg and cfg.get("api_key"):
        cfg = {**cfg, "api_key": "****" + cfg["api_key"][-4:] if len(cfg["api_key"]) > 4 else "****"}
    return cfg or {}


@router.delete("/configure")
async def clear_llm_config():
    """清除 LLM 配置。"""
    try:
        from app.persistence import sqlite_repo
        sqlite_repo.delete_metadata("ai_llm_config")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}