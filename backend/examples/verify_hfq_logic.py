"""
临时验证脚本：测试核心复权逻辑

直接跑 dat_day 的 5 只股票，验证：
1. baostock 复权因子能否正常拉取
2. 分钟级因子广播逻辑是否正确
3. 后复权价计算是否准确
"""
import duckdb
import pandas as pd
import baostock as bs
from datetime import datetime


# ========== 工具函数（从 setup 脚本复制） ==========

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
    if factor_df is None or factor_df.empty:
        chunk = chunk.copy()
        chunk['back_factor'] = 1.0
        return chunk

    # 统一转 naive datetime64[ns]（避免 DuckDB us/pandas ns 精度差异，以及时区差异）
    # 然后取天数作为合并键
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

    tmp = pd.DataFrame({'day_key': chunk_days}).reset_index(drop=False).rename(columns={'index': 'orig_idx'})
    tmp = tmp.sort_values('day_key')

    merged = pd.merge_asof(
        tmp[['day_key', 'orig_idx']],
        fdf[['day_key', 'back_factor']],
        on='day_key',
        direction='backward',
    )
    merged['back_factor'] = merged['back_factor'].ffill().bfill().fillna(1.0)
    merged = merged.sort_values('orig_idx')

    chunk = chunk.copy()
    chunk['back_factor'] = merged['back_factor'].values
    return chunk


# ========== 主逻辑 ==========

def main():
    SOURCE_DB = "C:/duckdb/quantifydata.duckdb"
    TEST_CODES = ['000001.SZ', '600000.SH', '000002.SZ', '600036.SH', '000063.SZ']

    print(f"[START] {datetime.now().isoformat()}")
    print(f"[TEST] 测试标的: {TEST_CODES}")

    # 1) 从 dat_day 读取测试标的
    src = duckdb.connect(SOURCE_DB, read_only=True)
    print("\n[STEP 1] 读取源数据")
    for code in TEST_CODES:
        chunk = src.execute(f"""
            SELECT code, trade_time, open, high, low, close, vol, amount
            FROM dat_day
            WHERE code = ?
            ORDER BY trade_time
        """, [code]).fetchdf()
        print(f"  {code}: {len(chunk)} 行, {chunk['trade_time'].min()} ~ {chunk['trade_time'].max()}")
        print(f"    最新 3 行:")
        print(chunk.tail(3)[['trade_time', 'close']].to_string(index=False))
    src.close()

    # 2) 拉取复权因子
    print("\n[STEP 2] 拉取 baostock 复权因子")
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
            print(f"  {code}: {len(df)} 个因子点, 最新 factor={df['back_factor'].iloc[-1]:.4f} @ {df['dt'].iloc[-1].date()}")

    bs.logout()

    # 3) 计算后复权价
    print("\n[STEP 3] 计算后复权价")
    src = duckdb.connect(SOURCE_DB, read_only=True)
    for code in TEST_CODES:
        chunk = src.execute(f"""
            SELECT code, trade_time, open, high, low, close, vol, amount
            FROM dat_day
            WHERE code = ?
            ORDER BY trade_time
        """, [code]).fetchdf()

        chunk = merge_factor(chunk, factor_cache.get(code))
        for c in ['open', 'high', 'low', 'close']:
            chunk[c + '_hfq'] = (chunk[c] * chunk['back_factor']).round(3)

        print(f"\n  {code} 后复权结果（最新 5 行）:")
        print(chunk.tail(5)[['trade_time', 'close', 'back_factor', 'close_hfq']].to_string(index=False))

        # 验证：长期收益率
        total_ret = (chunk['close_hfq'].iloc[-1] / chunk['close_hfq'].iloc[0] - 1) * 100
        print(f"  区间收益率: {total_ret:.2f}% ({chunk['trade_time'].iloc[0].date()} ~ {chunk['trade_time'].iloc[-1].date()})")

    src.close()

    # 4) 跨除权日连续性检查
    print("\n[STEP 4] 跨除权日连续性检查（000001.SZ）")
    src = duckdb.connect(SOURCE_DB, read_only=True)
    chunk = src.execute("""
        SELECT code, trade_time, close
        FROM dat_day WHERE code = '000001.SZ' ORDER BY trade_time
    """).fetchdf()
    chunk = merge_factor(chunk, factor_cache.get('000001.SZ'))
    chunk['close_hfq'] = (chunk['close'] * chunk['back_factor']).round(3)
    chunk['daily_ret'] = chunk['close_hfq'] / chunk['close_hfq'].shift(1) - 1

    # 找最大日收益率变化（应该是正常波动，不是除权跳变）
    max_ret_idx = chunk['daily_ret'].abs().idxmax()
    max_ret_row = chunk.loc[max_ret_idx]
    print(f"  最大单日变化: {max_ret_row['daily_ret']*100:.2f}% @ {max_ret_row['trade_time'].date()}")
    print(f"  相邻两日 close_hfq: {chunk.loc[max_ret_idx-1, 'close_hfq']:.3f} -> {max_ret_row['close_hfq']:.3f}")

    # 检查异常跳变（>50% 视为异常，正常涨跌停 ±10%）
    anomalies = chunk[chunk['daily_ret'].abs() > 0.5]
    if anomalies.empty:
        print("  [OK] 无异常跳变（所有日收益率 < +-50%）")
    else:
        print(f"  [WARN] 发现 {len(anomalies)} 处异常跳变:")
        print(anomalies[['trade_time', 'close_hfq', 'daily_ret']].head(10).to_string(index=False))

    src.close()
    print(f"\n[FINISH] {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
