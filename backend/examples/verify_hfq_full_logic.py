"""
快速验证脚本：测试前复权+后复权核心逻辑

直接跑 dat_day 的 3 只股票，验证：
1. baostock 复权因子能否正常拉取
2. 前复权因子计算是否正确（fore = back / latest_back）
3. 后复权价计算是否准确
4. 前复权价在最新日期是否等于未复权价（验证关键性质）
"""
import duckdb
import pandas as pd
import sys

try:
    import baostock as bs
except ImportError:
    print("[ERROR] baostock 未安装，请先运行: pip install baostock")
    sys.exit(1)


# ========== 工具函数 ==========

def normalize_code(c):
    c = str(c).strip().upper()
    if '.' in c:
        return c
    if len(c) == 6 and c.isdigit():
        market = 'SH' if c.startswith(('6', '9')) else 'SZ'
        return f"{c}.{market}"
    return c


def to_baostock_code(c):
    code, market = c.split('.')
    return f"{market.lower()}.{code}"


def merge_factor(chunk, factor_df):
    """广播复权因子，同时返回 back_factor 和 fore_factor"""
    if factor_df is None or factor_df.empty:
        chunk = chunk.copy()
        chunk['back_factor'] = 1.0
        chunk['fore_factor'] = 1.0
        return chunk

    chunk_dt_ns = (
        pd.to_datetime(chunk['trade_time'], utc=True)
        .dt.tz_convert('Asia/Shanghai')
        .dt.tz_localize(None)
        .astype('datetime64[ns]')
    )
    chunk_days = chunk_dt_ns.dt.floor('D').astype('int64') // (24 * 3600 * 10**9)
    chunk_days = pd.Series(chunk_days.values, index=chunk.index)

    fdf = factor_df.copy()
    factor_dt_ns = pd.to_datetime(fdf['dt']).dt.tz_localize(None).astype('datetime64[ns]')
    fdf['day_key'] = factor_dt_ns.dt.floor('D').astype('int64') // (24 * 3600 * 10**9)
    fdf = fdf.sort_values('day_key')

    # 前复权因子 = 后复权因子 / 最新后复权因子
    latest_back = fdf['back_factor'].iloc[-1]
    fdf['fore_factor'] = fdf['back_factor'] / latest_back

    tmp = pd.DataFrame({'day_key': chunk_days}).reset_index(drop=False).rename(columns={'index': 'orig_idx'})
    tmp = tmp.sort_values('day_key')

    merged = pd.merge_asof(
        tmp[['day_key', 'orig_idx']],
        fdf[['day_key', 'back_factor', 'fore_factor']],
        on='day_key',
        direction='backward',
    )
    merged['back_factor'] = merged['back_factor'].ffill().bfill().fillna(1.0)
    merged['fore_factor'] = merged['fore_factor'].ffill().bfill().fillna(1.0)
    merged = merged.sort_values('orig_idx')

    chunk = chunk.copy()
    chunk['back_factor'] = merged['back_factor'].values
    chunk['fore_factor'] = merged['fore_factor'].values
    return chunk


# ========== 主逻辑 ==========

def main():
    SOURCE_DB = "C:/duckdb/quantifydata.duckdb"
    TEST_CODES = ['000001.SZ', '600000.SH', '000002.SZ']

    print(f"[START] 前复权+后复权 快速验证")
    print(f"[TEST] 测试标的: {TEST_CODES}")

    # 1) 拉取复权因子
    print("\n[STEP 1] 拉取 baostock 复权因子")
    lg = bs.login()
    print(f"  baostock 登录: {lg.error_msg}")

    factor_cache = {}
    for code in TEST_CODES:
        rs = bs.query_adjust_factor(
            code=to_baostock_code(code),
            start_date='2000-01-01',
            end_date='2030-12-31',
        )
        rows = []
        while rs.next():
            r = rs.get_row_data()
            if r[3] and r[3] != '':
                rows.append({'dt': r[1], 'back_factor': float(r[3])})
        if rows:
            df = pd.DataFrame(rows)
            df['dt'] = pd.to_datetime(df['dt'])
            factor_cache[code] = df
            print(f"  {code}: {len(df)} 个因子点")
            print(f"    最新 back_factor = {df['back_factor'].iloc[-1]:.6f} @ {df['dt'].iloc[-1].date()}")
            print(f"    最早 back_factor = {df['back_factor'].iloc[0]:.6f} @ {df['dt'].iloc[0].date()}")

    bs.logout()

    # 2) 计算前复权+后复权价并验证
    print("\n[STEP 2] 计算并验证")
    src = duckdb.connect(SOURCE_DB, read_only=True)

    all_ok = True
    for code in TEST_CODES:
        chunk = src.execute(f"""
            SELECT code, trade_time, open, high, low, close, vol, amount
            FROM dat_day
            WHERE code = ?
            ORDER BY trade_time
        """, [code]).fetchdf()

        if chunk.empty:
            print(f"  {code}: 无数据")
            continue

        # 类型转换
        for c in ['open', 'high', 'low', 'close']:
            if chunk[c].dtype == object:
                chunk[c] = pd.to_numeric(chunk[c], errors='coerce')

        chunk = merge_factor(chunk, factor_cache.get(code))

        # 计算复权价
        for c in ['open', 'high', 'low', 'close']:
            chunk[c + '_qfq'] = (chunk[c] * chunk['fore_factor']).round(3)
            chunk[c + '_hfq'] = (chunk[c] * chunk['back_factor']).round(3)

        # 验证关键性质：最新日期的前复权价 ≈ 未复权价
        latest = chunk.iloc[-1]
        qfq_close = latest['close_qfq']
        raw_close = latest['close']
        diff_pct = abs(qfq_close - raw_close) / raw_close * 100

        print(f"\n  {code} ({len(chunk)} 行):")
        print(f"    最新日期: {latest['trade_time']}")
        print(f"    未复权 close: {raw_close}")
        print(f"    前复权 close: {qfq_close}")
        print(f"    后复权 close: {latest['close_hfq']}")
        print(f"    前复权 vs 未复权 偏差: {diff_pct:.4f}%")

        if diff_pct > 0.01:
            print(f"    [WARN] 偏差超过 0.01%，请检查！")
            all_ok = False
        else:
            print(f"    [OK] 前复权最新价 ≈ 未复权最新价（关键性质验证通过）")

        # 后复权连续性检查
        chunk['daily_ret_hfq'] = chunk['close_hfq'] / chunk['close_hfq'].shift(1) - 1
        anomalies = chunk[chunk['daily_ret_hfq'].abs() > 0.5]
        if anomalies.empty:
            print(f"    [OK] 后复权无异常跳变（所有日收益率 < ±50%）")
        else:
            print(f"    [WARN] 后复权发现 {len(anomalies)} 处异常跳变")
            all_ok = False

        # 显示最近 5 行
        print(f"    最近 3 行:")
        print(chunk.tail(3)[['trade_time', 'close', 'close_qfq', 'close_hfq']].to_string(index=False))

    src.close()

    print("\n" + "=" * 50)
    if all_ok:
        print("[PASS] 所有验证通过！可以运行完整工作流。")
    else:
        print("[FAIL] 部分验证未通过，请检查。")

    return all_ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
