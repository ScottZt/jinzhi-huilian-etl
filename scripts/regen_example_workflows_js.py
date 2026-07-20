"""把 docs/example_workflows.md 里的示例 JSON 抽出来，
生成 backend/app/static/example_workflows.js 供工作流编辑器「📥 导入示例」弹框消费。

md 中每个示例的格式约定：
    ## <N>. <标题>
    ...
    ```json
    { "nodes": [...], "connections": {...} }
    ```
    **说明**: ...
"""
import re
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "docs" / "example_workflows.md"
OUT_PATH = ROOT / "backend" / "app" / "static" / "example_workflows.js"


def extract_examples(md_text: str) -> list[dict]:
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
            print(f"skip #{num}: {e}")
            continue
        dm = re.search(r"\*\*说明\*\*[:：]\s*(.+)", p)
        desc = dm.group(1).strip() if dm else ""
        desc = re.sub(r"\*\*[^*]+\*\*[:：]?\s*", "", desc).strip()
        out.append({"id": num, "title": title, "description": desc, "workflow": wf})
    out.sort(key=lambda x: x["id"])
    return out


def main() -> None:
    md_text = MD_PATH.read_text(encoding="utf-8")
    examples = extract_examples(md_text)
    js = f"// 自动生成自 docs/example_workflows.md —— 勿手动编辑\n// 重新生成: python scripts/regen_example_workflows_js.py\nwindow.EXAMPLE_WORKFLOWS = {json.dumps(examples, ensure_ascii=False, indent=2)};\n"
    OUT_PATH.write_text(js, encoding="utf-8")
    print(f"[regen] 已写入 {len(examples)} 个示例 → {OUT_PATH.relative_to(ROOT)}  ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
