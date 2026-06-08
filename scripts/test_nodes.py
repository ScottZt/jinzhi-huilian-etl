"""ETL 节点测试脚本 — 直接用 Python 运行，测试各节点是否正常。

用法:
    python scripts/test_nodes.py          # 测试全部节点
    python scripts/test_nodes.py ma macd  # 只测试指定节点
"""
import sys
import os
from pathlib import Path

# 确保 backend 在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
backend_dir = PROJECT_ROOT / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import numpy as np
import pandas as pd

from app.core.workflow_engine import get_workflow_engine
from app.nodes import register_all_nodes


# ============================================================
# 样本数据工厂
# ============================================================

def make_kline_data(rows=120):
    """分钟 K 线样本数据，含 code/dt/OHLCV。"""
    np.random.seed(42)
    base = pd.Timestamp("2026-01-05 09:30")
    prices = 100 + np.cumsum(np.random.randn(rows) * 0.1)
    return pd.DataFrame({
        "code": "000001",
        "dt": [base + pd.Timedelta(minutes=i) for i in range(rows)],
        "open": prices - 0.05,
        "high": prices + 0.1,
        "low": prices - 0.1,
        "close": prices,
        "vol": np.random.randint(500, 5000, rows),
        "amount": prices * np.random.randint(500, 5000, rows),
    })


def make_multi_code_data():
    """多股票 K 线样本数据。"""
    frames = []
    for code in ["000001", "600000", "000002"]:
        np.random.seed(hash(code) % 2**32)
        n = 60
        base = pd.Timestamp("2026-01-05 09:30")
        prices = 10 + np.cumsum(np.random.randn(n) * 0.05)
        frames.append(pd.DataFrame({
            "code": code,
            "dt": [base + pd.Timedelta(minutes=i) for i in range(n)],
            "open": prices - 0.03,
            "high": prices + 0.08,
            "low": prices - 0.06,
            "close": prices,
            "vol": np.random.randint(200, 3000, n),
            "amount": prices * np.random.randint(200, 3000, n),
        }))
    return pd.concat(frames, ignore_index=True)


def make_trade_data():
    """成交明细样本数据。"""
    return pd.DataFrame([
        {"symbol": "IF2406", "price": 4123.2, "qty": 2, "side": "BUY"},
        {"symbol": "IF2406", "price": 4123.6, "qty": 1, "side": "SELL"},
        {"symbol": "IC2406", "price": 5890.0, "qty": 3, "side": "BUY"},
        {"symbol": "IC2406", "price": 5888.2, "qty": 1, "side": "BUY"},
        {"symbol": "IH2406", "price": None, "qty": 2, "side": "SELL"},
    ])


# ============================================================
# 测试用例定义
# ============================================================

TEST_CASES = {}


def register_test(node_type, name, workflow, initial_data_fn=make_kline_data):
    TEST_CASES[node_type] = {"name": name, "workflow": workflow, "data_fn": initial_data_fn}


# --- column_rename ---
register_test("column_rename", "列重命名", {
    "nodes": [{"id": "n1", "name": "重命名", "type": "column_rename",
               "parameters": {"renames": "code=stock_code,close=last_price"}}],
    "connections": {},
}, make_kline_data)

# --- expression ---
register_test("expression", "表达式计算", {
    "nodes": [{"id": "n1", "name": "涨跌幅", "type": "expression",
               "parameters": {"target_column": "pct", "expression": "(df['close'] - df['open']) / df['open'] * 100"}}],
    "connections": {},
}, make_kline_data)

# --- filter ---
register_test("filter", "数据过滤", {
    "nodes": [{"id": "n1", "name": "过滤", "type": "filter",
               "parameters": {"mode": "keep", "conditions": [
                   {"column": "vol", "operator": ">", "value": 1000}
               ]}}],
    "connections": {},
}, make_kline_data)

# --- sort ---
register_test("sort", "排序", {
    "nodes": [{"id": "n1", "name": "排序", "type": "sort",
               "parameters": {"by": "close", "ascending": False}}],
    "connections": {},
}, make_kline_data)

# --- group_by ---
register_test("group_by", "分组聚合", {
    "nodes": [{"id": "n1", "name": "分组", "type": "group_by",
               "parameters": {"group_by": "code", "aggregations": "open=first,close=max,vol=sum"}}],
    "connections": {},
}, make_multi_code_data)

# --- condition ---
register_test("condition", "条件分支", {
    "nodes": [{"id": "n1", "name": "条件", "type": "condition",
               "parameters": {"condition": "df['close'] > df['open']", "branch": "true"}}],
    "connections": {},
}, make_kline_data)

