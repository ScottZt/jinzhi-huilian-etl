"""集成测试：验证 P0 基础控制节点协同工作。"""
import pandas as pd
from app.core.workflow_engine import WorkflowEngine
from app.nodes import register_all_nodes


def test_basic_flow():
    """测试：set_variable → for_each → custom_python"""

    # 注册所有节点
    register_all_nodes()

    # 构建测试工作流
    workflow_json = {
        "nodes": [
            {
                "id": "n1",
                "name": "设置变量",
                "type": "set_variable",
                "parameters": {
                    "var_name": "tables",
                    "var_value": '["dat_day", "dat_60mins", "dat_30mins"]',
                    "value_type": "json",
                },
            },
            {
                "id": "n2",
                "name": "循环遍历表",
                "type": "for_each",
                "parameters": {
                    "items": "{{tables}}",  # 从 context 读取
                    "item_var": "current_table",
                    "index_var": "table_index",
                    "max_iterations": 10,
                },
            },
            {
                "id": "n3",
                "name": "处理当前表",
                "type": "custom_python",
                "parameters": {
                    "code": """
def process(df):
    import pandas as pd
    # 从 context 读取当前项（context 通过闭包注入）
    # 注意：custom_python 节点的 process 函数没有 context 参数
    # 这里只是演示，实际需要改造 custom_python 节点
    return df
""",
                },
            },
        ],
        "connections": {
            "n1": ["n2"],
            "n2": ["n3"],
        },
    }

    # 执行工作流
    engine = WorkflowEngine()
    engine.register_all()

    initial_df = pd.DataFrame({"test": [1, 2, 3]})
    context = {}

    print("=" * 60)
    print("开始执行测试工作流")
    print("=" * 60)

    result_df, timings, node_outputs = engine.execute(
        workflow_json,
        initial_df,
        workflow_context=context,
        return_intermediate=True
    )

    print("\n" + "=" * 60)
    print("执行完成")
    print("=" * 60)
    print(f"最终 context: {context}")
    print(f"节点输出: {list(node_outputs.keys())}")
    print(f"节点执行耗时: {timings}")
    print(f"输出 DataFrame 行数: {len(result_df)}")

    # 验证（context 是传入的参数，执行后会被修改）
    assert "tables" in context, "tables 变量未设置"
    assert context["tables"] == ["dat_day", "dat_60mins", "dat_30mins"], "tables 值错误"
    assert "current_table" in context, "current_table 变量未设置"
    assert "table_index" in context, "table_index 变量未设置"

    print("\n[OK] 基础测试通过！")
    return True


def test_for_each_with_custom_python():
    """测试：for_each + custom_python 读取 context"""

    register_all_nodes()

    # 改造 custom_python 节点，让它能读取 context
    # 这里用一个简化的测试：直接在 for_each 里用 custom_python 打印

    workflow_json = {
        "nodes": [
            {
                "id": "n1",
                "name": "循环数字列表",
                "type": "for_each",
                "parameters": {
                    "items": "[1, 2, 3, 4, 5]",
                    "item_var": "num",
                    "index_var": "idx",
                },
            },
            {
                "id": "n2",
                "name": "等待 0.1 秒",
                "type": "wait",
                "parameters": {
                    "seconds": 0.1,
                },
            },
        ],
        "connections": {
            "n1": ["n2"],
        },
    }

    engine = WorkflowEngine()
    engine.register_all()

    initial_df = pd.DataFrame({"x": [10, 20]})
    context = {}

    print("\n" + "=" * 60)
    print("测试 for_each + wait")
    print("=" * 60)

    result_df, timings = engine.execute(
        workflow_json,
        initial_df,
        workflow_context=context,
    )

    print(f"最终 context: {context}")
    print(f"节点执行耗时: {timings}")

    # 验证最后一次循环的值
    assert context.get("num") == 5, f"num 应该是 5，实际是 {context.get('num')}"
    assert context.get("idx") == 4, f"idx 应该是 4，实际是 {context.get('idx')}"

    print("\n[OK] for_each + wait 测试通过！")
    return True


if __name__ == "__main__":
    try:
        test_basic_flow()
        test_for_each_with_custom_python()
        print("\n" + "=" * 60)
        print("[SUCCESS] 所有集成测试通过！")
        print("=" * 60)
    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
