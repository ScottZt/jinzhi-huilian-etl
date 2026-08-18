"""AI 自动 commit 脚本 — 用大模型总结更改并生成 commit message。

用法：
  python scripts/ai_commit.py                    # 自动总结并 commit
  python scripts/ai_commit.py --dry-run          # 只生成 message，不实际 commit
  python scripts/ai_commit.py --scope "feat"     # 指定 scope（feat/fix/docs/chore 等）
  python scripts/ai_commit.py --no-ai            # 手动输入 message（不用 AI）

配置方式（优先级从高到低）：
  1. 配置文件：scripts/ai_commit.json（推荐，已加入 .gitignore）
  2. 环境变量：AI_COMMIT_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY

配置文件格式：
  {
    "api_key": "sk-...",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "language": "zh"
  }
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def get_git_diff() -> str:
    """获取暂存区的 diff。"""
    result = subprocess.run(
        ["git", "diff", "--staged", "--stat"],
        capture_output=True, text=True,
    )
    stat = result.stdout.strip()

    result = subprocess.run(
        ["git", "diff", "--staged"],
        capture_output=True, text=True,
    )
    diff = result.stdout.strip()

    if not diff:
        # 如果没有暂存区内容，获取工作区 diff
        result = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True, text=True,
        )
        stat = result.stdout.strip()

        result = subprocess.run(
            ["git", "diff"],
            capture_output=True, text=True,
        )
        diff = result.stdout.strip()

    return stat, diff


def get_untracked_files() -> str:
    """获取未跟踪文件列表。"""
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def load_config() -> dict:
    """从配置文件加载设置。"""
    config_path = Path(__file__).parent / "ai_commit.json"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_config(key: str, default: str = "") -> str:
    """获取配置值：配置文件 > 环境变量 > 默认值。"""
    config = load_config()

    # 配置文件优先
    if key in config and config[key]:
        return config[key]

    # 环境变量作为后备
    env_map = {
        "api_key": ["AI_COMMIT_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
        "base_url": ["AI_COMMIT_BASE_URL"],
        "model": ["AI_COMMIT_MODEL"],
        "language": ["AI_COMMIT_LANGUAGE"],
    }

    env_keys = env_map.get(key, [])
    for env_key in env_keys:
        value = os.environ.get(env_key)
        if value:
            return value

    return default


def call_llm(prompt: str) -> str:
    """调用大模型 API 生成 commit message。"""
    api_key = get_config("api_key")
    base_url = get_config("base_url", "https://api.openai.com/v1")
    model = get_config("model", "gpt-4o-mini")
    language = get_config("language", "zh")

    if not api_key:
        print("[ERROR] 未配置 API 密钥")
        print()
        print("请在以下位置之一配置：")
        print("  1. 配置文件：scripts/ai_commit.json")
        print("     {")
        print('       "api_key": "sk-...",')
        print('       "base_url": "https://api.openai.com/v1",')
        print('       "model": "gpt-4o-mini"')
        print("     }")
        print("  2. 环境变量：AI_COMMIT_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY")
        sys.exit(1)

    # 使用 OpenAI 兼容格式
    import requests

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个 git commit message 生成器。根据代码更改生成简洁、准确的 commit message。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 200,
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=data,
        timeout=30,
    )

    if response.status_code != 200:
        print(f"[ERROR] API 调用失败：{response.status_code}")
        print(response.text)
        sys.exit(1)

    result = response.json()
    return result["choices"][0]["message"]["content"].strip()


def generate_commit_message(stat: str, diff: str, untracked: str, scope: str = "") -> str:
    """生成 commit message。"""
    lang = os.environ.get("AI_COMMIT_LANGUAGE", "zh")
    lang_name = "中文" if lang == "zh" else "English"

    prompt = f"""请根据以下 git 更改，生成一条简洁的 commit message（使用{lang_name}）。

要求：
- 第一行：简洁的标题（50 字符以内）
- 可选第二行：空行
- 可选后续行：详细说明（每行 72 字符以内）
- 如果有指定 scope，以 "scope: " 开头

{f"Scope: {scope}" if scope else ""}

## 更改统计
{stat}

## 未跟踪文件
{untracked if untracked else "无"}

## 详细 diff（前 500 行）
{diff[:5000] if diff else "无"}

请直接输出 commit message，不要有其他说明。"""

    return call_llm(prompt)


def commit(message: str, dry_run: bool = False):
    """执行 git commit。"""
    if dry_run:
        print(f"[DRY-RUN] git commit -m \"{message}\"")
        return

    # 先 add 所有更改
    subprocess.run(["git", "add", "-A"], check=True)

    # 检查是否有更改
    result = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
    )
    if result.returncode == 0:
        print("[ERROR] 没有更改需要提交")
        sys.exit(1)

    # 提交
    subprocess.run(
        ["git", "commit", "-m", message],
        check=True,
    )
    print("[OK] 已提交")


def main():
    ap = argparse.ArgumentParser(description="AI 自动 commit 脚本")
    ap.add_argument("--dry-run", action="store_true", help="只生成 message，不实际 commit")
    ap.add_argument("--scope", default="", help="commit scope（如 feat/fix/docs/chore）")
    ap.add_argument("--no-ai", action="store_true", help="手动输入 message（不用 AI）")
    ap.add_argument("--message", default="", help="直接指定 message（跳过 AI 生成）")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)
    print(f"[工作目录] {repo_root}")
    print()

    # 手动输入模式
    if args.no_ai or args.message:
        if args.message:
            message = args.message
        else:
            message = input("请输入 commit message: ").strip()
        if not message:
            print("[ERROR] message 为空")
            sys.exit(1)
        commit(message, args.dry_run)
        return

    # AI 生成模式
    print("[1/3] 获取 git 更改...")
    stat, diff = get_git_diff()
    untracked = get_untracked_files()

    if not stat and not untracked:
        print("[ERROR] 没有更改需要提交")
        sys.exit(1)

    print(f"[2/3] 调用 AI 生成 commit message...")
    message = generate_commit_message(stat, diff, untracked, args.scope)

    print()
    print("=" * 60)
    print(" 生成的 commit message:")
    print("=" * 60)
    print(message)
    print("=" * 60)
    print()

    if args.dry_run:
        print("[DRY-RUN] 模式，不实际提交")
        return

    confirm = input("是否提交？(Y/n): ").strip().lower()
    if confirm in ["", "y", "yes"]:
        commit(message)
    else:
        print("[取消] 未提交")


if __name__ == "__main__":
    main()