# --- custom_python ---
register_test("custom_python", "自定义 Python 脚本", {
    "nodes": [{"id": "n1", "name": "自定义", "type": "custom_python",
               "parameters": {"code": "def process(df):\n    df['ratio'] = df['high'] / df['low']\n    return df"}}],
    "connections": {},
}, make_kline_data)

# --- resample ---
register_test("resample", "周期重采样", {
    "nodes": [{"id": "n1", "name": "重采样", "type": "resample",
               "parameters": {"rule": "30min", "time_column": "dt", "group_column": ""}}],
    "connections": {},
}, make_kline_data)

# --- ma ---
register_test("ma", "移动平均(MA/EMA)", {
    "nodes": [{"id": "n1", "name": "MA", "type": "ma",
               "parameters": {"windows": "5,10,20", "source_column": "close", "use_ema": False}}],
    "connections": {},
}, make_kline_data)

# --- ma (EMA) ---
register_test("ma_ema", "移动平均(EMA)", {
    "nodes": [{"id": "n1", "name": "EMA", "type": "ma",
               "parameters": {"windows": "12,26", "source_column": "close", "use_ema": True}}],
    "connections": {},
}, make_kline_data)

# --- macd ---
register_test("macd", "MACD 指标", {
    "nodes": [{"id": "n1", "name": "MACD", "type": "macd",
               "parameters": {"fast": 12, "slow": 26, "signal": 9, "source_column": "close"}}],
    "connections": {},
}, make_kline_data)

# --- rsi ---
register_test("rsi", "RSI 相对强弱", {
    "nodes": [{"id": "n1", "name": "RSI", "type": "rsi",
               "parameters": {"window": 14, "source_column": "close"}}],
    "connections": {},
}, make_kline_data)

# --- boll ---
register_test("boll", "布林带(BOLL)", {
    "nodes": [{"id": "n1", "name": "BOLL", "type": "boll",
               "parameters": {"window": 20, "std_mult": 2, "source_column": "close"}}],
    "connections": {},
}, make_kline_data)

# --- dedup ---
register_test("dedup", "数据去重", {
    "nodes": [{"id": "n1", "name": "去重", "type": "dedup",
               "parameters": {"mode": "keep_last", "columns": "code,dt"}}],
    "connections": {},
}, make_multi_code_data)

# --- time_window ---
register_test("time_window", "时间窗口分批", {
    "nodes": [{"id": "n1", "name": "时间窗口", "type": "time_window",
               "parameters": {"window_size": 7, "window_step": 7, "time_column": "dt", "sort_first": True}}],
    "connections": {},
}, make_kline_data)


# ============================================================
# 执行器
# ============================================================

def run_test(key, verbose=True):
    case = TEST_CASES.get(key)
    if not case:
        print(f"[SKIP] 未找到测试用例: {key}")
        print(f"    可用节点: {', '.join(TEST_CASES.keys())}")
        return False

    engine = get_workflow_engine()
    engine.register_all()

    df = case["data_fn"]()
    if verbose:
        print(f"\n{'='*60}")
        print(f" 测试: {case['name']} [{key}]")
        print(f" 输入: {len(df)} 行 x {len(df.columns)} 列")
        print(f" 输入列: {df.columns.tolist()}")

    try:
        result, timings = engine.execute(case["workflow"], initial_df=df)
    except Exception as e:
        print(f"[FAIL] 执行失败: {e}")
        return False

    if verbose:
        print(f" 输出: {len(result)} 行 x {len(result.columns)} 列")
        print(f" 输出列: {result.columns.tolist()}")
        for node, t in timings.items():
            print(f" 耗时: {node} = {t}s")
        print(f"\n 输出前 5 行:")
        print(result.head(5).to_string(index=False))

    if result.empty:
        print(f"[WARN] 输出为空 DataFrame")
        return False

    print(f"[PASS] 通过")
    return True


def run_all():
    engine = get_workflow_engine()
    engine.register_all()

    passed = 0
    failed = 0
    total = len(TEST_CASES)

    print(f"\n开始测试 {total} 个节点...\n")

    for key, case in TEST_CASES.items():
        ok = run_test(key, verbose=True)
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f" 总计: {total} | 通过: {passed} | 失败: {failed}")
    print(f"{'='*60}")
    return failed == 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 测试指定节点
        for node_key in sys.argv[1:]:
            run_test(node_key)
    else:
        run_all()
