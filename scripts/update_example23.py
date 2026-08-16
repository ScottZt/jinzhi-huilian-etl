# -*- coding: utf-8 -*-
"""更新示例23为多节点版：for_each 拆表 + custom_python 自接管 I/O"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "docs" / "example_workflows.md"

# ========== custom_python 代码（处理单张表，从 context 读 current_table） ==========

CUSTOM_CODE = r'''# ========== 配置 ==========
SOURCE_DB = 'C:/duckdb/quantifydata.duckdb'
TARGET_DB = 'C:/duckdb/quantifydata_adj.duckdb'

# ========== 工具函数 ==========

def normalize_code(c):
    # 统一为 '000001.SZ' 大写格式
    c = str(c).strip().upper()
    if '.' in c:
        return c
    if len(c) == 6 and c.isdigit():
        market = 'SH' if c.startswith(('6', '9')) else 'SZ'
        return f"{c}.{market}"
    return c

def to_baostock_code(c):
    # '000001.SZ' -> 'sz.000001' 或 6位纯数字 -> 'sz.000001'
    c = str(c).strip().upper()
    if '.' in c:
        code, market = c.split('.')
        return f"{market.lower()}.{code}"
    c = c.zfill(6)
    return ('sh.' + c) if c.startswith(('6', '9')) else ('sz.' + c)

def to_bare_code(c):
    # '000001.SZ' -> '000001'
    c = str(c).strip()
    if '.' in c:
        return c.split('.')[0]
    return c.zfill(6)

def merge_factor(chunk, factor_df):
    # 把日频复权因子广播到分钟级 chunk。
    # 同一天所有分钟 K 线共享同一个因子。
    # 返回 chunk 新增列: fore, back
    import pandas as pd
    if factor_df is None or factor_df.empty:
        chunk = chunk.copy()
        chunk['fore'] = 1.0
        chunk['back'] = 1.0
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

    tmp = pd.DataFrame({'day_key': chunk_days}).reset_index(drop=False).rename(columns={'index': 'orig_idx'})
    tmp = tmp.sort_values('day_key')

    merged = pd.merge_asof(
        tmp[['day_key', 'orig_idx']],
        fdf[['day_key', 'fore', 'back']],
        on='day_key',
        direction='backward',
    )
    merged['fore'] = merged['fore'].ffill().bfill()
    merged['back'] = merged['back'].ffill().bfill()
    merged = merged.sort_values('orig_idx')

    chunk = chunk.copy()
    chunk['fore'] = merged['fore'].values
    chunk['back'] = merged['back'].values
    return chunk

# ========== 主逻辑 ==========

def process(df, context=None):
    import duckdb
    import pandas as pd
    import baostock as bs
    import gc
    from datetime import datetime

    # 从 for_each 的 context 读取当前表名
    current_table = 'dat_day'
    if context:
        current_table = context.get('current_table', context.get('current_item', 'dat_day'))

    print(f"[START] 处理表: {current_table} - {datetime.now().isoformat()}")
    print(f"[CONFIG] 源库: {SOURCE_DB}")
    print(f"[CONFIG] 目标库: {TARGET_DB}")

    tbl = current_table
    tbl_raw = tbl + '_raw'
    tbl_qfq = tbl + '_qfq'
    tbl_hfq = tbl + '_hfq'

    # 1) 收集当前表的所有 code
    src_ro = duckdb.connect(SOURCE_DB, read_only=True)
    try:
        rows = src_ro.execute(f"SELECT DISTINCT code FROM {tbl}").fetchall()
        all_codes = sorted(set(normalize_code(r[0]) for r in rows))
    except Exception as e:
        print(f"[ERROR] 表 {tbl} 查询失败：{e}")
        src_ro.close()
        return pd.DataFrame([{'status': 'error', 'table': tbl, 'error': str(e)}])
    src_ro.close()
    print(f"[INFO] {tbl}: 共 {len(all_codes)} 只标的")

    # 2) baostock 拉取复权因子（fore + back）
    print(f"[INFO] 连接 baostock 拉取复权因子...")
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")

    factor_cache = {}
    total = len(all_codes)
    for i, code in enumerate(all_codes, 1):
        bare = to_bare_code(code)
        try:
            rs = bs.query_adjust_factor(
                code=to_baostock_code(code),
                start_date='2000-01-01',
                end_date='2030-12-31',
            )
            rows = []
            while rs.next():
                r = rs.get_row_data()
                if r[2] and r[2] != '' and r[3] and r[3] != '':
                    rows.append({'dt': r[1], 'fore': float(r[2]), 'back': float(r[3])})
            if rows:
                fdf = pd.DataFrame(rows)
                fdf['dt'] = pd.to_datetime(fdf['dt'])
                factor_cache[bare] = fdf
        except Exception as e:
            print(f"[WARN] {code} 因子拉取失败：{e}")
        if i % 200 == 0 or i == total:
            print(f"[INFO] baostock 进度：{i} / {total}")
    bs.logout()
    print(f"[INFO] baostock 加载复权因子：{len(factor_cache)} / {total} 只标的")

    # 3) 建目标表 + 清空
    tgt = duckdb.connect(TARGET_DB)
    tgt.execute(f"""
        CREATE TABLE IF NOT EXISTS {tbl_raw} (
            code VARCHAR, trade_time TIMESTAMPTZ,
            open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
            vol BIGINT, amount DOUBLE
        )
    """)
    tgt.execute(f"""
        CREATE TABLE IF NOT EXISTS {tbl_qfq} (
            code VARCHAR, trade_time TIMESTAMPTZ,
            open_qfq DOUBLE, high_qfq DOUBLE, low_qfq DOUBLE, close_qfq DOUBLE,
            vol BIGINT, amount DOUBLE
        )
    """)
    tgt.execute(f"""
        CREATE TABLE IF NOT EXISTS {tbl_hfq} (
            code VARCHAR, trade_time TIMESTAMPTZ,
            open_hfq DOUBLE, high_hfq DOUBLE, low_hfq DOUBLE, close_hfq DOUBLE,
            vol BIGINT, amount DOUBLE
        )
    """)
    tgt.execute(f"DELETE FROM {tbl_raw}")
    tgt.execute(f"DELETE FROM {tbl_qfq}")
    tgt.execute(f"DELETE FROM {tbl_hfq}")

    # 4) 逐 code 处理
    src = duckdb.connect(SOURCE_DB, read_only=True)
    total_raw = 0
    total_qfq = 0
    total_hfq = 0
    code_ok = 0
    code_fail = 0

    for i, code in enumerate(all_codes, 1):
        try:
            chunk = src.execute(f"""
                SELECT code, trade_time, open, high, low, close, vol, amount
                FROM {tbl}
                WHERE code = ?
                ORDER BY trade_time
            """, [code]).fetchdf()
        except Exception as e:
            print(f"[WARN] {code} 读取失败：{e}")
            code_fail += 1
            continue

        if chunk.empty:
            continue

        for c in ['open', 'high', 'low', 'close', 'amount']:
            if chunk[c].dtype == object:
                chunk[c] = pd.to_numeric(chunk[c], errors='coerce')
        if chunk['vol'].dtype == object:
            chunk['vol'] = pd.to_numeric(chunk['vol'], errors='coerce').astype('Int64')

        bare = to_bare_code(code)
        chunk = merge_factor(chunk, factor_cache.get(bare))

        for c in ['open', 'high', 'low', 'close']:
            chunk[c + '_qfq'] = (chunk[c] * chunk['fore']).round(3)
            chunk[c + '_hfq'] = (chunk[c] * chunk['back']).round(3)

        try:
            tgt.execute(f"""
                INSERT INTO {tbl_raw}
                SELECT code, trade_time, open, high, low, close,
                       vol::BIGINT as vol, amount
                FROM chunk
            """)
            total_raw += len(chunk)
        except Exception as e:
            print(f"[WARN] {code} 未复权写入失败：{e}")

        try:
            tgt.execute(f"""
                INSERT INTO {tbl_qfq}
                SELECT code, trade_time, open_qfq, high_qfq, low_qfq, close_qfq,
                       vol::BIGINT as vol, amount
                FROM chunk
            """)
            total_qfq += len(chunk)
        except Exception as e:
            print(f"[WARN] {code} 前复权写入失败：{e}")

        try:
            tgt.execute(f"""
                INSERT INTO {tbl_hfq}
                SELECT code, trade_time, open_hfq, high_hfq, low_hfq, close_hfq,
                       vol::BIGINT as vol, amount
                FROM chunk
            """)
            total_hfq += len(chunk)
            code_ok += 1
        except Exception as e:
            print(f"[WARN] {code} 后复权写入失败：{e}")
            code_fail += 1

        if i % 200 == 0 or i == len(all_codes):
            print(f"  [PROGRESS] {i}/{len(all_codes)} 只标的, raw={total_raw} / qfq={total_qfq} / hfq={total_hfq} 行")

        del chunk
        if i % 100 == 0:
            gc.collect()

    src.close()
    tgt.close()

    detail = f"{tbl}: raw={total_raw} / qfq={total_qfq} / hfq={total_hfq} ({code_ok} ok / {code_fail} fail)"
    print(f"[DONE] {detail}")

    return pd.DataFrame([{
        'status': 'ok',
        'table': tbl,
        'timestamp': datetime.now().isoformat(),
        'raw_rows': total_raw,
        'qfq_rows': total_qfq,
        'hfq_rows': total_hfq,
        'codes_ok': code_ok,
        'codes_fail': code_fail,
        'detail': detail,
    }])
'''

# ========== 构建工作流 JSON（多节点版） ==========

workflow_json = {
    "nodes": [
        {
            "id": "n1",
            "name": "设置表名列表",
            "type": "set_variable",
            "parameters": {
                "var_name": "tables",
                "var_value": '["dat_day","dat_60mins","dat_30mins","dat_15mins","dat_10mins","dat_5mins","dat_1mins"]',
                "value_type": "json"
            }
        },
        {
            "id": "n2",
            "name": "遍历表",
            "type": "for_each",
            "parameters": {
                "items": "{{tables}}",
                "item_var": "current_table",
                "index_var": "table_index",
                "max_iterations": 10
            }
        },
        {
            "id": "n3",
            "name": "复权计算（未复权+前复权+后复权）",
            "type": "custom_python",
            "parameters": {
                "code": CUSTOM_CODE.strip()
            }
        },
        {
            "id": "n4",
            "name": "等待 0.5 秒",
            "type": "wait",
            "parameters": {
                "seconds": 0.5,
                "mode": "delay"
            }
        }
    ],
    "connections": {
        "n1": ["n2"],
        "n2": ["n3"],
        "n3": ["n4"]
    }
}

# ========== 生成新的示例23 markdown ==========

wf_json_str = json.dumps(workflow_json, ensure_ascii=False, indent=2)

NEW_SECTION = '''---

## 23. 后复权处理工程化 — 全量分钟/日线数据批量复权（多节点版）

**测试节点**: `set_variable` + `for_each` + `custom_python` + `wait`
**说明**: 用 `for_each` 遍历 7 张表，每次迭代由 `custom_python` 自接管 I/O，从 baostock 拉取 fore+back 因子，同时输出未复权/前复权/后复权 3 张表到 `C:/duckdb/quantifydata_adj.duckdb`。每种频率 3 张表，共 21 张。

```json
''' + wf_json_str + '''
```

### 23.1 节点架构

```
set_variable(tables = 7张表名)
  -> for_each(current_table)
       -> custom_python(自接管I/O: 读源表 + baostock拉因子 + 计算复权 + 写3张目标表)
       -> wait(0.5s)
```

| 节点 | 作用 | 为什么这样设计 |
|---|---|---|
| `set_variable` | 设置待处理的表名列表 | JSON 数组，for_each 通过 `{{tables}}` 引用 |
| `for_each` | 遍历 7 张表，每次注入 `current_table` 到 context | 可视化看到每张表的进度 |
| `custom_python` | 自接管全部 I/O，按 code 分批处理 | 框架节点间传完整 DataFrame，33亿行必爆；自接管可控制内存 |
| `wait` | 每次迭代间隔 0.5s | 避免 DuckDB 连接竞争，给系统喘息 |

**为什么不拆成 `db_query -> custom_python -> target_write`？**
框架节点间是全量 DataFrame 传递。`db_query` 无分页，`dat_1mins` 33亿行直接加载到内存必爆。让 `custom_python` 自接管 I/O，按 code 分批（单 code 最多 ~200万行），每次只返回 1 行状态。

### 23.2 复权因子来源

使用 baostock 的 `query_adjust_factor` 接口，**同时获取前复权因子（fore）和后复权因子（back）**：

- `r[2]` = foreAdjustFactor（前复权因子）
- `r[3]` = backAdjustFactor（后复权因子）

每次 for_each 迭代处理一张表时拉取一次因子。7 张表共享相同的 code 集合，baostock 拉取 7 次（后续可优化为缓存到本地表）。

**精度提示**：baostock 复权因子与同花顺/通达信存在一定偏差。如需精准对齐，可修改代码中的因子加载逻辑，改为从本地 Excel/DuckDB 读取。

### 23.3 输出结构

每种频率输出 3 张表到 `quantifydata_adj.duckdb`：

| 表名后缀 | 含义 | 价格列命名 |
|---|---|---|
| `_raw` | 未复权（原值透传） | open, high, low, close |
| `_qfq` | 前复权 | open_qfq, high_qfq, low_qfq, close_qfq |
| `_hfq` | 后复权 | open_hfq, high_hfq, low_hfq, close_hfq |

共 7 频率 x 3 类型 = **21 张目标表**。

### 23.4 输出表结构

以 `dat_day` 为例：

**dat_day_raw（未复权）**：

| 字段 | 类型 | 说明 |
|---|---|---|
| code | VARCHAR | 股票代码（带 `.SZ` / `.SH` 后缀） |
| trade_time | TIMESTAMPTZ | 交易时间（带时区） |
| open / high / low / close | DOUBLE | 未复权 OHLC |
| vol | BIGINT | 成交量（股） |
| amount | DOUBLE | 成交额（元） |

**dat_day_qfq / dat_day_hfq**：

| 字段 | 类型 | 说明 |
|---|---|---|
| code | VARCHAR | 股票代码 |
| trade_time | TIMESTAMPTZ | 交易时间 |
| open_qfq / high_qfq / ... | DOUBLE | 前/后复权 OHLC |
| vol | BIGINT | 成交量 |
| amount | DOUBLE | 成交额 |

### 23.5 关键实现细节

**1. for_each 如何传递当前表名**

`for_each` 把当前项注入 `context['current_table']`，`custom_python` 通过 `context.get('current_table')` 读取。这样每次迭代只处理一张表，内存可控。

**2. baostock 同时返回 fore + back**

`query_adjust_factor` 每行包含前复权因子和后复权因子，无需手动推导。代码直接取 `r[2]=fore`、`r[3]=back`。

**3. 分钟级数据的因子广播**

日频复权因子广播到分钟级：同一天的所有分钟 K 线共享同一个因子。通过 `pandas.merge_asof(direction='backward')` 按日期对齐实现。

**4. VARCHAR 字段自动转换**

`dat_1mins` 所有字段都是 VARCHAR，按 code 分批后用 `pd.to_numeric(errors='coerce')` 转换，避免整表转换的内存峰值。

**5. 内存控制**

- 按 code 分批（单只标的最多 ~200 万行 1min K 线）
- 每 100 只标的调用 `gc.collect()`
- 处理完立即 `del chunk`
- 节点返回 1 行状态 DataFrame，不传递大数据

**6. code 格式归一化**

源数据 `000001.SZ`、baostock 要 `sz.000001`。代码内置 `normalize_code()`、`to_baostock_code()`、`to_bare_code()` 自动转换。

### 23.6 数据量参考

| 表 | 行数 | 字段类型 |
|---|---|---|
| dat_day | 1423 万 | 正常 |
| dat_60mins | 8144 万 | 正常 |
| dat_30mins | 1.3 亿 | 正常 |
| dat_15mins | 2.4 亿 | 正常 |
| dat_10mins | 3.5 亿 | 正常 |
| dat_5mins | 6.7 亿 | 正常 |
| **dat_1mins** | **33 亿** | **全是 VARCHAR** |

### 23.7 验证 SQL

```sql
-- 在 quantifydata_adj.duckdb 中执行

-- 1. 数据量核对（raw 应与源表一致）
SELECT 'dat_day_raw' as tbl, COUNT(*) FROM dat_day_raw
UNION ALL SELECT 'dat_day_qfq', COUNT(*) FROM dat_day_qfq
UNION ALL SELECT 'dat_day_hfq', COUNT(*) FROM dat_day_hfq;

-- 2. 前复权关键性质：最新日期 前复权价 约等于 未复权价
SELECT trade_time, close, close_qfq, close_hfq
FROM dat_day_qfq
WHERE code = '000001.SZ'
ORDER BY trade_time DESC LIMIT 5;

-- 3. 后复权准确性（与通达信客户端比对）
SELECT * FROM dat_day_hfq
WHERE code = '000001.SZ'
ORDER BY trade_time DESC LIMIT 5;

-- 4. 跨除权日连续性（后复权价应连续，无异常断崖）
SELECT trade_time, close_hfq,
    close_hfq / LAG(close_hfq) OVER (ORDER BY trade_time) - 1 as daily_ret
FROM dat_day_hfq
WHERE code = '000001.SZ'
ORDER BY trade_time;
-- daily_ret 应在 +/-11% 以内（涨跌停限制）
```

### 23.8 风险与应对

| 风险 | 应对 |
|---|---|
| dat_1mins 全是 VARCHAR，转换慢 | 按 code 分批转换，目标表用 DOUBLE |
| baostock 每张表拉一次因子，共 7 次 | 可改为首次拉取后缓存到目标库的 adj_factor 表 |
| for_each 传 df.copy() 给子图 | 初始 df 为空（set_variable 不产生数据），不影响内存 |
| custom_python 执行时间长 | for_each 可视化进度；Pipeline 后台执行 |
| 内存峰值 | 按 code 分批 + gc.collect() + del chunk |

### 23.9 与示例 24 的对比

| 维度 | 示例 23（本示例） | 示例 24 |
|---|---|---|
| 复权类型 | 未复权 + 前复权 + 后复权（3套） | 仅后复权（1套） |
| 因子来源 | baostock fore + back | baostock back only |
| 目标库 | quantifydata_adj.duckdb | quantifydata_hfq.duckdb |
| 输出表数 | 21 张 | 7 张 |
| 节点架构 | 相同（set_variable + for_each + custom_python + wait） | 相同 |'''

# ========== 替换示例23 ==========

md_text = MD_PATH.read_text(encoding="utf-8")

# 匹配示例23：从 "---\n\n## 23." 到 "\n---\n\n## 节点覆盖清单" 之前
pattern = r"(---\n\n## 23\. .*?)(\n---\n\n## 节点覆盖清单)"
match = re.search(pattern, md_text, re.DOTALL)
if not match:
    print("[ERROR] 未找到示例23的位置")
    exit(1)

old_section = match.group(1)
new_md = md_text.replace(old_section, NEW_SECTION)

MD_PATH.write_text(new_md, encoding="utf-8")
print(f"[OK] 已更新示例23（多节点版）-> {MD_PATH}")
print(f"     代码长度: {len(CUSTOM_CODE)} 字符")
print(f"     节点数: {len(workflow_json['nodes'])}")
