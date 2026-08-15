"""构建 .jspack 内容包文件。

.jspack 本质是 ZIP 格式，包含：
  - manifest.json    包描述
  - workflows.json   工作流列表
  - plugins/         插件 .py 文件

用法：
    python build_pack.py [pack_version]

示例：
    python build_pack.py v1
"""
import json
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def build_pack(version: str = "v1") -> str:
    """构建指定版本的内容包，返回输出文件路径。"""
    pack_dir = SCRIPT_DIR / "packs" / version
    if not pack_dir.exists():
        raise FileNotFoundError(f"版本目录不存在: {pack_dir}")

    manifest_path = pack_dir / "manifest.json"
    workflows_path = pack_dir / "pro_workflows.json"
    plugins_dir = pack_dir / "plugins"

    if not manifest_path.exists():
        raise FileNotFoundError(f"缺少 manifest.json: {manifest_path}")
    if not workflows_path.exists():
        raise FileNotFoundError(f"缺少 pro_workflows.json: {workflows_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    workflows = json.loads(workflows_path.read_text(encoding="utf-8"))

    # 输出文件名
    pack_name = manifest.get("name", f"content-pack-{version}").replace(" ", "_")
    output_path = SCRIPT_DIR / f"{pack_name}.jspack"

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 写入 manifest
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        # 写入工作流
        zf.writestr("workflows.json", json.dumps(workflows, ensure_ascii=False, indent=2))

        # 写入插件
        if plugins_dir.exists():
            for py_file in plugins_dir.glob("*.py"):
                zf.write(py_file, f"plugins/{py_file.name}")

    print(f"[ok] 已生成内容包: {output_path}")
    print(f"     工作流: {len(workflows)} 个")
    plugins_count = len(list(plugins_dir.glob("*.py"))) if plugins_dir.exists() else 0
    print(f"     插件: {plugins_count} 个")
    print(f"     大小: {output_path.stat().st_size / 1024:.1f} KB")
    return str(output_path)


if __name__ == "__main__":
    import sys
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    build_pack(version)
