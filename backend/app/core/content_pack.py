"""内容包管理 -- .jspack 格式的定义、校验、解析、导入。

.jspack 本质是一个 ZIP 文件，包含：
  - manifest.json  包描述（版本、名称、工作流数量、插件列表、可选激活码）
  - workflows.json 工作流列表 [{name, description, workflow_json}, ...]
  - plugins/       (可选) 插件 .py 文件

manifest.json 格式：
  {
    "pack_version": "1.0",
    "name": "金智汇联专业版内容包 v1",
    "activation_code": "personal:2027-12-31:xxx",  // 可选，嵌入激活码
    "workflows_count": 25,
    "plugins": [...],
    "created_at": "2026-08-15"
  }

如果 manifest 包含 activation_code，导入时会自动激活 License。
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

    result = {
        "manifest": manifest,
        "workflows_preview": workflows_preview,
        "plugins_preview": plugins,
    }

    # 如果有嵌入的激活码，显示信息
    activation_code = manifest.get("activation_code", "")
    if activation_code:
        parts = activation_code.split(":")
        if len(parts) >= 2:
            result["has_activation"] = True
            result["activation_type"] = parts[0]
            result["activation_expires"] = parts[1]

    return result


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

    支持两种包类型：
      - 基础包（manifest.is_patch=False 或缺失）：按 name 去重，跳过已存在的工作流
      - 增量补丁（manifest.is_patch=True）：
          * 必须先已安装 base_version 对应的基础包，否则报错
          * 只跳过 base_version 包内的工作流名，允许新增的工作流导入

    Returns:
        {
            "workflows_imported": int,
            "workflows_skipped": int,
            "plugins_imported": list[str],
            "manifest": dict,
            "is_patch": bool,
            "base_version": str | None,
            "skipped_by_base": int,      # 增量补丁：被基础包跳过的工作流数
        }
    """
    manifest, workflows, plugins = extract_pack(file_path)

    is_patch = bool(manifest.get("is_patch", False))
    base_version = manifest.get("base_version")

    # 增量补丁：先校验基础包已装
    if is_patch:
        if not base_version:
            raise ValueError("增量补丁 manifest 缺少 base_version")
        installed = get_installed_packs()
        base_installed = any(
            p.get("pack_version_label") == base_version and not p.get("is_patch")
            for p in installed
        )
        if not base_installed:
            raise PermissionError(
                f"导入补丁前需先安装基础包 v{base_version}。"
                f"当前已安装包: {[p.get('name') for p in installed]}"
            )

    workflows_imported = 0
    workflows_skipped = 0
    skipped_by_base = 0

    # 工作流去重策略
    from app.persistence import sqlite_repo

    if is_patch:
        # 补丁模式：只跳过「基础包内的工作流名」，允许其他新增工作流导入
        base_names = _collect_base_workflow_names(base_version)
        skip_names = base_names
    elif overwrite_existing:
        skip_names = set()
    else:
        skip_names = {wf.get("name") for wf in sqlite_repo.list_workflows()}

    for wf in workflows:
        name = wf.get("name", "").strip()
        if not name:
            workflows_skipped += 1
            continue

        if name in skip_names:
            if is_patch:
                skipped_by_base += 1
            else:
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
        # 非补丁模式下避免重复导入同名工作流
        if not is_patch:
            skip_names.add(name)

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
        "is_patch": is_patch,
        "base_version": base_version,
        "skipped_by_base": skipped_by_base,
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


def _collect_base_workflow_names(base_version: str) -> set:
    """从已安装的基础包中收集工作流名集合（含基础包 + 该版本之前的所有补丁）。

    查找策略：在 _installed_packs 中找到所有 pack_version_label <= base_version
    的包（包括基础包和该版本前的补丁），合并它们的 workflow_names。
    """
    installed = get_installed_packs()
    names = set()
    for p in installed:
        if p.get("pack_version_label") and p.get("pack_version_label") <= base_version:
            for n in p.get("workflow_names", []) or []:
                names.add(n)
    return names


def _save_pack_record(manifest: dict):
    """记录已安装的内容包信息（基础包 / 增量补丁均保存）。"""
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
