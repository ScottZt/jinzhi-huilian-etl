"""依赖管理 API — 检查/安装可选依赖包。"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from app.dep_utils import OPTIONAL_DEPS, check_dep, auto_install_dep

router = APIRouter()


class InstallRequest(BaseModel):
    packages: List[str]


@router.get("/")
async def list_deps():
    """列出所有可选依赖及其安装状态。"""
    results = []
    for pkg_name in OPTIONAL_DEPS:
        results.append(check_dep(pkg_name))
    missing_count = sum(1 for r in results if not r["installed"])
    return {"deps": results, "total": len(results), "missing": missing_count}


@router.post("/install")
async def install_deps(req: InstallRequest):
    """安装指定的依赖包。"""
    results = []
    for pkg_name in req.packages:
        if pkg_name not in OPTIONAL_DEPS:
            results.append({"package": pkg_name, "success": False, "msg": "未知包名"})
            continue
        success = auto_install_dep(pkg_name)
        if success:
            results.append({"package": pkg_name, "success": True, "msg": "安装成功"})
        else:
            results.append({"package": pkg_name, "success": False, "msg": "安装失败，请手动执行: pip install " + pkg_name})
    return {"results": results}
