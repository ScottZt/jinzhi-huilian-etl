"""从 docs/example_workflows.md 提取工作流 JSON，生成 pro_workflows.json。

此脚本在闭源仓库中使用，用于生成内容包的工作流数据。
"""
import re
import json
from pathlib import Path

# 找到开源仓库的 docs 目录
SCRIPT_DIR = Path(__file__).resolve().parent
# quantsync-pro 和 quantsync-etl 在同一父目录下
OPEN_SOURCE_ROOT = SCRIPT_DIR.parent / "quantsync-etl"
MD_PATH = OPEN_SOURCE_ROOT / "docs" / "example_workflows.md"
OUT_PATH = SCRIPT_DIR / "pro_workflows.json"


def extract_workflows(md_text: str) -> list[dict]:
    """从 markdown 中提取所有工作流 JSON。"""
    parts = re.split(r"(?=^## \d+\. )", md_text, flags=re.M)
    out = []
    for p in parts:
        m = re.match(r"^## (\d+)\.\s*(.+?)\n", p)
        if not m:
            continue
        num, title = int(m.group(1)), m.group(2).strip()
        jm = re.search(r"```json\s*(\{.+?\})\s*```", p, re.S)
        if not jm:
            print(f"[skip] #{num} {title}: 未找到 JSON")
            continue
        try:
            wf = json.loads(jm.group(1))
        except Exception as e:
            print(f"[skip] #{num} {title}: JSON 解析失败 - {e}")
            continue
        dm = re.search(r"\*\*说明\*\*[:：]\s*(.+)", p)
        desc = dm.group(1).strip() if dm else ""
        desc = re.sub(r"\*\*[^*]+\*\*[:：]?\s*", "", desc).strip()
        out.append({
            "id": num,
            "name": f"示例{num}: {title}",
            "description": desc,
            "workflow_json": wf,
        })
    out.sort(key=lambda x: x["id"])
    return out


def main():
    if not MD_PATH.exists():
        print(f"[error] 找不到 markdown 文件: {MD_PATH}")
        print("请确保在正确的目录运行此脚本，或修改 OPEN_SOURCE_ROOT 路径")
        return

    md_text = MD_PATH.read_text(encoding="utf-8")
    workflows = extract_workflows(md_text)

    OUT_PATH.write_text(
        json.dumps(workflows, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[ok] 已提取 {len(workflows)} 个工作流 -> {OUT_PATH.name}")
    for wf in workflows:
        node_count = len(wf.get("workflow_json", {}).get("nodes", []))
        print(f"  #{wf['id']:2d} {wf['name'][:40]:<42s} {node_count} 节点")


if __name__ == "__main__":
    main()
