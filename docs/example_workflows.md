# ETL 工作流示例集合

用于测试各个节点是否正常工作。每个示例包含：
- **workflow_json**: 可直接导入工作流编辑器
- **sample_data**: 用于测试的初始样本数据（Python 格式）
- **预期输出**: 帮助判断节点运行是否正确

---

## 1. 数据源拉取 → 写入 DuckDB

**测试节点**: `source_fetch` → `target_write`
**说明**: 从 tdx 本地数据拉取股票分钟线，写入 DuckDB。需要先确保本地有 TDX 数据。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "拉取1分钟K线",
      "type": "source_fetch",
      "parameters": {
        "source_type": "tdx",
        "source_config": "{\"data_dir\": \"D:/new_tdx64/vipdoc\"}",
        "codes": "000001",
        "interval": "1min",
        "time_mode": "lookback",
        "lookback_days": 3,
        "parallel": false,
        "session_only": true
      }
    },
    {
      "id": "n2",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/demo.db\"}",
        "target_table": "stock_minute_kline",
        "batch_size": 5000,
        "on_duplicate": "ignore",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"]}
}
```

**样本数据** (如果不连真实数据源，可用以下数据作为初始输入跳过 source_fetch 测试 target_write):

```python
import pandas as pd
from datetime import datetime, timedelta
base = datetime(2026, 1, 5, 9, 30)
sample_data = pd.DataFrame([
    {"code": "000001", "dt": base + timedelta(minutes=i), "open": 10.0+i*0.01, "high": 10.1+i*0.01,
     "low": 9.9+i*0.01, "close": 10.05+i*0.01, "vol": 1000+i*5, "amount": (1000+i*5)*10.05}
    for i in range(30)
])
```

---

## 2. Binance 拉取 → 重命名 → 重采样 → MACD → 写入

**测试节点**: `source_fetch(binance)` → `column_rename` → `resample` → `macd` → `target_write`
**说明**: 测试加密货币数据源拉取，完整数据处理链路。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "拉取Binance数据",
      "type": "source_fetch",
      "parameters": {
        "source_type": "binance",
        "source_config": "{}",
        "codes": "BTCUSDT",
        "interval": "1min",
        "time_mode": "lookback",
        "lookback_days": 1,
        "parallel": false,
        "session_only": false
      }
    },
    {
      "id": "n2",
      "name": "列重命名",
      "type": "column_rename",
      "parameters": {
        "renames": "datetime=dt,vol=volume"
      }
    },
    {
      "id": "n3",
      "name": "重采样5分钟",
      "type": "resample",
      "parameters": {
        "rule": "5min",
        "time_column": "dt",
        "group_column": ""
      }
    },
    {
      "id": "n4",
      "name": "计算MACD",
      "type": "macd",
      "parameters": {
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "source_column": "close"
      }
    },
    {
      "id": "n5",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/crypto.db\"}",
        "target_table": "btc_5min_macd",
        "batch_size": 5000,
        "on_duplicate": "ignore",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"], "n4": ["n5"]}
}
```

---

## 3. Yahoo Finance 拉取 → MA → RSI → BOLL → 过滤 → 写入

