# 示例 24：多节点后复权工作流（基础控制节点版）

> 本文档演示如何用基础控制节点（set_variable、for_each、wait）搭建多节点后复权工作流。

## 工作流结构

```
set_variable(tables)
  → for_each(current_table)
      → custom_python(处理整张表，按 code 分组)
      → wait(0.1s)
```

## 工作流 JSON

```json
{
  "name": "后复权处理（多节点版）",
  "description": "用基础控制节点搭建的后复权工作流",
  "nodes": [
    {
      "id": "n1",
      "name": "设置表名列表",
      "type": "set_variable",
      "parameters": {
        "var_name": "tables",
        "var_value": "[\"dat_day\", \"dat_60mins\"]",
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
      "name": "处理当前表",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df, context):\n    import duckdb\n    import pandas as pd\n    import baostock as bs\n    from datetime import datetime\n    \n    # 从 context 读取当前表名\n    current_table = context.get('current_table')\n    print(f'[PROCESS] 处理表: {current_table}')\n    \n    # 连接源库\n    src = duckdb.connect('C:/duckdb/quantifydata.duckdb', read_only=True)\n    \n    # 读取当前表的所有 code\n    codes = [r[0] for r in src.execute(f'SELECT DISTINCT code FROM {current_table}').fetchall()]\n    print(f'[INFO] 共 {len(codes)} 只标的')\n    \n    # 加载复权因子（简化版：用 baostock）\n    bs.login()\n    factor_cache = {}\n    for code in codes[:5]:  # 只处理前 5 只（演示用）\n        rs = bs.query_adjust_factor(code=f'sz.{code}' if code.endswith('.SZ') else f'sh.{code}', start_date='2000-01-01', end_date='2030-12-31')\n        rows = []\n        while rs.next():\n            r = rs.get_row_data()\n            if r[3]:\n                rows.append({'dt': r[1], 'back_factor': float(r[3])})\n        if rows:\n            factor_cache[code] = pd.DataFrame(rows)\n            factor_cache[code]['dt'] = pd.to_datetime(factor_cache[code]['dt'])\n    bs.logout()\n    \n    # 逐 code 处理\n    tgt = duckdb.connect('C:/duckdb/quantifydata_hfq.duckdb')\n    tgt_table = current_table + '_hfq'\n    tgt.execute(f'CREATE TABLE IF NOT EXISTS {tgt_table} (code VARCHAR, trade_time TIMESTAMPTZ, open_hfq DOUBLE, high_hfq DOUBLE, low_hfq DOUBLE, close_hfq DOUBLE, vol BIGINT, amount DOUBLE)')\n    tgt.execute(f'DELETE FROM {tgt_table}')\n    \n    for code in codes[:5]:\n        chunk = src.execute(f'SELECT * FROM {current_table} WHERE code = ? ORDER BY trade_time', [code]).fetchdf()\n        if chunk.empty:\n            continue\n        \n        # 合并因子\n        if code in factor_cache:\n            factor_df = factor_cache[code]\n            chunk_dt_ns = pd.to_datetime(chunk['trade_time'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None).astype('datetime64[ns]')\n            chunk_days = chunk_dt_ns.dt.floor('D').astype('int64') // (24 * 3600 * 10**9)\n            factor_dt_ns = pd.to_datetime(factor_df['dt']).dt.tz_localize(None).astype('datetime64[ns]')\n            factor_days = factor_dt_ns.dt.floor('D').astype('int64') // (24 * 3600 * 10**9)\n            factor_df = factor_df.copy()\n            factor_df['day_key'] = factor_days\n            tmp = pd.DataFrame({'day_key': chunk_days}).reset_index(drop=False).rename(columns={'index': 'orig_idx'})\n            merged = pd.merge_asof(tmp.sort_values('day_key'), factor_df[['day_key', 'back_factor']].sort_values('day_key'), on='day_key', direction='backward')\n            merged['back_factor'] = merged['back_factor'].ffill().bfill().fillna(1.0)\n            chunk['back_factor'] = merged.sort_values('orig_idx')['back_factor'].values\n        else:\n            chunk['back_factor'] = 1.0\n        \n        # 计算后复权价\n        for c in ['open', 'high', 'low', 'close']:\n            chunk[c + '_hfq'] = (chunk[c] * chunk['back_factor']).round(3)\n        \n        # 写入目标表\n        tgt.execute(f'INSERT INTO {tgt_table} SELECT code, trade_time, open_hfq, high_hfq, low_hfq, close_hfq, vol::BIGINT, amount FROM chunk')\n    \n    src.close()\n    tgt.close()\n    \n    return pd.DataFrame([{'status': 'ok', 'table': current_table, 'codes_processed': len(codes[:5])}])"
      }
    },
    {
      "id": "n4",
      "name": "等待 0.1 秒",
      "type": "wait",
      "parameters": {
        "seconds": 0.1,
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
```

## 使用方法

1. 在前端工作流编辑器中，点击"📥 导入示例"
2. 搜索"后复权处理（多节点版）"或"示例 24"
3. 导入后，点击"▶ 执行"运行工作流
4. 查看输出结果

## 与示例 23 的对比

| 维度 | 示例 23（单节点） | 示例 24（多节点） |
|---|---|---|
| 节点数 | 1 个 custom_python | 4 个（set_variable + for_each + custom_python + wait） |
| 可视化 | 无 | 清晰的数据流 |
| 复用性 | 低（所有逻辑在一个节点） | 高（每个节点职责单一） |
| 调试 | 困难 | 容易（可单独测试每个节点） |
| 性能 | 相同 | 相同 |

## 扩展建议

- 增加第二层 `for_each` 遍历 code，实现更细粒度的控制
- 用 `try_catch` 节点（P1）包裹 `custom_python`，实现错误重试
- 用 `loop` 节点（P1）实现条件循环（如：处理到新数据为止）
