## 📋 示例11 详解：TDX 本地日 K 复权（前复权 / 后复权）

### 🎯 目标

通达信本地 `.day` 文件读出的是原始价。本示例演示如何基于用户自维护的「复权因子表」，在同一支流水里产出前复权 + 后复权两套价格，并写入 DuckDB 的两张表。

---

### 🔗 节点流程图

```
┌─ 拉取TDX日K (source_fetch)
  ┌─ 复权计算 (custom_python)
    ┌─ 写入前复权表 (target_write)
┌─ 写入后复权表 (target_write)
```

---

### 📦 各节点详解

#### 1️⃣ n1: 拉取TDX日K

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `source_fetch` |
| 功能 | 从数据源拉取原始数据 |
| 参数 | {"source_type": "tdx", "source_config": "{\"data_dir\": \"D:/new_tdx64/vipdoc\"}", "codes": "000001,600000", "interval": "D", "time_mode": "lookback", "lookback_days": 3650, "parallel": false, "sessio |

#### 2️⃣ n2: 复权计算

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `custom_python` |
| 功能 | 自定义 Python 脚本 |
| 参数 | {"code": "def process(df):\n    import pandas as pd, os\n    # 0) 防御：上游 source_fetch 未产出标准 K 线（预览模式 / 本地无 TDX 数据）→ 造一份 sample\n    if df.empty or 'dt' not in df.columns or 'code' not in df.columns:\n  |

#### 3️⃣ n3: 写入后复权表

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}", "target_table": "kline_hfq", "batch_size": 5000, "on_duplicate": "replace", "columns": "code,dt,open_hfq,high_ |

#### 4️⃣ n4: 写入前复权表

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n4` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}", "target_table": "kline_qfq", "batch_size": 5000, "on_duplicate": "replace", "columns": "code,dt,open_qfq,high_ |

---

### 💡 使用场景

本示例适用于需要**通达信本地 `.day` 文件读出的是原始价。本示例演示如何基于用户自维护的「复权因子表」，在同一支**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