**测试节点**: `source_fetch(yfinance)` → `ma` → `rsi` → `boll` → `filter` → `target_write`
**说明**: 测试 yfinance 数据源 + 全部技术指标节点组合。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "拉取Yahoo数据",
      "type": "source_fetch",
      "parameters": {
        "source_type": "yfinance",
        "source_config": "{}",
        "codes": "AAPL",
        "interval": "D",
        "time_mode": "lookback",
        "lookback_days": 365,
        "parallel": false,
        "session_only": false
      }
    },
    {
      "id": "n2",
      "name": "移动平均MA",
      "type": "ma",
      "parameters": {
        "windows": "5,10,20,60",
        "source_column": "close",
        "use_ema": false
      }
    },
    {
      "id": "n3",
      "name": "RSI指标",
      "type": "rsi",
      "parameters": {
        "window": 14,
        "source_column": "close"
      }
    },
    {
      "id": "n4",
      "name": "布林带",
      "type": "boll",
      "parameters": {
        "window": 20,
        "std_mult": 2,
        "source_column": "close"
      }
    },
    {
      "id": "n5",
      "name": "过滤非空RSI",
      "type": "filter",
      "parameters": {
        "mode": "keep",
        "conditions": [
          {"column": "rsi", "operator": "is_not_null", "value": ""},
          {"column": "boll_mid", "operator": "is_not_null", "value": ""}
        ]
      }
    },
    {
      "id": "n6",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/stock.db\"}",
        "target_table": "aapl_daily_indicators",
        "batch_size": 5000,
        "on_duplicate": "ignore",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"], "n4": ["n5"], "n5": ["n6"]}
}
```

---

## 4. 表达式计算 → 条件分支 → 自定义 Python

**测试节点**: `expression` → `condition` → `custom_python`
**说明**: 测试流程控制和高级自定义脚本能力。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "计算涨跌幅",
      "type": "expression",
      "parameters": {
        "target_column": "pct_change",
        "expression": "(df['close'] - df['open']) / df['open'] * 100"
      }
    },
    {
      "id": "n2",
      "name": "筛选上涨",
      "type": "condition",
      "parameters": {
        "condition": "df['pct_change'] > 0",
        "branch": "true"
      }
    },
    {
      "id": "n3",
      "name": "自定义信号",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    df['signal'] = 0\n    df.loc[df['pct_change'] > 2, 'signal'] = 1\n    df.loc[df['pct_change'] < -2, 'signal'] = -1\n    return df"
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"]}
}
```

**样本数据**:

```python
sample_data = pd.DataFrame([
    {"code": "000001", "dt": "2026-01-05 09:30", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.3},
    {"code": "000001", "dt": "2026-01-05 09:31", "open": 10.3, "high": 10.4, "low": 10.1, "close": 10.15},
    {"code": "000001", "dt": "2026-01-05 09:32", "open": 10.15, "high": 10.6, "low": 10.1, "close": 10.55},
    {"code": "000001", "dt": "2026-01-05 09:33", "open": 10.55, "high": 10.7, "low": 10.3, "close": 10.35},
    {"code": "000001", "dt": "2026-01-05 09:34", "open": 10.35, "high": 10.4, "low": 9.9, "close": 9.95},
])
```

**预期输出**: 应包含 `pct_change`、`signal` 列，signal 为 1 表示涨幅 >2%，-1 表示跌幅 <-2%，0 为正常。

---

## 5. 数据过滤 + 排序 + 分组聚合 + 去重

