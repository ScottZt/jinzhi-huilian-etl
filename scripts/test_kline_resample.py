"""手动跑一遍 kline_resample 的核心算法，验证关键场景。"""
import sys, os
# 从 scripts/ 的父目录（项目根）加入 sys.path，让 app.* 可导入
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_here, "..", "backend")))

import pandas as pd
from app.nodes.kline_resample import KlineResampleNode, _parse_sessions, _assign_session_bar


def build_1min_a_stock(day="2024-01-02", code="000001"):
    """构造 A 股一天完整的 1min 数据（上午 120 根 + 下午 120 根 = 240 根）。"""
    rows = []
    # 上午 09:30-11:29（120 根，最后一根 11:29-11:30）
    for i in range(120):
        m = 9 * 60 + 30 + i
        rows.append((code, f"{day} {m // 60:02d}:{m % 60:02d}:00", 10.0 + i * 0.01))
    # 下午 13:00-14:59（120 根）
    for i in range(120):
        m = 13 * 60 + i
        rows.append((code, f"{day} {m // 60:02d}:{m % 60:02d}:00", 10.0 + i * 0.01))
    df = pd.DataFrame(rows, columns=["code", "dt", "price"])
    # 模拟 OHLC
    df["open"] = df["price"]
    df["high"] = df["price"] + 0.005
    df["low"] = df["price"] - 0.005
    df["close"] = df["price"] + 0.002
    df["vol"] = 100
    df["amount"] = 1000
    return df


def test_parse_sessions():
    # 普通
    s = _parse_sessions("09:30-11:30,13:00-15:00")
    assert s == [(570, 690), (780, 900)], s
    # 跨午夜
    s = _parse_sessions("21:00-02:30")
    assert s == [(1260, 1590)], s  # 1590 = 2*60+30+1440
    # 格式错误
    try:
        _parse_sessions("abc")
        assert False, "应该抛异常"
    except ValueError:
        pass
    print("[OK] _parse_sessions")


def test_assign_session_bar():
    sessions = [(570, 690), (780, 900)]  # A股
    # 9:30 → session 0, bar 0（以 5min 为例）
    assert _assign_session_bar(570, sessions, 5) == (0, 0)
    # 10:00 → session 0, bar 6 (30min / 5min)
    assert _assign_session_bar(600, sessions, 5) == (0, 6)
    # 11:35 → 不在任何时段（午休中）
    assert _assign_session_bar(11 * 60 + 35, sessions, 5) is None
    # 13:00 → session 1, bar 0
    assert _assign_session_bar(780, sessions, 5) == (1, 0)
    # 跨午夜：21:00 in 21:00-02:30
    sessions2 = [(1260, 1590)]
    assert _assign_session_bar(21 * 60, sessions2, 1) == (0, 0)
    # 次日 01:00 → 60+1440=1500; 1500-1260=240; 240//1=240
    assert _assign_session_bar(1 * 60, sessions2, 1) == (0, 240)
    # 90min 合成：11:00 在 09:30-11:30 内 → offset=90, bar_idx=1
    assert _assign_session_bar(11 * 60, sessions, 90) == (0, 1)
    print("[OK] _assign_session_bar")


