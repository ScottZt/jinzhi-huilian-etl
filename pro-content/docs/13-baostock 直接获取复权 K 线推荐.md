## 📋 示例13 详解：baostock 直接获取复权 K 线（推荐）

### 🎯 目标

直接使用 baostock 的 `query_history_k_data_plus` 接口获取已复权的 K 线数据，无需手动计算。

---

### 🔗 节点流程图

```
┌─ baostock 获取K线数据 (custom_python)
  ┌─ 过滤不复权数据 (filter)
    ┌─ 写入不复权表 (target_write)
  ┌─ 过滤前复权数据 (filter)
    ┌─ 写入前复权表 (target_write)
  ┌─ 过滤后复权数据 (filter)
    ┌─ 写入后复权表 (target_write)
```

---

### 📦 各节点详解

#### 1️⃣ n1: baostock 获取K线数据

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `custom_python` |
| 功能 | 自定义 Python 脚本 |
| 参数 | {"code": "def process(df):\n    import pandas as pd\n    import baostock as bs\n    \n    # 显式指定市场，避免代码冲突（000001 可以是上证指数也可以是平安银行）\n    CODES = [\n        ('sh', '000001'),  # 上证指数\n        ('sz', '000 |

#### 2️⃣ n2: 过滤不复权数据

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `filter` |
| 功能 | 按条件过滤数据 |
| 参数 | {"mode": "keep", "conditions": [{"column": "adjust_type", "operator": "==", "value": "raw"}]} |

#### 3️⃣ n3: 写入不复权表

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}", "target_table": "kline_raw", "batch_size": 5000, "on_duplicate": "replace", "columns": "market,code,dt,open,hi |

#### 4️⃣ n4: 过滤前复权数据

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n4` |
| 节点类型 | `filter` |
| 功能 | 按条件过滤数据 |
| 参数 | {"mode": "keep", "conditions": [{"column": "adjust_type", "operator": "==", "value": "qfq"}]} |

#### 5️⃣ n5: 写入前复权表

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n5` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}", "target_table": "kline_qfq", "batch_size": 5000, "on_duplicate": "replace", "columns": "market,code,dt,open,hi |

#### 6️⃣ n6: 过滤后复权数据

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n6` |
| 节点类型 | `filter` |
| 功能 | 按条件过滤数据 |
| 参数 | {"mode": "keep", "conditions": [{"column": "adjust_type", "operator": "==", "value": "hfq"}]} |

#### 7️⃣ n7: 写入后复权表

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n7` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}", "target_table": "kline_hfq", "batch_size": 5000, "on_duplicate": "replace", "columns": "market,code,dt,open,hi |

---

### 💡 使用场景

本示例适用于需要**直接使用 baostock 的 `query_history_k_data_plus` 接口获取已复**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
