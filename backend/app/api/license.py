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
    return lm.get_license_info()


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
