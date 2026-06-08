# -*- coding: utf-8 -*-
"""Pipeline 层智能识别工作流能力的测试。

验证 Pipeline 在不同工作流能力下是否正确跳过/执行 Source/Target。
运行：backend/venv/Scripts/python scripts/test_pipeline_integration.py
"""
import os
import sys
import json
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(PROJECT_ROOT, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pandas as pd

from app.api.pipelines import _analyze_workflow_capabilities, _build_pipeline_preview
from app.core.workflow_presets import get_workflow_presets
from app.persistence import sqlite_repo
from app.core.workflow_engine import get_workflow_engine


def _make_test_pipeline(workflow_id, wf_json, sources=None, target=None):
    """构造测试用 Pipeline 字典。"""
    if sources is None:
        sources = [{"connection_id": "test_conn", "params": {"codes": ["000001"], "interval": "1min"}}]
    if target is None:
        target = {"connection_id": "duckdb_conn", "table": "test_table"}
    return {
        "id": "test_pipeline",
        "name": "测试Pipeline",
        "pipeline_json": {
            "sources": sources,
            "target": target,
            "workflow_id": workflow_id,
            "field_mappings": [],
            "batch_size": 5000,
            "on_duplicate": "ignore",
        },
    }


def test_capabilities_analysis():
    """测试能力检测函数。"""
    print("\n=== 测试1: _analyze_workflow_capabilities ===\n")

    # 纯 Transform
    wf1 = {"nodes": [
        {"type": "resample"}, {"type": "ma"}, {"type": "filter"}
    ]}
    caps1 = _analyze_workflow_capabilities(wf1)
    assert caps1 == set(), f"纯Transform应为空集, 实际: {caps1}"
    print("  [OK] 纯 Transform 工作流 → 无能力检测通过")

    # 含 source_fetch
    wf2 = {"nodes": [
        {"type": "source_fetch"}, {"type": "resample"}, {"type": "filter"}
    ]}
    caps2 = _analyze_workflow_capabilities(wf2)
    assert caps2 == {"source_fetch"}, f"应为source_fetch, 实际: {caps2}"
    print("  [OK] 含 source_fetch → 检测通过")

    # 含 target_write
    wf3 = {"nodes": [
        {"type": "resample"}, {"type": "filter"}, {"type": "target_write"}
    ]}
    caps3 = _analyze_workflow_capabilities(wf3)
    assert caps3 == {"target_write"}, f"应为target_write, 实际: {caps3}"
    print("  [OK] 含 target_write → 检测通过")

    # 完整闭环
    wf4 = {"nodes": [
        {"type": "source_fetch"}, {"type": "resample"},
        {"type": "filter"}, {"type": "target_write"}
    ]}
    caps4 = _analyze_workflow_capabilities(wf4)
    assert caps4 == {"source_fetch", "target_write"}, f"应为两者, 实际: {caps4}"
    print("  [OK] 完整闭环 → 检测通过")


def test_all_presets():
    """测试所有预制工作流的实际执行（通过临时数据库）。"""
    print("\n=== 测试2: 所有预制工作流执行 ===\n")

    tmpdir = tempfile.mkdtemp()

    engine = get_workflow_engine()
    engine.register_all()
    presets = get_workflow_presets()

    for preset in presets:
        wf = preset["workflow_json"]
        nodes = wf.get("nodes", [])
        node_types = [n.get("type") for n in nodes]
        has_source = "source_fetch" in node_types
        has_target = "target_write" in node_types

        mode = "闭环" if has_source and has_target else ("仅Source" if has_source else "Transform")
        caps = _analyze_workflow_capabilities(wf)

        # 去掉 source_fetch 节点构建测试用 workflow
        test_nodes = [n for n in nodes if n.get("type") != "source_fetch"]
        test_connections = {}
        for src, tgts in wf.get("connections", {}).items():
            src_node = next((nn for nn in nodes if nn["id"] == src), None)
            if src_node and src_node.get("type") == "source_fetch":
                continue
            test_connections[src] = tgts

        test_wf = {"nodes": test_nodes, "connections": test_connections}

        # 替换 DuckDB 路径
        for node in test_wf["nodes"]:
            if node.get("type") == "target_write":
                params = node.get("parameters", {})
                cfg_str = params.get("target_config", "{}")
                try:
                    cfg = json.loads(cfg_str)
                except Exception:
                    cfg = {}
                table = params.get("target_table", "test")
                cfg["db_path"] = os.path.join(tmpdir, f"{table}.db").replace("\\", "/")
                params["target_config"] = json.dumps(cfg, ensure_ascii=False)

        # 选择数据
        if has_source:
            source_type = ""
            for n in nodes:
                if n.get("type") == "source_fetch":
                    source_type = n.get("parameters", {}).get("source_type", "")
                    break
            if "binance" in str(source_type):
                np = __import__("numpy")
                np.random.seed(42)
                base = pd.Timestamp("2026-01-05 09:30")
                prices = 50000 + np.cumsum(np.random.randn(120) * 10)
                df = pd.DataFrame({
                    "code": "BTCUSDT",
                    "dt": [base + pd.Timedelta(minutes=i) for i in range(120)],
                    "open": prices - 5, "high": prices + 10, "low": prices - 10,
                    "close": prices, "vol": np.random.randint(100, 5000, 120),
                })
            elif "yfinance" in str(source_type):
                np = __import__("numpy")
                np.random.seed(99)
                base = pd.Timestamp("2025-06-01")
                prices = 150 + np.cumsum(np.random.randn(120) * 0.5)
                df = pd.DataFrame({
                    "code": "AAPL",
                    "dt": [base + pd.Timedelta(days=i) for i in range(120)],
                    "open": prices - 0.3, "high": prices + 0.8, "low": prices - 0.5,
                    "close": prices, "vol": np.random.randint(50000, 500000, 120),
                })
            else:
                df = pd.DataFrame(preset.get("sample_data", []))
        else:
            sample = preset.get("sample_data", [])
            df = pd.DataFrame(sample) if sample else pd.DataFrame()

        # 执行
        try:
            result, timings = engine.execute(test_wf, df)
            status = "PASS"
            if has_target:
                # 验证 target_write 返回状态记录
                if "_write_status" in result.columns:
                    status = "PASS"
                elif len(result) == 0:
                    status = "FAIL (输出为空)"
            else:
                if len(result) > 0:
                    status = "PASS"
                else:
                    status = "FAIL (输出为空)"
        except Exception as e:
            status = f"FAIL ({e})"
            result = pd.DataFrame()
            timings = {}

        icon = "[OK]" if status == "PASS" else "[XX]"
        print(f"  {icon} [{mode}] {preset['name']}")
        if result is not None and len(result.columns) > 0:
            print(f"       输入 {len(df)}行 → 输出 {len(result)}行 x {len(result.columns)}列")
            print(f"       输出列: {', '.join(result.columns.tolist()[:12])}")
        else:
            print(f"       输入 {len(df)}行 → 无输出")
        if status != "PASS":
            print(f"       错误: {status}")
        print()

    print(f"  临时目录: {tmpdir}")


def test_pipeline_preview_with_source_fetch():
    """测试 Pipeline 预览识别 source_fetch 工作流。"""
    print("\n=== 测试3: Pipeline 预览含 source_fetch 的工作流 ===\n")

    # 先将闭环工作流写入数据库
    from app.api.workflows import _upsert_workflow_by_name
    for preset in get_workflow_presets():
        _upsert_workflow_by_name(
            name=preset["name"],
            description=preset["description"],
            workflow_json=preset["workflow_json"],
            overwrite_existing=True,
        )

    # 找到闭环工作流
    for preset in get_workflow_presets():
        wf = preset["workflow_json"]
        nodes = wf.get("nodes", [])
        node_types = [n.get("type") for n in nodes]
        if "source_fetch" not in node_types:
            continue

        wf_data = None
        for wf in sqlite_repo.list_workflows():
            if wf.get("name") == preset["name"]:
                wf_data = wf
                break
        if not wf_data:
            continue

        # 构造 Pipeline（含 source_fetch 工作流）
        pipeline = _make_test_pipeline(
            workflow_id=wf_data["id"],
            wf_json=wf_data["workflow_json"],
            # 故意不配 source，测试 Pipeline 是否正确跳过
            sources=[],
        )

        try:
            preview = _build_pipeline_preview(pipeline)
            if "error" in preview:
                print(f"  [XX] {preset['name']} 预览报错: {preview['error']}")
            else:
                print(f"  [OK] {preset['name']}")
                print(f"       返回 {preview.get('rows', 0)}行, {len(preview.get('columns', []))}列")
                print(f"       来源: {preview.get('sources', [])}")
        except Exception as e:
            print(f"  [XX] {preset['name']} 异常: {e}")
        print()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print(" Pipeline 集成测试")
    print("=" * 70)

    test_capabilities_analysis()
    test_all_presets()
    test_pipeline_preview_with_source_fetch()

    print("\n" + "=" * 70)
    print(" 全部测试完成")
    print("=" * 70 + "\n")
