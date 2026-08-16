"""License 授权 API。"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.core import license_manager as lm

router = APIRouter()


class LicenseActivateRequest(BaseModel):
    activation_code: str


@router.get("/info")
async def get_license_info():
    """返回当前版本信息。

    开源模式：根据是否导入内容包判断版本
      - edition = "open_source"（开源版）：未导入任何内容包
      - edition = "pro"（专业版）：已导入至少一个内容包，享受尊贵标识
    功能层面全版本一致（全功能开放），差异仅在官方精选模板/插件。
    """
    info = dict(lm.get_license_info())
    try:
        from app.core import content_pack
        installed = content_pack.get_installed_packs() or []
    except Exception:
        installed = []

    info["installed_packs_count"] = len(installed)
    info["installed_pack_names"] = [p.get("name") or p.get("title") for p in installed if isinstance(p, dict)]
    info["edition"] = "pro" if installed else "open_source"
    return info


@router.post("/activate")
async def activate(body: LicenseActivateRequest):
    try:
        info = lm.activate_online(body.activation_code)
        return info
    except Exception as e:
        return {"error": str(e)}


@router.post("/deactivate")
async def deactivate():
    lm.clear_license()
    return {"status": "ok"}


@router.post("/offline/activate")
async def offline_activate(body: BaseModel):
    """离线激活，body 含 file_content 或 file_path。"""
    try:
        info = lm.activate_offline("/tmp/license.lic")  # placeholder — file upload not supported in this context
        return info
    except Exception as e:
        return {"error": str(e)}


@router.get("/offline/request")
async def offline_request():
    return lm.export_offline_request()


@router.get("/check/{feature}")
async def check_feature(feature: str):
    return {"feature": feature, "allowed": lm.check_feature(feature)}
