"""构建 .jspack 内容包文件。

.jspack 本质是 ZIP 格式，包含：
  - manifest.json    包描述（可内嵌激活码）
  - workflows.json   工作流列表
  - plugins/         插件 .py 文件

用法：
    python build_pack.py [pack_version] [--activation-code CODE]

示例：
    # 构建不带激活码的内容包（用户需手动激活）
    python build_pack.py v1

    # 构建带激活码的内容包（导入时自动激活）
    python build_pack.py v1 --activation-code "personal:2027-12-31:xxx"

    # 使用 gen_license.py 生成激活码并嵌入
    python build_pack.py v1 --gen-activation personal --expires 2027-12-31
"""
import json
import zipfile
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def build_pack(version: str = "v1", activation_code: str = None) -> str:
    """构建指定版本的内容包，返回输出文件路径。

    Args:
        version: 版本目录名（如 "v1"）
        activation_code: 可选，嵌入的激活码
    """
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

    # 如果有激活码，嵌入到 manifest
    if activation_code:
        manifest["activation_code"] = activation_code

    # 输出文件名（带激活码的加后缀）
    pack_name = manifest.get("name", f"content-pack-{version}").replace(" ", "_")
    suffix = "_with_license" if activation_code else ""
    output_path = SCRIPT_DIR / f"{pack_name}{suffix}.jspack"

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
    if activation_code:
        lic_type = activation_code.split(":")[0] if ":" in activation_code else "unknown"
        print(f"     激活码: 已嵌入 ({lic_type})")
    else:
        print(f"     激活码: 无（用户需手动激活）")
    print(f"     大小: {output_path.stat().st_size / 1024:.1f} KB")
    return str(output_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="构建 .jspack 内容包")
    parser.add_argument("version", nargs="?", default="v1", help="版本目录名")
    parser.add_argument("--activation-code", dest="activation_code",
                        help="嵌入的激活码（格式: type:expires:signature）")
    parser.add_argument("--gen-activation", dest="gen_type",
                        choices=["personal", "professional"],
                        help="自动生成激活码并嵌入（指定类型）")
    parser.add_argument("--expires", default="lifetime",
                        help="激活码过期日期（配合 --gen-activation 使用）")
    args = parser.parse_args()

    activation_code = args.activation_code

    # 如果需要自动生成激活码
    if args.gen_type:
        sys.path.insert(0, str(SCRIPT_DIR / "license"))
        try:
            from gen_license import load_private_key, generate_code
            private_key = load_private_key()
            activation_code = generate_code(private_key, args.gen_type, args.expires)
            print(f"[info] 已生成激活码: {activation_code[:30]}...")
        except ImportError as e:
            print(f"[error] 无法生成激活码: {e}")
            print("        请确保 license/gen_license.py 存在")
            sys.exit(1)

    build_pack(args.version, activation_code)