**测试节点**: `filter` → `sort` → `group_by` → `dedup`
**说明**: 测试数据处理链路：过滤 → 排序 → 聚合 → 去重。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "过滤空成交量",
      "type": "filter",
      "parameters": {
        "mode": "keep",
        "conditions": [
          {"column": "vol", "operator": "is_not_null", "value": ""},
          {"column": "vol", "operator": ">", "value": 0}
        ]
      }
    },
    {
      "id": "n2",
      "name": "按股票和时间排序",
      "type": "sort",
      "parameters": {
        "by": "code,dt",
        "ascending": true
      }
    },
    {
      "id": "n3",
      "name": "分组聚合",
      "type": "group_by",
      "parameters": {
        "group_by": "code",
        "aggregations": "open=first,close=max,low=min,vol=sum"
      }
    },
    {
      "id": "n4",
      "name": "按code去重",
      "type": "dedup",
      "parameters": {
        "mode": "keep_last",
        "columns": "code",
        "target_type": "",
        "target_config": "{}",
        "target_table": "",
        "keep_existing_rows": "0"
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"]}
}
```

**样本数据**:

```python
sample_data = pd.DataFrame([
    {"code": "000001", "dt": "2026-01-05 09:30", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "vol": 1000},
    {"code": "000001", "dt": "2026-01-05 09:31", "open": 10.1, "high": 10.3, "low": 10.0, "close": 10.2, "vol": 800},
    {"code": "000001", "dt": "2026-01-05 09:32", "open": 10.2, "high": 10.5, "low": 10.1, "close": 10.4, "vol": 0},  # vol=0 应被过滤
    {"code": "600000", "dt": "2026-01-05 09:30", "open": 8.0, "high": 8.3, "low": 7.9, "close": 8.1, "vol": 2000},
    {"code": "600000", "dt": "2026-01-05 09:31", "open": 8.1, "high": 8.2, "low": 8.0, "close": 8.15, "vol": 1500},
    {"code": "600000", "dt": "2026-01-05 09:31", "open": 8.1, "high": 8.2, "low": 8.0, "close": 8.15, "vol": 1500},  # 重复行
])
```

**预期输出**: 每个 code 一行，包含 first(open), max(close), min(low), sum(vol)，无重复。

---

## 6. EMA 指标 + 布林带 + 表达式交叉信号

**测试节点**: `ma(use_ema)` → `boll` → `expression` → `condition`
**说明**: 测试 EMA + 布林带 + 自定义表达式组合策略信号。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "EMA指标",
      "type": "ma",
      "parameters": {
        "windows": "12,26",
        "source_column": "close",
        "use_ema": true
      }
    },
    {
      "id": "n2",
      "name": "布林带",
      "type": "boll",
      "parameters": {
        "window": 20,
        "std_mult": 2,
        "source_column": "close"
      }
    },
    {
      "id": "n3",
      "name": "交叉信号",
      "type": "expression",
      "parameters": {
        "target_column": "signal",
        "expression": "1 if df['ema_12'] > df['ema_26'] else -1"
      }
    },
    {
      "id": "n4",
      "name": "突破上轨",
      "type": "condition",
      "parameters": {
        "condition": "df['close'] > df['boll_upper']",
        "branch": "true"
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"]}
}
```

**样本数据**:

```python
import pandas as pd
base_price = 100.0
sample_data = pd.DataFrame([
    {"code": "000001", "dt": f"2026-01-{5+i//60:02d} {(9+i%60):02d}:00",
     "open": base_price+i*0.3, "high": base_price+i*0.3+1, "low": base_price+i*0.3-0.5,
     "close": base_price+i*0.3+0.5, "vol": 1000+i*10}
    for i in range(120)
])
```

---

## 7. 多股票代码并行拉取 → 过滤 → 重采样 → 分组汇总 → 写入

**测试节点**: `source_fetch(parallel)` → `filter` → `resample` → `group_by` → `target_write`
**说明**: 测试并行拉取能力 + 完整 ETL 流程。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "并行拉取多股票",
      "type": "source_fetch",
      "parameters": {
        "source_type": "mootdx",
        "source_config": "{}",
        "codes": "000001,600000,000002",
        "interval": "1min",
        "time_mode": "lookback",
        "lookback_days": 5,
        "parallel": true,
        "max_workers": 3,
        "session_only": true
      }
    },
    {
      "id": "n2",
      "name": "过滤空值",
      "type": "filter",
      "parameters": {
        "mode": "keep",
        "conditions": [
          {"column": "close", "operator": "is_not_null", "value": ""},
          {"column": "vol", "operator": "is_not_null", "value": ""}
        ]
      }
    },
    {
      "id": "n3",
      "name": "重采样30分钟",
      "type": "resample",
      "parameters": {
        "rule": "30min",
        "time_column": "dt",
        "group_column": "code"
      }
    },
    {
      "id": "n4",
      "name": "分组汇总",
      "type": "group_by",
      "parameters": {
        "group_by": "code",
        "aggregations": "open=first,high=max,low=min,close=last,vol=sum"
      }
    },
    {
      "id": "n5",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/etl_output.db\"}",
        "target_table": "stock_30min_summary",
        "batch_size": 5000,
        "on_duplicate": "ignore",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"], "n4": ["n5"]}
}
```

---

## 8. 时间窗口分批 + 去重(check_existing) + 写入

**测试节点**: `time_window` → `dedup(check_existing)` → `target_write`
**说明**: 测试增量 ETL 场景：按时间窗口分批，排除已有数据后写入。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "时间窗口分批",
      "type": "time_window",
      "parameters": {
        "window_size": 7,
        "window_step": 7,
        "time_column": "dt",
        "sort_first": true
      }
    },
    {
      "id": "n2",
      "name": "去重(检查已有)",
      "type": "dedup",
      "parameters": {
        "mode": "check_existing",
        "columns": "code,dt",
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/etl_output.db\"}",
        "target_table": "stock_minute_kline",
        "keep_existing_rows": "0"
      }
    },
    {
      "id": "n3",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/etl_output.db\"}",
        "target_table": "stock_minute_kline",
        "batch_size": 5000,
        "on_duplicate": "ignore",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"]}
}
```

