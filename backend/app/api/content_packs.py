"""内容包导入 API -- 上传/校验/导入 .jspack 文件。"""
import os
import tempfile
from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional

from app.core import content_pack

router = APIRouter()


@router.post("/validate")
async def validate_pack(file: UploadFile = File(...)):
    """上传 .jspack 文件，返回包内容预览（不实际导入）。"""
    if not file.filename or not file.filename.endswith(".jspack"):
        return {"error": "请上传 .jspack 格式文件"}

    tmp_path = None
    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jspack") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = content_pack.validate_pack(tmp_path)
        return result
    except content_pack.PackError as e:
        return {"error": f"内容包格式错误: {e}"}
    except Exception as e:
        return {"error": f"校验失败: {e}"}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/import")
async def import_pack(
    file: UploadFile = File(...),
    overwrite_existing: bool = Form(False),
):
    """导入 .jspack 内容包（校验 License >= personal）。"""
    if not file.filename or not file.filename.endswith(".jspack"):
        return {"error": "请上传 .jspack 格式文件"}

    tmp_path = None
    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jspack") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = content_pack.import_pack(
            tmp_path,
            overwrite_existing=overwrite_existing,
            license_check=True,
        )
        wf_count = result['workflows_imported']
        plugin_count = len(result['plugins_imported'])
        skipped = result['workflows_skipped']
        license_activated = result.get('license_activated', False)
        license_type = result.get('license_type')

        msg = f"导入完成: {wf_count} 个工作流"
        if plugin_count > 0:
            msg += f", {plugin_count} 个插件"
        if skipped > 0:
            msg += f", 跳过 {skipped} 个已存在"
        if license_activated:
            type_names = {'personal': '个人版', 'professional': '专业版'}
            type_name = type_names.get(license_type, license_type)
            msg += f"。已自动激活 {type_name} License"

        return {
            "success": True,
            "message": msg,
            **result,
        }
    except PermissionError as e:
        return {"error": str(e)}
    except content_pack.PackError as e:
        return {"error": f"内容包格式错误: {e}"}
    except Exception as e:
        return {"error": f"导入失败: {e}"}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.get("/status")
async def pack_status():
    """返回已安装的内容包信息。"""
    from app.core.license_manager import get_license_info, is_dev_mode

    packs = content_pack.get_installed_packs()
    lic_info = get_license_info()

    return {
        "installed_packs": packs,
        "installed_packs_count": len(packs),
        "license_type": lic_info.get("type", "free"),
        "dev_mode": is_dev_mode(),
        "can_import": is_dev_mode() or lic_info.get("features", {}).get("pro_content_import", False),
    }


@router.get("/workflow/{pack_name}/{workflow_index}")
async def get_workflow(pack_name: str, workflow_index: str):
    """从已安装的内容包中按「包名 + 工作流索引」读取单条工作流。

    workflow_index 是整数索引（从 0 起），对应打包时 workflows.json 数组的下标。
    前端不暴露 workflow JSON，通过此接口按需获取。
    """
    from urllib.parse import unquote
    pack_name = unquote(pack_name)
    try:
        idx = int(workflow_index)
    except ValueError:
        return {"error": "workflow_index 必须为整数"}

    packs = content_pack.get_installed_packs()
    for pack in packs:
        if pack.get("name") != pack_name:
            continue
        workflows = pack.get("workflows", [])
        if 0 <= idx < len(workflows):
            return workflows[idx]
    return {"error": "工作流未找到（包名或索引不匹配）"}
