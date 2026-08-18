## 📋 示例8 详解：时间窗口分批 + 去重(check_existing) + 写入

### 🎯 目标

测试增量 ETL 场景：按时间窗口分批，排除已有数据后写入。

---

### 🔗 节点流程图

```
┌─ 时间窗口分批 (time_window)
  ┌─ 去重(检查已有) (dedup)
    ┌─ 写入DuckDB (target_write)
```

---

### 📦 各节点详解

#### 1️⃣ n1: 时间窗口分批

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `time_window` |
| 功能 | 时间窗口处理 |
| 参数 | {"window_size": 7, "window_step": 7, "time_column": "dt", "sort_first": true} |

#### 2️⃣ n2: 去重(检查已有)

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `dedup` |
| 功能 | 去重 |
| 参数 | {"mode": "check_existing", "columns": "code,dt", "target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/etl_output.db\"}", "target_table": "stock_minute_kline", "keep_existing_rows": "0"} |

#### 3️⃣ n3: 写入DuckDB

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/etl_output.db\"}", "target_table": "stock_minute_kline", "batch_size": 5000, "on_duplicate": "ignore", "columns": ""} |

---

### 💡 使用场景

本示例适用于需要**测试增量 ETL 场景：按时间窗口分批，排除已有数据后写入。**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