---

## 9. 全指标流水线（MA → EMA → MACD → RSI → BOLL → 综合过滤）

**测试节点**: 所有指标节点串联
**说明**: 一条流水线测试全部技术指标，验证数据流通畅性。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "MA均线",
      "type": "ma",
      "parameters": {
        "windows": "5,10,20",
        "source_column": "close",
        "use_ema": false
      }
    },
    {
      "id": "n2",
      "name": "EMA均线",
      "type": "ma",
      "parameters": {
        "windows": "12,26",
        "source_column": "close",
        "use_ema": true
      }
    },
    {
      "id": "n3",
      "name": "MACD",
      "type": "macd",
      "parameters": {
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "source_column": "close"
      }
    },
    {
      "id": "n4",
      "name": "RSI",
      "type": "rsi",
      "parameters": {
        "window": 14,
        "source_column": "close"
      }
    },
    {
      "id": "n5",
      "name": "布林带",
      "type": "boll",
      "parameters": {
        "window": 20,
        "std_mult": 2,
        "source_column": "close"
      }
    },
    {
      "id": "n6",
      "name": "综合过滤",
      "type": "filter",
      "parameters": {
        "mode": "keep",
        "conditions": [
          {"column": "ma_20", "operator": "is_not_null", "value": ""},
          {"column": "macd", "operator": "is_not_null", "value": ""},
          {"column": "rsi", "operator": "is_not_null", "value": ""}
        ]
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"], "n4": ["n5"], "n5": ["n6"]}
}
```

**样本数据**（需要足够多的数据点，至少 60 行，否则部分指标计算结果为 NaN）:

```python
import pandas as pd
import numpy as np
np.random.seed(42)
n = 120
base = pd.Timestamp("2026-01-05 09:30")
prices = 100 + np.cumsum(np.random.randn(n) * 0.1)
sample_data = pd.DataFrame({
    "code": "000001",
    "dt": [base + pd.Timedelta(minutes=i) for i in range(n)],
    "open": prices - 0.05,
    "high": prices + 0.1,
    "low": prices - 0.1,
    "close": prices,
    "vol": np.random.randint(500, 5000, n),
    "amount": prices * np.random.randint(500, 5000, n),
})
```

---

## 10. 自定义 Python 脚本 — 复杂数据处理

**测试节点**: `custom_python`
**说明**: 测试自定义 Python 脚本节点的沙箱执行能力。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "自定义: K线形态识别",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    # 识别十字星: 实体很小, 上下影线较长\n    body = abs(df['close'] - df['open'])\n    upper_shadow = df['high'] - df[['close', 'open']].max(axis=1)\n    lower_shadow = df[['close', 'open']].min(axis=1) - df['low']\n    avg_body = body.rolling(20).mean()\n    df['is_doji'] = (body < avg_body * 0.1) & (upper_shadow > body * 2) & (lower_shadow > body * 2)\n    # 计算ATR\n    df['tr'] = np.maximum(df['high'] - df['low'],\n                          np.maximum(abs(df['high'] - df['close'].shift(1)),\n                                     abs(df['low'] - df['close'].shift(1))))\n    df['atr'] = df['tr'].rolling(14).mean()\n    return df"
      }
    },
    {
      "id": "n2",
      "name": "过滤十字星",
      "type": "condition",
      "parameters": {
        "condition": "df['is_doji'] == True",
        "branch": "true"
      }
    }
  ],
  "connections": {"n1": ["n2"]}
}
```

---

## 快速测试脚本

如果要通过 Python 直接测试节点（不走前端），可运行以下脚本：

```python
import sys, json, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import pandas as pd
from app.core.workflow_engine import get_workflow_engine

# 样本数据
sample = pd.DataFrame([
    {"code": "000001", "dt": f"2026-01-05 {9+i//60:02d}:{i%60:02d}",
     "open": 10.0+i*0.01, "high": 10.2+i*0.01, "low": 9.9+i*0.01,
     "close": 10.05+i*0.01, "vol": 1000+i*5, "amount": 10000+i*50}
    for i in range(120)
])

# 以示例 9（全指标流水线）为例
workflow = {
    "nodes": [
        {"id": "n1", "name": "MA", "type": "ma", "parameters": {"windows": "5,10,20", "source_column": "close", "use_ema": False}},
        {"id": "n2", "name": "EMA", "type": "ma", "parameters": {"windows": "12,26", "source_column": "close", "use_ema": True}},
        {"id": "n3", "name": "MACD", "type": "macd", "parameters": {"fast": 12, "slow": 26, "signal": 9, "source_column": "close"}},
        {"id": "n4", "name": "RSI", "type": "rsi", "parameters": {"window": 14, "source_column": "close"}},
        {"id": "n5", "name": "BOLL", "type": "boll", "parameters": {"window": 20, "std_mult": 2, "source_column": "close"}},
        {"id": "n6", "name": "过滤", "type": "filter", "parameters": {"mode": "keep", "conditions": [{"column": "rsi", "operator": "is_not_null", "value": ""}]}},
    ],
    "connections": {"n1": ["n2"], "n2": ["n3"], "n3": ["n4"], "n4": ["n5"], "n5": ["n6"]}
}

engine = get_workflow_engine()
engine.register_all()

result, timings = engine.execute(workflow, initial_df=sample)

print("=== 执行时间 ===")
for node, t in timings.items():
    print(f"  {node}: {t}s")

print(f"\n=== 输出: {len(result)} 行 x {len(result.columns)} 列 ===")
print(f"列名: {result.columns.tolist()}")
print(result.head(5).to_string())
```

---

## 节点覆盖清单

| 节点类型 | 显示名称 | 覆盖示例 |
|---------|---------|---------|
| `source_fetch` | 数据源拉取 | 1, 2, 3, 7 |
| `target_write` | 写入目标数据库 | 1, 2, 3, 7, 8 |
| `column_rename` | 列重命名 | 2 |
| `expression` | 表达式计算 | 4, 6 |
| `filter` | 数据过滤 | 3, 5, 7, 9 |
| `sort` | 排序 | 5 |
| `group_by` | 分组聚合 | 5, 7 |
| `condition` | 条件分支 | 4, 6, 10 |
| `custom_python` | 自定义 Python 脚本 | 4, 10 |
| `resample` | 周期重采样 | 2, 3, 7 |
| `ma` | 移动平均(MA/EMA) | 3, 6, 9 |
| `macd` | MACD 指标 | 2, 6, 9 |
| `rsi` | RSI 相对强弱 | 3, 6, 9 |
| `boll` | 布林带(BOLL) | 3, 6, 9 |
| `dedup` | 数据去重 | 5, 8 |
| `time_window` | 时间窗口分批 | 8 |