def test_90min_no_cross_lunch():
    """核心：90min 合成不能跨午休。A 股上午 120min → 1 根满(90) + 1 根不满(30)。"""
    df = build_1min_a_stock()
    node = KlineResampleNode()

    # drop_incomplete=False：保留不完整 bar
    params = {"minutes": 90, "mode": "session",
              "sessions": "09:30-11:30,13:00-15:00",
              "drop_incomplete": False}
    r = node.process(df, params)
    # 上午：bar0=[9:30,11:00) 90 根，bar1=[11:00,11:30) 30 根
    # 下午：bar0=[13:00,14:30) 90 根，bar1=[14:30,15:00) 30 根
    # 共 4 根
    assert len(r) == 4, f"预期 4 根，实际 {len(r)}:\n{r[['code','dt']]}"
    # 关键断言：第二根 bar 的 dt 应该是 11:00（不是 12:30，那会跨午休）
    times = r["dt"].dt.strftime("%H:%M").tolist()
    assert times == ["09:30", "11:00", "13:00", "14:30"], f"时间错误：{times}"

    # drop_incomplete=True：丢弃不满 90 根的 bar
    params["drop_incomplete"] = True
    r2 = node.process(df, params)
    assert len(r2) == 2, f"预期 2 根（丢弃 2 根不满），实际 {len(r2)}"
    times2 = r2["dt"].dt.strftime("%H:%M").tolist()
    assert times2 == ["09:30", "13:00"], f"时间错误：{times2}"

    # 关键：OHLC 正确性
    first = r2.iloc[0]
    assert first["open"] == df.iloc[0]["open"], "第一根 open 应该是第 1 分钟的 open"
    # 第一根覆盖 9:30-11:00 共 90 根，最后一根是 index 89
    assert first["close"] == df.iloc[89]["close"], "第一根 close 应该是第 90 分钟的 close"
    assert first["high"] == df.iloc[:90]["high"].max()
    assert first["low"] == df.iloc[:90]["low"].min()
    assert first["vol"] == 90 * 100

    print("[OK] 90min 合成不跨午休")


def test_natural_mode():
    """自然分钟对齐：7x24 市场直接用 floor。"""
    # 构造连续 7x24 数据 3 小时
    rows = []
    base = pd.Timestamp("2024-01-02 00:00:00")
    for i in range(180):
        rows.append(("BTC", base + pd.Timedelta(minutes=i), 100.0 + i * 0.1))
    df = pd.DataFrame(rows, columns=["code", "dt", "price"])
    df["open"] = df["price"]; df["high"] = df["price"] + 0.05
    df["low"] = df["price"] - 0.05; df["close"] = df["price"] + 0.02
    df["vol"] = 1; df["amount"] = 100

    node = KlineResampleNode()
    r = node.process(df, {"minutes": 15, "mode": "natural", "drop_incomplete": False})
    # 180 / 15 = 12 根
    assert len(r) == 12, f"预期 12 根，实际 {len(r)}"
    # 第一根 00:00，第二根 00:15，...
    times = r["dt"].dt.strftime("%H:%M").tolist()
    assert times[0] == "00:00" and times[1] == "00:15" and times[-1] == "02:45", times
    print("[OK] natural 模式")


def test_group_column_empty():
    """不分组：整表合成。"""
    df = build_1min_a_stock()
    node = KlineResampleNode()
    r = node.process(df, {"minutes": 30, "mode": "session",
                          "sessions": "09:30-11:30,13:00-15:00",
                          "group_column": "", "drop_incomplete": False})
    # 120/30=4 (上午) + 120/30=4 (下午) = 8
    assert len(r) == 8, f"预期 8，实际 {len(r)}"
    print("[OK] 不分组")


def test_empty_df():
    df = pd.DataFrame(columns=["code", "dt", "open", "high", "low", "close", "vol"])
    node = KlineResampleNode()
    r = node.process(df, {"minutes": 5})
    assert r.empty
    print("[OK] 空 DataFrame")


def test_preset_alias():
    """sessions 字段可以填预设名 'a_stock'。"""
    df = build_1min_a_stock()
    node = KlineResampleNode()
    r = node.process(df, {"minutes": 30, "mode": "session",
                          "sessions": "a_stock", "drop_incomplete": False})
    assert len(r) == 8
    print("[OK] 预设别名")


if __name__ == "__main__":
    test_parse_sessions()
    test_assign_session_bar()
    test_90min_no_cross_lunch()
    test_natural_mode()
    test_group_column_empty()
    test_empty_df()
    test_preset_alias()
    print("\n全部通过")
