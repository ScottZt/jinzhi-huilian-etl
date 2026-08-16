"""内容包管理 -- .jspack 格式的定义、校验、解析、导入。

.jspack 本质是一个 ZIP 文件，包含：
  - manifest.json  包描述（版本、名称、工作流数量、插件列表）
  - workflows.json 工作流列表 [{name, description, workflow_json}, ...]
  - plugins/       (可选) 插件 .py 文件
"""
import json
import os
import shutil
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 插件目录：与 plugins/official_*.py 同级
PLUGINS_DIR = Path(__file__).resolve().parent.parent.parent / "plugins"

# 允许的 manifest 版本
SUPPORTED_PACK_VERSIONS = ("1.0",)


class PackError(Exception):
    """内容包格式或校验错误。"""


def _read_json_from_zip(zf: zipfile.ZipFile, name: str) -> dict:
    """从 ZIP 中读取指定 JSON 文件。"""
    try:
        raw = zf.read(name)
    except KeyError:
        raise PackError(f"缺少必要文件: {name}")
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise PackError(f"{name} 解析失败: {e}")


def validate_pack(file_path: str) -> dict:
    """校验 .jspack 文件，返回 manifest + 内容预览（不实际导入）。

    Returns:
        {
            "manifest": {...},
            "workflows_preview": [{"name": ..., "node_count": ...}, ...],
            "plugins_preview": ["plugin_type", ...],
        }
    """
    if not os.path.isfile(file_path):
        raise PackError("文件不存在")

    if not zipfile.is_zipfile(file_path):
        raise PackError("不是有效的 ZIP 文件")

    with zipfile.ZipFile(file_path, "r") as zf:
        names = zf.namelist()

        # 必须包含 manifest.json
        if "manifest.json" not in names:
            raise PackError("缺少 manifest.json")

        manifest = _read_json_from_zip(zf, "manifest.json")

        # 校验 manifest 版本
        pack_ver = str(manifest.get("pack_version", ""))
        if pack_ver not in SUPPORTED_PACK_VERSIONS:
            raise PackError(
                f"不支持的内容包版本: {pack_ver}，"
                f"当前支持: {', '.join(SUPPORTED_PACK_VERSIONS)}"
            )

        # 校验 workflows.json
        workflows = []
        if "workflows.json" in names:
            wf_data = _read_json_from_zip(zf, "workflows.json")
            if not isinstance(wf_data, list):
                raise PackError("workflows.json 格式错误，应为数组")
            workflows = wf_data

        # 收集插件列表
        plugins = [
            n.replace("plugins/", "").replace(".py", "")
            for n in names
            if n.startswith("plugins/") and n.endswith(".py")
        ]

    # 构造预览
    workflows_preview = []
    for wf in workflows:
        node_count = len(wf.get("workflow_json", {}).get("nodes", []))
        workflows_preview.append({
            "name": wf.get("name", "未命名"),
            "description": wf.get("description", ""),
            "node_count": node_count,
        })

    return {
        "manifest": manifest,
        "workflows_preview": workflows_preview,
        "plugins_preview": plugins,
    }


def extract_pack(file_path: str) -> Tuple[dict, List[dict], List[Tuple[str, bytes]]]:
    """解析 .jspack 文件，返回 (manifest, workflows, plugins)。

    Returns:
        manifest: dict
        workflows: [{"name": str, "description": str, "workflow_json": dict}, ...]
        plugins: [(filename, file_content_bytes), ...]
    """
    with zipfile.ZipFile(file_path, "r") as zf:
        manifest = _read_json_from_zip(zf, "manifest.json")

        workflows = []
        if "workflows.json" in zf.namelist():
            wf_data = _read_json_from_zip(zf, "workflows.json")
            if isinstance(wf_data, list):
                workflows = wf_data

        plugins = []
        for name in zf.namelist():
            if name.startswith("plugins/") and name.endswith(".py"):
                filename = name.split("/")[-1]
                content = zf.read(name)
                plugins.append((filename, content))

    return manifest, workflows, plugins


def import_pack(
    file_path: str,
    overwrite_existing: bool = False,
    license_check: bool = True,
) -> dict:
    """导入 .jspack 内容包。

    Args:
        file_path: .jspack 文件路径
        overwrite_existing: 是否覆盖同名工作流
        license_check: 是否检查 License（开发者模式可跳过）

    Returns:
        {
            "workflows_imported": int,
            "workflows_skipped": int,
            "plugins_imported": list[str],
            "manifest": dict,
        }
    """
    from app.core.license_manager import check_feature, is_dev_mode

    if license_check and not is_dev_mode():
        if not check_feature("pro_content_import"):
            raise PermissionError(
                "导入专业版内容包需要 Personal 或 Professional License"
            )

    manifest, workflows, plugins = extract_pack(file_path)

    workflows_imported = 0
    workflows_skipped = 0

    # 导入工作流
    from app.persistence import sqlite_repo

    existing_names = set()
    if not overwrite_existing:
        existing_names = {
            wf.get("name") for wf in sqlite_repo.list_workflows()
        }

    for wf in workflows:
        name = wf.get("name", "").strip()
        if not name:
            workflows_skipped += 1
            continue

        if not overwrite_existing and name in existing_names:
            workflows_skipped += 1
            continue

        record = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": wf.get("description", ""),
            "workflow_json": wf.get("workflow_json", {}),
        }
        sqlite_repo.save_workflow(record)
        workflows_imported += 1
        existing_names.add(name)

    # 导入插件
    plugins_imported = []
    if plugins:
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        for filename, content in plugins:
            target = PLUGINS_DIR / filename
            target.write_bytes(content)
            plugins_imported.append(filename.replace(".py", ""))

        # 重新加载插件
        try:
            from app.nodes import reload_plugins
            reload_plugins()
        except Exception:
            pass

    # 记录已安装的内容包
    _save_pack_record(manifest)

    return {
        "workflows_imported": workflows_imported,
        "workflows_skipped": workflows_skipped,
        "plugins_imported": plugins_imported,
        "manifest": manifest,
    }


def get_installed_packs() -> List[dict]:
    """获取已安装的内容包列表。"""
    from app.persistence import sqlite_repo
    raw = sqlite_repo.get_metadata("_installed_packs")
    if not raw:
        return []
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []


def _save_pack_record(manifest: dict):
    """记录已安装的内容包信息。"""
    from app.persistence import sqlite_repo
    packs = get_installed_packs()

    # 更新或追加
    found = False
    for i, p in enumerate(packs):
        if p.get("name") == manifest.get("name"):
            packs[i] = manifest
            found = True
            break
    if not found:
        packs.append(manifest)

    sqlite_repo.save_metadata("_installed_packs", json.dumps(packs, ensure_ascii=False))
