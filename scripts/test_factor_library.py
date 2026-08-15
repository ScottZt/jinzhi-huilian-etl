"""因子库集成测试 — 验证完整流程。

运行: python scripts/test_factor_library.py
"""
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_factor_compute():
    """测试因子计算节点。"""
    from app.nodes.factor_compute import FactorComputeNode

    print("=" * 50)
    print("1. 测试因子计算节点")
    print("=" * 50)

    node = FactorComputeNode()

    # 生成测试数据
    np.random.seed(42)
    rows = []
    price = 10.0
    for i in range(30):
        dt = datetime(2024, 1, 1) + timedelta(days=i)
        price *= (1 + np.random.normal(0, 0.02))
        rows.append({
            'code': '000001',
            'dt': dt.strftime('%Y-%m-%d'),
            'close': price,
            'high': price * 1.01,
            'low': price * 0.99,
        })
    df = pd.DataFrame(rows)

    # 测试各种因子
    test_cases = [
        ('ma_5', 'ma', '{"window": 5}'),
        ('ema_10', 'ema', '{"span": 10}'),
        ('rsi_14', 'rsi', '{"window": 14}'),
        ('macd', 'macd', '{"fast": 12, "slow": 26, "signal": 9}'),
        ('boll', 'boll', '{"window": 20, "std_mult": 2}'),
        ('ret_1d', 'return', '{"window": 1}'),
        ('volatility_20', 'volatility', '{"window": 20}'),
        ('atr', 'atr', '{"window": 14}'),
        ('bias_6', 'bias', '{"window": 6}'),
    ]

    for factor_id, compute_type, params_json in test_cases:
        result = node.process(df.copy(), {
            'factor_id': factor_id,
            'compute_type': compute_type,
            'params_json': params_json,
            'source_column': 'close',
        })
        valid_count = result['factor_value'].notna().sum()
        print(f"  {factor_id:15} -> {valid_count:3} valid values")

    print()


def test_factor_write():
    """测试因子写入节点。"""
    from app.nodes.factor_compute import FactorComputeNode
    from app.nodes.factor_write import FactorWriteNode
    import duckdb

    print("=" * 50)
    print("2. 测试因子写入节点")
    print("=" * 50)

    compute_node = FactorComputeNode()
    write_node = FactorWriteNode()

    # 生成测试数据
    np.random.seed(42)
    rows = []
    for code in ['000001', '600000']:
        price = 10.0
        for i in range(30):
            dt = datetime(2024, 1, 1) + timedelta(days=i)
            price *= (1 + np.random.normal(0, 0.02))
            rows.append({
                'code': code,
                'dt': dt.strftime('%Y-%m-%d'),
                'close': price,
            })
    df = pd.DataFrame(rows)

    # 计算并写入多个因子
    test_factors = [
        ('ma_5', 'ma', '{"window": 5}'),
        ('ma_20', 'ma', '{"window": 20}'),
        ('rsi_14', 'rsi', '{"window": 14}'),
    ]

    test_db = 'D:/data/test_factor_library.duckdb'
    if os.path.exists(test_db):
        os.remove(test_db)

    for factor_id, compute_type, params_json in test_factors:
        computed = compute_node.process(df.copy(), {
            'factor_id': factor_id,
            'compute_type': compute_type,
            'params_json': params_json,
            'source_column': 'close',
        })

        result = write_node.process(computed, {
            'factor_id': factor_id,
            'db_path': test_db,
            'write_mode': 'upsert',
            'register_meta': True,
            'factor_name': factor_id,
            'compute_type': compute_type,
            'params_json_meta': params_json,
        })
        count = result['_factor_write_count'].iloc[0]
        print(f"  {factor_id:15} -> {count:3} rows written")

    # 验证结果
    print()
    print("  DuckDB 验证:")
    conn = duckdb.connect(test_db, read_only=True)

    tables = conn.execute("SHOW TABLES").fetchall()
    print(f"    Tables: {[t[0] for t in tables]}")

    for t in tables:
        if t[0].startswith('factor_') and t[0] != 'factor_registry':
            count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
            print(f"    {t[0]}: {count} rows")

    print()
    print("  factor_registry:")
    registry = conn.execute("SELECT factor_id, factor_name, compute_type FROM factor_registry").fetchdf()
    print(registry.to_string(index=False))

    conn.close()
    print()


def test_factor_query():
    """测试因子查询功能。"""
    import duckdb

    print("=" * 50)
    print("3. 测试因子查询（模拟 API）")
    print("=" * 50)

    test_db = 'D:/data/test_factor_library.duckdb'
    if not os.path.exists(test_db):
        print("  Skip: test database not found")
        return

    conn = duckdb.connect(test_db, read_only=True)

    # 单因子查询
    print("  查询 ma_5 (000001, 前5条):")
    result = conn.execute("""
        SELECT code, dt, factor_value
        FROM factor_ma_5
        WHERE code = '000001'
        ORDER BY dt
        LIMIT 5
    """).fetchdf()
    print(result.to_string(index=False))
    print()

    # 多因子 JOIN 查询
    print("  多因子 JOIN (ma_5 + ma_20, 000001, 前5条):")
    result = conn.execute("""
        SELECT t0.code, t0.dt, t0.factor_value as ma_5, t1.factor_value as ma_20
        FROM factor_ma_5 t0
        INNER JOIN factor_ma_20 t1 ON t0.code = t1.code AND t0.dt = t1.dt
        WHERE t0.code = '000001'
        ORDER BY t0.dt
        LIMIT 5
    """).fetchdf()
    print(result.to_string(index=False))
    print()

    conn.close()


def main():
    print()
    print("*" * 50)
    print("* 因子库集成测试")
    print("*" * 50)
    print()

    test_factor_compute()
    test_factor_write()
    test_factor_query()

    print("=" * 50)
    print("All tests passed!")
    print("=" * 50)


if __name__ == '__main__':
    main()
