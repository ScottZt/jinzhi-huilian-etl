## 📋 示例1 详解：数据源拉取 → 写入 DuckDB

### 🎯 目标

从 tdx 本地数据拉取股票分钟线，写入 DuckDB。需要先确保本地有 TDX 数据。

---

### 🔗 节点流程图

```
┌─ 拉取1分钟K线 (source_fetch)
  ┌─ 写入DuckDB (target_write)
```

---

### 📦 各节点详解

#### 1️⃣ n1: 拉取1分钟K线

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `source_fetch` |
| 功能 | 从数据源拉取原始数据 |
| 参数 | {"source_type": "tdx", "source_config": "{\"data_dir\": \"D:/new_tdx64/vipdoc\"}", "codes": "000001", "interval": "1min", "time_mode": "lookback", "lookback_days": 3, "parallel": false, "session_only" |

#### 2️⃣ n2: 写入DuckDB

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/demo.db\"}", "target_table": "stock_minute_kline", "batch_size": 5000, "on_duplicate": "ignore", "columns": ""} |

---

### 💡 使用场景

本示例适用于需要**从 tdx 本地数据拉取股票分钟线，写入 DuckDB。需要先确保本地有 TDX 数据。**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
