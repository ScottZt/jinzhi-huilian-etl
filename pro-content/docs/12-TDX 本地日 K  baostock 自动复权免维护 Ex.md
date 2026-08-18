## 📋 示例12 详解：TDX 本地日 K + baostock 自动复权（免维护 Excel）

### 🎯 目标

如果不想自维护复权因子 Excel，可用免费开源库 [baostock](http://baostock.com)（BSD 协议，无需注册/token）在线查询复权因子。本示例与示例 11 等价，区别是因子来源从 Excel 换成 baostock API。

---

### 🔗 节点流程图

```
┌─ 拉取TDX日K (source_fetch)
  ┌─ baostock 复权 (custom_python)
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

#### 2️⃣ n2: baostock 复权

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `custom_python` |
| 功能 | 自定义 Python 脚本 |
| 参数 | {"code": "def process(df):\n    import pandas as pd, numpy as np\n    # 0) 防御：上游 source_fetch 未产出标准 K 线（预览模式 / 本地无 TDX 数据）→ 造一份 sample\n    if df.empty or 'dt' not in df.columns or 'code' not in df.co |

#### 3️⃣ n3: 写入前复权表

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}", "target_table": "kline_qfq", "batch_size": 5000, "on_duplicate": "replace", "columns": "code,dt,open_qfq,high_ |

#### 4️⃣ n4: 写入后复权表

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n4` |
| 节点类型 | `target_write` |
| 功能 | 将处理结果写入目标库 |
| 参数 | {"target_type": "duckdb", "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}", "target_table": "kline_hfq", "batch_size": 5000, "on_duplicate": "replace", "columns": "code,dt,open_hfq,high_ |

---

### 💡 使用场景

本示例适用于需要**如果不想自维护复权因子 Excel，可用免费开源库 [baostock](http://baosto**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
