"""打包 .jspack 内容包 —— 开发者工具。

.jspack 本质是 ZIP，结构：
  - manifest.json     包描述（pack_version=1.0 / name / workflows_count / plugins / ...）
  - workflows.json    工作流列表 [{name, description, workflow_json}, ...]
  - plugins/          (可选) 插件 .py 文件

用法：
  # 从工作流 JSON 目录打包（每个 .json 是一个工作流）
  python scripts/pack_jspack.py --workflows-dir ./my-workflows -n "金智汇联专业版内容包" -o dist/pro-pack-v1.jspack

  # 从工作流 JSON 目录 + 插件目录打包
  python scripts/pack_jspack.py --workflows-dir ./wf --plugins-dir ./plugins -n "..." -o out.jspack

  # 只打包插件（不含工作流）
  python scripts/pack_jspack.py --plugins-dir ./plugins -n "高级插件包" -o plugins.jspack

  # 从当前数据库已安装的工作流打包（含名字过滤）
  python scripts/pack_jspack.py --from-db -n "我的备份" -o backup.jspack

工作流 JSON 文件格式（单个工作流一个文件）：
  {
    "name": "TDX本地数据 → 写入DuckDB",
    "description": "...",
    "workflow": { "nodes": [...], "edges": [...] }
  }
  或
  {
    "name": "...",
    "description": "...",
    "workflow_json": { "nodes": [...], "edges": [...] }
  }
"""
import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path


def _load_workflow_file(p: Path) -> dict:
    """读取单个工作流 JSON 文件，兼容 workflow / workflow_json 两种字段名。"""
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{p} 不是合法的工作流 JSON（应为对象）")
    if "workflow_json" in data:
        wf_json = data["workflow_json"]
    elif "workflow" in data:
        wf_json = data["workflow"]
    else:
        raise ValueError(f"{p} 缺少 workflow / workflow_json 字段")
    # 名称优先级：title > name > 文件 stem
    name = (data.get("title") or data.get("name") or "").strip() or p.stem
    return {
        "name": name,
        "description": data.get("description", ""),
        "workflow_json": wf_json,
    }


def pack(
    output: Path,
    name: str,
    pack_version: str = "1.0",
    version: str = "1.0",
    description: str = "",
    workflows_dir: Path | None = None,
    plugins_dir: Path | None = None,
    from_db: bool = False,
) -> dict:
    """生成 .jspack 文件。"""
    workflows: list[dict] = []
    plugins: list[Path] = []

    # 1) 工作流来源 A：目录扫描
    if workflows_dir:
        if not workflows_dir.is_dir():
            raise FileNotFoundError(f"工作流目录不存在: {workflows_dir}")
        for f in sorted(workflows_dir.glob("*.json")):
            try:
                workflows.append(_load_workflow_file(f))
            except Exception as e:
                print(f"[warn] 跳过 {f.name}: {e}", file=sys.stderr)

    # 2) 工作流来源 B：当前数据库
    if from_db:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
        try:
            from app.persistence import sqlite_repo
            rows = sqlite_repo.list_workflows() or []
            for r in rows:
                workflows.append({
                    "name": r.get("name", ""),
                    "description": r.get("description", ""),
                    "workflow_json": r.get("workflow_json") or {},
                })
            print(f"[info] 从数据库读取 {len(rows)} 个工作流", file=sys.stderr)
        except Exception as e:
            raise RuntimeError(f"从数据库读取工作流失败: {e}") from e

    # 3) 插件
    if plugins_dir:
        if not plugins_dir.is_dir():
            raise FileNotFoundError(f"插件目录不存在: {plugins_dir}")
        # 排除示例/元数据文件
        excluded = {"example_plugin.py", "official.json", "__init__.py"}
        plugins = sorted(
            p for p in plugins_dir.glob("*.py")
            if not p.name.startswith("_") and p.name not in excluded
        )

    # 4) manifest
    manifest = {
        "pack_version": pack_version,
        "name": name,
        "pack_version_label": version,
        "edition": "professional",
        "workflows_count": len(workflows),
        "plugins": [p.stem for p in plugins],
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "description": description or f"包含 {len(workflows)} 个工作流模板 + {len(plugins)} 个插件",
    }

    # 5) 写入 ZIP
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("workflows.json", json.dumps(workflows, ensure_ascii=False, indent=2))
        for p in plugins:
            zf.write(p, arcname=f"plugins/{p.name}")

    return {
        "output": str(output),
        "workflows": len(workflows),
        "plugins": [p.stem for p in plugins],
        "manifest": manifest,
    }


def main():
    ap = argparse.ArgumentParser(description="打包 .jspack 内容包")
    ap.add_argument("--workflows-dir", type=Path, help="工作流 JSON 文件目录")
    ap.add_argument("--plugins-dir", type=Path, help="插件 .py 文件目录")
    ap.add_argument("--from-db", action="store_true", help="从当前数据库已安装的工作流打包")
    ap.add_argument("-n", "--name", required=True, help="内容包名称（如「金智汇联专业版内容包」）")
    ap.add_argument("-o", "--output", required=True, type=Path, help="输出 .jspack 文件路径")
    ap.add_argument("--version", default="1.0", help="包版本号（默认 1.0）")
    ap.add_argument("--description", default="", help="包描述（可选）")
    args = ap.parse_args()

    if not args.workflows_dir and not args.plugins_dir and not args.from_db:
        ap.error("至少需要指定 --workflows-dir / --plugins-dir / --from-db 之一")

    result = pack(
        output=args.output,
        name=args.name,
        version=args.version,
        description=args.description,
        workflows_dir=args.workflows_dir,
        plugins_dir=args.plugins_dir,
        from_db=args.from_db,
    )
    print(f"[OK] 打包完成: {result['output']}")
    print(f"   工作流: {result['workflows']} 个")
    print(f"   插件:   {len(result['plugins'])} 个 {result['plugins']}")


if __name__ == "__main__":
    # Windows 终端默认 GBK，强制 UTF-8 输出以避免 emoji / 中文乱码
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
