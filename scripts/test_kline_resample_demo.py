"""实际跑一遍 kline_resample，验证能生成多种分钟级数据。

构造 A 股 1 天完整 1min 数据（240 根），合成为 5/15/30/60/90/120min，
展示每种周期的输出结果。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pandas as pd
from app.nodes.kline_resample import KlineResampleNode


def build_1min_a_stock_full_day(day="2024-01-02", code="000001"):
    """构造 A 股一天完整 1min 数据（上午 120 根 + 下午 120 根 = 240 根）。"""
    rows = []
    price = 10.0
    # 上午 09:30-11:29（120 根）
    for i in range(120):
        m = 9 * 60 + 30 + i
        dt = f"{day} {m // 60:02d}:{m % 60:02d}:00"
        # 模拟价格波动
        price += (i % 7 - 3) * 0.01
        rows.append({
            "code": code, "dt": dt,
            "open": price, "high": price + 0.02,
            "low": price - 0.02, "close": price + 0.01,
            "vol": 1000 + i * 10, "amount": 10000 + i * 100,
        })
    # 下午 13:00-14:59（120 根）
    for i in range(120):
        m = 13 * 60 + i
        dt = f"{day} {m // 60:02d}:{m % 60:02d}:00"
        price += (i % 5 - 2) * 0.015
        rows.append({
            "code": code, "dt": dt,
            "open": price, "high": price + 0.02,
            "low": price - 0.02, "close": price + 0.01,
            "vol": 1200 + i * 8, "amount": 12000 + i * 80,
        })
    return pd.DataFrame(rows)


def test_resample_to_minutes(df_1min: pd.DataFrame, minutes: int):
    """合成指定分钟数，返回结果 DataFrame。"""
    node = KlineResampleNode()
    params = {
        "minutes": minutes,
        "time_column": "dt",
        "group_column": "code",
        "mode": "session",
        "sessions": "09:30-11:30,13:00-15:00",
        "drop_incomplete": True,  # 丢弃不完整的 bar
    }
    result = node.process(df_1min, params)
    return result


def main():
    print("=" * 70)
    print("构造 1min 数据（A 股一天 240 根）")
    print("=" * 70)
    df_1min = build_1min_a_stock_full_day()
    # 转换 dt 为 Timestamp，便于后续比较
    df_1min["dt"] = pd.to_datetime(df_1min["dt"])
    print(f"输入数据：{len(df_1min)} 行")
    print(f"时间范围：{df_1min['dt'].iloc[0]} ~ {df_1min['dt'].iloc[-1]}")
    print()

    test_cases = [
        (5, "5 分钟 K 线"),
        (15, "15 分钟 K 线"),
        (30, "30 分钟 K 线"),
        (60, "60 分钟 K 线（1 小时）"),
        (90, "90 分钟 K 线"),
        (120, "120 分钟 K 线（2 小时）"),
    ]

    for minutes, desc in test_cases:
        print("=" * 70)
        print(f"合成 {desc}")
        print("=" * 70)
        result = test_resample_to_minutes(df_1min, minutes)
        print(f"输出数据：{len(result)} 行")
        if len(result) > 0:
            print(f"时间范围：{result['dt'].iloc[0]} ~ {result['dt'].iloc[-1]}")
            print("\n前 5 根 K 线：")
            print(result[["code", "dt", "open", "high", "low", "close", "vol"]].head(5).to_string(index=False))
            if len(result) > 5:
                print("\n后 5 根 K 线：")
                print(result[["code", "dt", "open", "high", "low", "close", "vol"]].tail(5).to_string(index=False))

            # 验证第一根 bar 的 OHLC 正确性
            first_bar = result.iloc[0]
            # 找到第一根 bar 覆盖的 1min 数据
            bar_start = first_bar["dt"]
            bar_end = bar_start + pd.Timedelta(minutes=minutes)
            covered_1min = df_1min[(df_1min["dt"] >= bar_start) & (df_1min["dt"] < bar_end)]
            print(f"\n第一根 bar 覆盖 {len(covered_1min)} 根 1min 数据")
            print(f"  预期 open={covered_1min.iloc[0]['open']:.4f}, 实际 open={first_bar['open']:.4f} {'[OK]' if abs(first_bar['open'] - covered_1min.iloc[0]['open']) < 0.0001 else '[FAIL]'}")
            print(f"  预期 close={covered_1min.iloc[-1]['close']:.4f}, 实际 close={first_bar['close']:.4f} {'[OK]' if abs(first_bar['close'] - covered_1min.iloc[-1]['close']) < 0.0001 else '[FAIL]'}")
            print(f"  预期 high={covered_1min['high'].max():.4f}, 实际 high={first_bar['high']:.4f} {'[OK]' if abs(first_bar['high'] - covered_1min['high'].max()) < 0.0001 else '[FAIL]'}")
            print(f"  预期 low={covered_1min['low'].min():.4f}, 实际 low={first_bar['low']:.4f} {'[OK]' if abs(first_bar['low'] - covered_1min['low'].min()) < 0.0001 else '[FAIL]'}")
            print(f"  预期 vol={covered_1min['vol'].sum()}, 实际 vol={first_bar['vol']} {'[OK]' if first_bar['vol'] == covered_1min['vol'].sum() else '[FAIL]'}")
        print()


if __name__ == "__main__":
    main()
