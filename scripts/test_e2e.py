# -*- coding: utf-8 -*-
"""端到端测试：所有预制工作流 + 数据流完整链路验证。

运行：backend/venv/Scripts/python scripts/test_e2e.py
"""
import os
import sys
import json
import time
import tempfile
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(PROJECT_ROOT, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pandas as pd
import numpy as np

# ---------- 模拟真实 Binance 返回格式（7列，无amount）----------

def make_binance_kline(rows=120):
    """模拟 Binance API 返回的 K 线数据（7列）。"""
    np.random.seed(42)
    base = pd.Timestamp("2026-01-05 09:30")
    prices = 50000 + np.cumsum(np.random.randn(rows) * 10)
    return pd.DataFrame({
        "code": "BTCUSDT",
        "dt": [base + pd.Timedelta(minutes=i) for i in range(rows)],
        "open": prices - 5,
        "high": prices + 10,
        "low": prices - 10,
        "close": prices,
        "vol": np.random.randint(100, 5000, rows),
    })


def make_yahoo_daily(rows=120):
    """模拟 Yahoo Finance 日线数据（7列，无amount）。"""
    np.random.seed(99)
    base = pd.Timestamp("2025-06-01")
    prices = 150 + np.cumsum(np.random.randn(rows) * 0.5)
    return pd.DataFrame({
        "code": "AAPL",
        "dt": [base + pd.Timedelta(days=i) for i in range(rows)],
        "open": prices - 0.3,
        "high": prices + 0.8,
        "low": prices - 0.5,
        "close": prices,
        "vol": np.random.randint(50000, 500000, rows),
    })


def make_full_kline(rows=120):
    """模拟完整 K 线数据（8列，含amount）。"""
    np.random.seed(42)
    base = pd.Timestamp("2026-01-05 09:30")
    prices = 10 + np.cumsum(np.random.randn(rows) * 0.05)
    vols = np.random.randint(500, 5000, rows)
    return pd.DataFrame({
        "code": "000001.SZ",
        "dt": [base + pd.Timedelta(minutes=i) for i in range(rows)],
        "open": prices - 0.03,
        "high": prices + 0.08,
        "low": prices - 0.06,
        "close": prices,
        "vol": vols,
        "amount": prices * vols,
    })


def make_trade_data():
    """成交明细数据。"""
    return pd.DataFrame([
        {"symbol": "IF2406", "price": 4123.2, "qty": 2, "side": "BUY"},
        {"symbol": "IF2406", "price": 4123.6, "qty": 1, "side": "SELL"},
        {"symbol": "IC2406", "price": 5890.0, "qty": 3, "side": "BUY"},
        {"symbol": "IC2406", "price": 5888.2, "qty": 1, "side": "BUY"},
        {"symbol": "IH2406", "price": None, "qty": 2, "side": "SELL"},
    ])


def make_tick_data():
    """Tick 数据。"""
    return pd.DataFrame([
        {"code": "600000.SH", "trade_date": "2026-01-05", "price": 10.1, "vol": 120},
        {"code": "600000.SH", "trade_date": "2026-01-05", "price": 10.2, "vol": 80},
        {"code": "600000.SH", "trade_date": "2026-01-06", "price": 10.4, "vol": 100},
        {"code": "000001.SZ", "trade_date": "2026-01-05", "price": 12.3, "vol": 90},
        {"code": "000001.SZ", "trade_date": "2026-01-06", "price": 12.6, "vol": 110},
        {"code": "000001.SZ", "trade_date": "2026-01-06", "price": 12.7, "vol": 60},
    ])


# ---------- 数据源映射 ----------

DATA_MAP = {
    "binance": ("binance", make_binance_kline),
    "yfinance": ("yfinance", make_yahoo_daily),
    "tdx": ("000001", make_full_kline),
    "mootdx": ("000001", make_full_kline),
    "akshare": ("000001", make_full_kline),
    "tushare": ("000001", make_full_kline),
}


def _detect_source_type(nodes):
    """从工作流节点中检测数据源类型。"""
    for n in nodes:
        if n.get("type") == "source_fetch":
            return n.get("parameters", {}).get("source_type", "")
    return None


# ---------- 测试引擎 ----------

class E2ETester:
    def __init__(self):
        from app.core.workflow_engine import get_workflow_engine
        from app.core.workflow_presets import get_workflow_presets
        self.engine = get_workflow_engine()
        self.engine.register_all()
        self.presets = get_workflow_presets()
        self.tmpdir = tempfile.mkdtemp()
        self.results = []

    def _replace_duckdb_path(self, wf_json):
        """将所有 target_write 的 db_path 指向临时目录。"""
        for node in wf_json.get("nodes", []):
            if node.get("type") == "target_write":
                params = node.get("parameters", {})
                cfg_str = params.get("target_config", "{}")
                try:
                    cfg = json.loads(cfg_str)
                except Exception:
                    cfg = {}
                db_path = cfg.get("db_path", "")
                if db_path:
                    table = params.get("target_table", "test_table")
                    cfg["db_path"] = os.path.join(self.tmpdir, f"{table}.db").replace("\\", "/")
                    params["target_config"] = json.dumps(cfg, ensure_ascii=False)

    def test_workflow(self, preset):
        """测试单个工作流（去掉 source_fetch 节点，用模拟数据替代）。"""
        wf = preset["workflow_json"]
        nodes = wf.get("nodes", [])
        node_types = [n.get("type") for n in nodes]

        has_source = "source_fetch" in node_types
        has_target = "target_write" in node_types

        # 构建测试用 workflow（去掉 source_fetch）
        test_nodes = [n for n in nodes if n.get("type") != "source_fetch"]
        test_connections = {}
        # 重建连接：source_fetch 的目标节点改为无前驱
        source_targets = set()
        for src, tgts in wf.get("connections", {}).items():
            src_node = next((n for n in nodes if n["id"] == src), None)
            if src_node and src_node.get("type") == "source_fetch":
                # 记录 source_fetch 指向的第一个目标
                for t in tgts:
                    source_targets.add(t)
            else:
                test_connections[src] = tgts

        test_wf = {
            "nodes": test_nodes,
            "connections": test_connections,
        }

        # 选择模拟数据
        if has_source:
            source_type = _detect_source_type(nodes)
            if "binance" in str(source_type):
                df = make_binance_kline(rows=120)
            elif "yfinance" in str(source_type):
                df = make_yahoo_daily(rows=120)
            else:
                df = make_full_kline(rows=120)
        else:
            # 纯 Transform 使用 sample_data
            sample = preset.get("sample_data", [])
            df = pd.DataFrame(sample) if sample else make_full_kline(rows=120)

        # 替换 DuckDB 路径
        self._replace_duckdb_path(test_wf)

        # 执行
        t0 = time.time()
        try:
            result, timings = self.engine.execute(test_wf, df)
            elapsed = round(time.time() - t0, 3)
            self.results.append({
                "name": preset["name"],
                "key": preset["key"],
                "mode": "闭环" if has_source and has_target else ("仅拉取" if has_source else "Transform"),
                "status": "PASS",
                "input_rows": len(df),
                "output_rows": len(result),
                "output_cols": result.columns.tolist(),
                "timings": timings,
                "elapsed": elapsed,
                "error": None,
            })
        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            self.results.append({
                "name": preset["name"],
                "key": preset["key"],
                "mode": "闭环" if has_source and has_target else ("仅拉取" if has_source else "Transform"),
                "status": "FAIL",
                "input_rows": len(df),
                "output_rows": 0,
                "output_cols": [],
                "timings": {},
                "elapsed": elapsed,
                "error": str(e),
            })

    def run_all(self):
        print(f"\n{'='*70}")
        print(f" E2E 端到端测试 — 全部预制工作流")
        print(f"{'='*70}")
        print(f" 预制工作流数量: {len(self.presets)}")
        print(f" 临时目录: {self.tmpdir}")
        print()

        for i, preset in enumerate(self.presets, 1):
            print(f"[{i}/{len(self.presets)}] {preset['name']}")
            self.test_workflow(preset)

        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")

        print(f"\n{'='*70}")
        print(f" 总计: {len(self.results)} | 通过: {passed} | 失败: {failed}")
        print(f"{'='*70}\n")

        for r in self.results:
            status = "PASS" if r["status"] == "PASS" else "FAIL"
            icon = "[OK]" if r["status"] == "PASS" else "[XX]"
            print(f"  {icon} [{status}] {r['name']}")
            if r["status"] == "PASS":
                print(f"       输入 {r['input_rows']}行 → 输出 {r['output_rows']}行 x {len(r['output_cols'])}列")
                print(f"       输出列: {', '.join(r['output_cols'][:15])}{'...' if len(r['output_cols']) > 15 else ''}")
                print(f"       耗时: {r['elapsed']}s")
            else:
                print(f"       错误: {r['error']}")
            print()

        # 输出失败详情和修复建议
        if failed > 0:
            print(f"\n{'='*70}")
            print(" 失败工作流修复建议:")
            print(f"{'='*70}\n")
            for r in self.results:
                if r["status"] == "FAIL":
                    print(f"  工作流: {r['name']}")
                    print(f"  错误: {r['error']}")
                    print()

        return failed == 0


if __name__ == "__main__":
    tester = E2ETester()
    ok = tester.run_all()
    sys.exit(0 if ok else 1)
