## 📋 示例3 详解：Yahoo Finance 拉取 → MA → RSI → BOLL → 过滤 → 写入

### 🎯 目标

测试 yfinance 数据源 + 全部技术指标节点组合。

---

### 🔗 节点流程图

```
┌─ 拉取Yahoo数据 (source_fetch)
  ┌─ 移动平均MA (ma)
    ┌─ RSI指标 (rsi)
      ┌─ 布林带 (boll)
        ┌─ 过滤非空RSI (filter)
          ┌─ 写入DuckDB (target_write)
```

---

### 📦 各节点详解

#### 1️⃣ n1: 拉取Yahoo数据

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `source_fetch` |
| 功能 | 从数据源拉取原始数据 |
| 参数 | {"source_type": "yfinance", "source_config": "{}", "codes": "AAPL", "interval": "D", "time_mode": "lookback", "lookback_days": 365, "parallel": false, "session_only": false} |

#### 2️⃣ n2: 移动平均MA

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `ma` |
| 功能 | 计算移动平均线（MA/EMA） |
| 参数 | {"windows": "5,10,20,60", "source_column": "close", "use_ema": false} |

#### 3️⃣ n3: RSI指标

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `rsi` |
| 功能 | 计算 RSI 指标 |
| 参数 | {"window": 14, "source_column": "close"} |

#### 4️⃣ n4: 布林带

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n4` |
| 节点类型 | `boll` |
| 功能 | 计算布林带（BOLL） |
| 参数 | {"window": 20, "std_mult": 2, "source_column": "close"} |

#### 5️⃣ n5: 过滤非空RSI

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n5` |
| 节点类型 | `filter` |
| 功能 | 按条件过滤数据 |
| 参数 | {"mode": "keep", "conditions": [{"column": "rsi", "operator": "is_not_null", "value": ""}, {"column": "boll_mid", "operator": "is_not_null", "value": ""}]} |

#### 6️⃣ n6: 写入DuckDB

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n6` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/stock.db\"}", "target_table": "aapl_daily_indicators", "batch_size": 5000, "on_duplicate": "ignore", "columns": ""} |

---

### 💡 使用场景

本示例适用于需要**测试 yfinance 数据源 + 全部技术指标节点组合。**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
