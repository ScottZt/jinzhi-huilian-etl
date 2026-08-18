"""双仓库一键推送脚本。

同步 main → open-source，清理敏感内容后推送到 GitHub；同时推送 main 到 Gitee。

用法：
  python scripts/push_all.py               # 正常推送（含安全检查）
  python scripts/push_all.py --dry-run     # 预览，不实际执行
  python scripts/push_all.py --skip-check  # 跳过安全检查（紧急推送）
  python scripts/push_all.py --message "描述" # 指定 open-source 清理 commit 信息
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path


def run(cmd: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """执行 shell 命令。"""
    print(f"$ {cmd}")
    result = subprocess.run(
        cmd, shell=True,
        capture_output=capture, text=True,
    )
    if check and result.returncode != 0:
        print(f"[ERROR] 命令失败: {result.stderr or result.stdout}", file=sys.stderr)
        sys.exit(1)
    return result


def get_git_info() -> dict:
    """获取当前 git 状态。"""
    branch = run("git branch --show-current", capture=True).stdout.strip()
    status = run("git status --porcelain", capture=True).stdout.strip()
    return {"branch": branch, "dirty": bool(status), "status": status}


def security_check() -> list[str]:
    """在 open-source 分支执行安全检查，返回失败项列表。"""
    failures = []

    # 1. pro-content
    if Path("pro-content").exists() and any(Path("pro-content").iterdir()):
        failures.append("pro-content/ 目录存在")

    # 2. 私钥
    key_files = list(Path(".").rglob("license_private_key.pem"))
    if key_files:
        failures.append(f"发现私钥文件: {key_files[0]}")

    # 3. 官方插件源码
    official_py = [f for f in Path("backend/plugins").glob("official_*.py")]
    if official_py:
        failures.append(f"发现 {len(official_py)} 个 official_*.py 源码")

    # 4. 打包脚本
    for script in ["scripts/pack_jspack.py", "scripts/export_pro_workflows.py"]:
        if Path(script).exists():
            failures.append(f"{script} 存在")

    # 5. 打包产物
    jspack_files = list(Path("dist").glob("*.jspack"))
    if jspack_files:
        failures.append(f"dist/ 下有 {len(jspack_files)} 个 .jspack 文件")

    return failures


def push_all(args):
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)
    print(f"[工作目录] {repo_root}")
    print()

    # ========== 阶段 1：main 分支推送 ==========
    print("=" * 60)
    print(" 阶段 1：推送 main → Gitee")
    print("=" * 60)

    info = get_git_info()
    if info["branch"] != "main":
        print(f"[ERROR] 当前在 {info['branch']} 分支，请先切到 main")
        sys.exit(1)

    if info["dirty"]:
        print("[ERROR] main 分支有未提交的更改，请先 commit")
        print(info["status"])
        sys.exit(1)

    print("[OK] main 分支干净")
    print()

    if args.dry_run:
        print("[DRY-RUN] git push 金汇智连 main")
    else:
        run("git push 金汇智连 main")
    print()

    # ========== 阶段 2：同步到 open-source 并清理 ==========
    print("=" * 60)
    print(" 阶段 2：同步 main → open-source")
    print("=" * 60)

    if args.dry_run:
        print("[DRY-RUN] git checkout open-source")
        print("[DRY-RUN] git merge main --no-edit")
    else:
        run("git checkout open-source")
        run("git merge main --no-edit")

    # 清理敏感内容
    files_to_remove = [
        "backend/plugins/official_divergence.py",
        "backend/plugins/official_drawdown.py",
        "backend/plugins/official_future_label.py",
        "backend/plugins/official_outlier.py",
        "backend/plugins/official_pattern.py",
        "backend/plugins/official_suspended.py",
        "scripts/pack_jspack.py",
        "scripts/export_pro_workflows.py",
        "scripts/gen_example_docs.py",
        "pro-content",
        "dist/pro-pack-v1.jspack",
    ]

    print()
    print("[清理敏感内容]")
    for f in files_to_remove:
        p = Path(f)
        if p.exists():
            if p.is_dir():
                if args.dry_run:
                    print(f"  [DRY-RUN] rm -rf {f}/")
                else:
                    import shutil
                    shutil.rmtree(p)
                    print(f"  [OK] 删除 {f}/")
            else:
                if args.dry_run:
                    print(f"  [DRY-RUN] rm {f}")
                else:
                    p.unlink()
                    print(f"  [OK] 删除 {f}")
        else:
            print(f"  [SKIP] {f} 不存在")
    print()

    # 安全检查
    if not args.skip_check:
        print("[安全检查]")
        failures = security_check()
        if failures:
            print("[FAIL] 以下检查未通过：")
            for f in failures:
                print(f"  - {f}")
            print()
            print("如需强制推送，加 --skip-check 参数")
            sys.exit(1)
        print("[OK] 安全检查通过")
        print()

    # 提交清理
    if args.dry_run:
        print(f'[DRY-RUN] git add -A && git commit -m "{args.message}"')
    else:
        run("git add -A")
        # 检查是否有变更需要提交
        status = run("git status --porcelain", capture=True).stdout.strip()
        if status:
            run(f'git commit -m "{args.message}"')
            print("[OK] 已提交清理 commit")
        else:
            print("[SKIP] 无变更，跳过 commit")
    print()

    # 推送 open-source → GitHub
    if args.dry_run:
        print("[DRY-RUN] git push origin open-source:main")
    else:
        run("git push origin open-source:main")
    print()

    # ========== 阶段 3：切回 main ==========
    print("=" * 60)
    print(" 阶段 3：切回 main")
    print("=" * 60)

    if args.dry_run:
        print("[DRY-RUN] git checkout main")
    else:
        run("git checkout main")

    print()
    print("=" * 60)
    print(" ✅ 推送完成！")
    print("=" * 60)
    print()
    print("  main        → Gitee 私有仓库   ✅")
    print("  open-source → GitHub 公开仓库  ✅")
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="双仓库一键推送脚本")
    ap.add_argument("--dry-run", action="store_true", help="预览模式，不实际执行")
    ap.add_argument("--skip-check", action="store_true", help="跳过安全检查")
    ap.add_argument("--message", default="chore: 同步 main 并清理敏感内容",
                    help="open-source 清理 commit 信息（默认：chore: 同步 main 并清理敏感内容）")
    args = ap.parse_args()
    push_all(args)
