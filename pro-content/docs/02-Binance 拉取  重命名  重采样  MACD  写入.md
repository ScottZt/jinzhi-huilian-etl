## 📋 示例2 详解：Binance 拉取 → 重命名 → 重采样 → MACD → 写入

### 🎯 目标

测试加密货币数据源拉取，完整数据处理链路。

---

### 🔗 节点流程图

```
┌─ 拉取Binance数据 (source_fetch)
  ┌─ 列重命名 (column_rename)
    ┌─ 重采样5分钟 (resample)
      ┌─ 计算MACD (macd)
        ┌─ 写入DuckDB (target_write)
```

---

### 📦 各节点详解

#### 1️⃣ n1: 拉取Binance数据

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `source_fetch` |
| 功能 | 从数据源拉取原始数据 |
| 参数 | {"source_type": "binance", "source_config": "{}", "codes": "BTCUSDT", "interval": "1min", "time_mode": "lookback", "lookback_days": 1, "parallel": false, "session_only": false} |

#### 2️⃣ n2: 列重命名

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `column_rename` |
| 功能 | 列重命名 |
| 参数 | {"renames": "datetime=dt,vol=volume"} |

#### 3️⃣ n3: 重采样5分钟

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `resample` |
| 功能 | 重采样（如 1 分钟→30 分钟） |
| 参数 | {"rule": "5min", "time_column": "dt", "group_column": ""} |

#### 4️⃣ n4: 计算MACD

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n4` |
| 节点类型 | `macd` |
| 功能 | 计算 MACD 指标 |
| 参数 | {"fast": 12, "slow": 26, "signal": 9, "source_column": "close"} |

#### 5️⃣ n5: 写入DuckDB

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n5` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/crypto.db\"}", "target_table": "btc_5min_macd", "batch_size": 5000, "on_duplicate": "ignore", "columns": ""} |

---

### 💡 使用场景

本示例适用于需要**测试加密货币数据源拉取，完整数据处理链路。**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
