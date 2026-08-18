"""从工作流 JSON 自动生成教程 markdown。"""
import json
from pathlib import Path

# 节点类型说明
NODE_DESCRIPTIONS = {
    "source_fetch": "从数据源拉取原始数据",
    "target_write": "将处理结果写入目标库",
    "filter": "按条件过滤数据",
    "sort": "排序",
    "group_by": "分组聚合",
    "dedup": "去重",
    "resample": "重采样（如 1 分钟→30 分钟）",
    "ma": "计算移动平均线（MA/EMA）",
    "macd": "计算 MACD 指标",
    "rsi": "计算 RSI 指标",
    "boll": "计算布林带（BOLL）",
    "expression": "表达式计算（自定义公式）",
    "condition": "条件分支（if/else）",
    "custom_python": "自定义 Python 脚本",
    "column_rename": "列重命名",
    "factor_compute": "因子计算",
    "factor_write": "因子写入",
    "set_variable": "设置变量",
    "for_each": "循环遍历",
    "loop": "条件循环",
    "wait": "等待（控制频率）",
    "outlier_handler": "异常值处理（官方插件）",
    "fill_suspended": "停牌日填充（官方插件）",
    "label_future_return": "未来收益标签（官方插件）",
    "volume_price_divergence": "量价背离检测（官方插件）",
    "candlestick_pattern": "K 线形态识别（官方插件）",
    "max_drawdown": "最大回撤计算（官方插件）",
    "time_window": "时间窗口处理",
}

# 插件类型说明
PLUGIN_DESCRIPTIONS = {
    "outlier_handler": "检测并处理异常值（乌龙指、脏数据），支持 zscore/iqr/multiplier 三种方法",
    "fill_suspended": "补齐 A 股停牌/缺失交易日，支持 ffill/interpolate/zero 三种填充方式",
    "label_future_return": "基于未来 N 日收益率生成机器学习标签（分类/回归）",
    "volume_price_divergence": "检测价格与指标之间的顶背离/底背离（MACD/RSI/成交量/自定义）",
    "candlestick_pattern": "识别 10 种经典 K 线形态（锤子线、吞没、十字星、启明星、黄昏星等）",
    "max_drawdown": "计算最大回撤、回撤持续天数、夏普比率、索提诺比率、卡尔玛比率",
}


def generate_tutorial(workflow: dict, example_id: int) -> str:
    """为单个工作流生成教程 markdown。"""
    name = workflow.get("name", "未命名")
    description = workflow.get("description", "")
    wf_json = workflow.get("workflow_json", {})
    nodes = wf_json.get("nodes", [])
    connections = wf_json.get("connections", {})

    # 教程标题
    lines = [
        f"## 📋 示例{example_id} 详解：{name}",
        "",
        "### 🎯 目标",
        "",
        description or "本示例演示如何使用金智汇联 ETL 工具构建自动化数据处理工作流。",
        "",
        "---",
        "",
        "### 🔗 节点流程图",
        "",
        "```",
    ]

    # 生成流程图（简单的线性或分支图）
    # 找到起始节点（没有入度的节点）
    in_degree = {n["id"]: 0 for n in nodes}
    for src, targets in connections.items():
        for t in targets:
            if t in in_degree:
                in_degree[t] += 1

    start_nodes = [n for n in nodes if in_degree.get(n["id"], 0) == 0]
    if not start_nodes:
        start_nodes = nodes[:1]

    # 简单的线性流程图
    node_map = {n["id"]: n for n in nodes}
    visited = set()
    flow_lines = []

    def dfs(node_id, indent=0):
        if node_id in visited or node_id not in node_map:
            return
        visited.add(node_id)
        node = node_map[node_id]
        node_type = node.get("type", "unknown")
        node_name = node.get("name", node_type)
        prefix = "  " * indent
        flow_lines.append(f"{prefix}┌─ {node_name} ({node_type})")
        for target in connections.get(node_id, []):
            dfs(target, indent + 1)

    for start in start_nodes:
        dfs(start["id"])

    lines.append("\n".join(flow_lines) if flow_lines else "  [工作流节点]")
    lines.extend(["```", "", "---", "", "### 📦 各节点详解", ""])

    # 逐个节点说明
    for i, node in enumerate(nodes, 1):
        node_id = node.get("id", f"n{i}")
        node_type = node.get("type", "unknown")
        node_name = node.get("name", node_type)
        parameters = node.get("parameters", {})

        lines.append(f"#### {i}️⃣ {node_id}: {node_name}")
        lines.append("")
        lines.append(f"| 配置项 | 说明 |")
        lines.append(f"|-------|------|")
        lines.append(f"| 节点 ID | `{node_id}` |")
        lines.append(f"| 节点类型 | `{node_type}` |")
        lines.append(f"| 功能 | {NODE_DESCRIPTIONS.get(node_type, '自定义处理')} |")

        if parameters:
            lines.append(f"| 参数 | {json.dumps(parameters, ensure_ascii=False)[:200]} |")

        lines.append("")

    # 使用场景
    lines.extend([
        "---",
        "",
        "### 💡 使用场景",
        "",
        f"本示例适用于需要**{description[:50] if description else '自动化数据处理'}**的场景。",
        "",
        "### ⚠️ 注意事项",
        "",
        "1. 确保已配置对应的数据源连接",
        "2. 根据实际数据调整参数配置",
        "3. 大数据量时建议分批处理",
        "",
    ])

    return "\n".join(lines)


def main():
    """为所有工作流生成教程。"""
    workflows_path = Path("pro-content/workflows-extracted.json")
    if not workflows_path.exists():
        print("❌ workflows-extracted.json 不存在，请先提取工作流")
        return

    with open(workflows_path, encoding="utf-8") as f:
        workflows = json.load(f)

    docs_dir = Path("pro-content/docs")
    docs_dir.mkdir(exist_ok=True)

    print(f"为 {len(workflows)} 个工作流生成教程...")

    for i, wf in enumerate(workflows, 1):
        tutorial = generate_tutorial(wf, i)
        # 文件名：01-数据源拉取.md
        name = wf.get("name", "未命名")
        # 清理文件名
        safe_name = "".join(c for c in name if c.isalnum() or c in " -_").strip()[:30]
        filename = docs_dir / f"{i:02d}-{safe_name}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(tutorial)
        print(f"  [OK] {i:02d}: {filename.name}")

    print(f"\n[OK] 教程已生成到 {docs_dir}/")


if __name__ == "__main__":
    main()
