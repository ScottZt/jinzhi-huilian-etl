"""从 docs/example_workflows.md 提取专业版工作流 JSON，输出为独立 .json 文件。

配合 scripts/pack_jspack.py 使用，生成可分发的 .jspack 内容包。

用法：
  # 1. 导出 25 个专业工作流 JSON 到 out/ 目录
  python scripts/export_pro_workflows.py -o pro-content/workflows-v1

  # 2. 打包成 .jspack
  python scripts/pack_jspack.py \\
    --workflows-dir pro-content/workflows-v1 \\
    -n "金智汇联专业版内容包 v1" \\
    -o dist/pro-pack-v1.jspack
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "docs" / "example_workflows.md"

# 与 regen_example_workflows_js.py 保持一致
PRO_EXAMPLE_IDS = set(range(1, 26))


def extract_examples(md_text: str) -> list[dict]:
    """解析 md，返回所有带 workflow JSON 的示例。"""
    parts = re.split(r"(?=^## \d+\. )", md_text, flags=re.M)
    out = []
    for p in parts:
        m = re.match(r"^## (\d+)\.\s*(.+?)\n", p)
        if not m:
            continue
        num, title = int(m.group(1)), m.group(2).strip()
        jm = re.search(r"```json\s*(\{.+?\})\s*```", p, re.S)
        if not jm:
            continue
        try:
            wf = json.loads(jm.group(1))
        except Exception as e:
            print(f"[skip] #{num}: {e}")
            continue
        dm = re.search(r"\*\*说明\*\*[:：]\s*(.+)", p)
        desc = dm.group(1).strip() if dm else ""
        desc = re.sub(r"\*\*[^*]+\*\*[:：]?\s*", "", desc).strip()
        out.append({
            "id": num,
            "title": title,
            "description": desc,
            "workflow_json": wf,
        })
    out.sort(key=lambda x: x["id"])
    return out


def slugify(s: str) -> str:
    """标题 → 文件名安全字符串。"""
    s = re.sub(r"[\\/:*?\"<>|]+", "_", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:60]


def main():
    ap = argparse.ArgumentParser(description="导出专业版工作流 JSON")
    ap.add_argument("-o", "--out-dir", required=True, type=Path, help="输出目录")
    ap.add_argument("--ids", default="", help="只导出指定 ID，逗号分隔（默认全部 1..25）")
    args = ap.parse_args()

    md_text = MD_PATH.read_text(encoding="utf-8")
    examples = extract_examples(md_text)

    if args.ids:
        wanted = {int(x) for x in args.ids.split(",") if x.strip()}
        examples = [e for e in examples if e["id"] in wanted]
    else:
        examples = [e for e in examples if e["id"] in PRO_EXAMPLE_IDS]

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for ex in examples:
        filename = f"{ex['id']:02d}-{slugify(ex['title'])}.json"
        target = args.out_dir / filename
        target.write_text(
            json.dumps(ex, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  #{ex['id']:2d} -> {filename}")

    print(f"\n[OK] 导出 {len(examples)} 个工作流 -> {args.out_dir}")


if __name__ == "__main__":
    main()
