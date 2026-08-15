"""把 docs/example_workflows.md 里的示例 JSON 抽出来，
生成 backend/app/static/example_workflows.js 供工作流编辑器「📥 导入示例」弹框消费。

md 中每个示例的格式约定：
    ## <N>. <标题>
    ...
    ```json
    { "nodes": [...], "connections": {...} }
    ```
    **说明**: ...

标签维护在本脚本的 TAGS_MAP 里（不污染 md 文档），输出时带上 tags 字段。

专业版示例（PRO_EXAMPLE_IDS）只输出元数据（id/title/description/tags），
不包含完整 workflow JSON，防止 View Source 泄露。
"""
import re
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "docs" / "example_workflows.md"
OUT_PATH = ROOT / "backend" / "app" / "static" / "example_workflows.js"

# ---------- 专业版示例标记 ----------
# 这些示例的 workflow JSON 不会输出到前端文件，需要从内容包获取
PRO_EXAMPLE_IDS = set(range(1, 26))  # 全部 25 个示例为专业版

# ---------- 示例标签映射 ----------
# 主分类 chips: 全部 / 快速上手 / 数据源 / 指标 / 策略信号 / 数据处理 / 进阶ETL / 复权 / 因子库 / 官方插件
# 次级细分标签（如 tdx/binance/yfinance/并行/增量）也一并打上，搜索框可直接命中
TAGS_MAP = {
    1:  ["快速上手", "数据源", "tdx"],
    2:  ["数据源", "指标", "数据处理", "binance"],
    3:  ["数据源", "指标", "数据处理", "yfinance"],
    4:  ["策略信号", "数据处理"],
    5:  ["快速上手", "数据处理"],
    6:  ["指标", "策略信号"],
    7:  ["数据源", "进阶ETL", "并行"],
    8:  ["进阶ETL", "增量"],
    9:  ["指标", "数据处理"],
    10: ["策略信号", "数据处理", "进阶ETL"],
    11: ["复权", "tdx"],
    12: ["复权", "tdx"],
    13: ["复权"],
    14: ["因子库"],
    15: ["因子库"],
    16: ["因子库"],
    17: ["官方插件", "数据处理", "异常值"],
    18: ["官方插件", "数据处理", "A股"],
    19: ["官方插件", "因子库", "机器学习"],
    20: ["官方插件", "指标", "量价"],
    21: ["官方插件", "指标", "K线"],
    22: ["官方插件", "进阶ETL", "回测"],
    23: ["复权", "进阶ETL", "大数据"],
    24: ["快速上手", "进阶ETL", "循环遍历", "for_each"],
    25: ["进阶ETL", "条件循环", "loop", "分页"],
}

# 弹框顶部 chips 显示顺序（主分类）
FILTER_CHIPS = ["全部", "快速上手", "数据源", "指标", "策略信号", "数据处理", "进阶ETL", "复权", "因子库", "官方插件"]


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
        out.append({
            "id": num,
            "title": title,
            "description": desc,
            "tags": TAGS_MAP.get(num, []),
            "workflow": wf,
        })
    out.sort(key=lambda x: x["id"])
    return out


def main() -> None:
    md_text = MD_PATH.read_text(encoding="utf-8")
    examples = extract_examples(md_text)

    # 专业版示例只保留元数据，移除 workflow JSON（防止 View Source 泄露）
    pro_count = 0
    for ex in examples:
        if ex["id"] in PRO_EXAMPLE_IDS:
            ex.pop("workflow", None)
            pro_count += 1

    payload = {
        "filterChips": FILTER_CHIPS,
        "examples": examples,
    }
    js = (
        "// 自动生成自 docs/example_workflows.md —— 勿手动编辑\n"
        "// 重新生成: python scripts/regen_example_workflows_js.py\n"
        f"window.EXAMPLE_WORKFLOWS_DATA = {json.dumps(payload, ensure_ascii=False, indent=2)};\n"
        "// 兼容旧版：把 examples 也挂到 EXAMPLE_WORKFLOWS\n"
        "window.EXAMPLE_WORKFLOWS = window.EXAMPLE_WORKFLOWS_DATA.examples;\n"
    )
    OUT_PATH.write_text(js, encoding="utf-8")
    print(f"[regen] 已写入 {len(examples)} 个示例 → {OUT_PATH.relative_to(ROOT)}  "
          f"({OUT_PATH.stat().st_size} bytes)")
    print(f"[regen] 其中 {pro_count} 个专业版示例已移除 workflow JSON")
    for ex in examples:
        is_pro = "[P]" if ex["id"] in PRO_EXAMPLE_IDS else "   "
        has_wf = "WF" if "workflow" in ex else "--"
        print(f"  {is_pro} #{ex['id']:2d} [{has_wf}] {ex['title'][:24]:<26s} tags={ex['tags']}")


if __name__ == "__main__":
    main()
