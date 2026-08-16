# ETL 工作流示例集合

用于测试各个节点是否正常工作。每个示例包含：
- **workflow_json**: 工作流 JSON，可通过 `POST /api/workflows/` 导入（见下方「如何把示例导入到工作流编辑器」）
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

## 11. TDX 本地日 K 复权（前复权 / 后复权）

**测试节点**: `source_fetch(tdx)` → `custom_python(复权)` → `target_write`
**说明**: 通达信本地 `.day` 文件读出的是**未复权**原始价。本示例演示如何基于用户自维护的「复权因子表」，在同一支流水里产出前复权 + 后复权两套价格，并写入 DuckDB 的两张表。

### 11.1 复权原理

通达信本地只存未复权 OHLC。复权必须依赖一个外部「**复权因子**」序列（等价于每日累计除权比例），通常来源于：
- 用户自行从交易所/数据商导出并维护的 CSV/Excel（本项目合规约束：**不内置**任何第三方私有协议，复权因子由用户自备）；
- 或用 `custom_python` 基于除权除息事件手工推算。

设 `factor[i]` 为第 i 日的复权因子（数值越大代表累计稀释越多）：

| 模式 | 公式 | 特点 |
|------|------|------|
| 后复权 | `price_adj = price_raw × factor[i]` | 历史价格被抬升，时间序列连续向上，适合计算长期收益 |
| 前复权 | `price_adj = price_raw × factor[i] / factor[last]` | 最新一日价格不变，历史价格被向下压，适合技术形态观察 |

`factor` 是同一套，只是基准不同，因此 **一次计算同时出两张表**，无需重复拉取。

### 11.2 工作流 JSON

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "拉取TDX日K",
      "type": "source_fetch",
      "parameters": {
        "source_type": "tdx",
        "source_config": "{\"data_dir\": \"D:/new_tdx64/vipdoc\"}",
        "codes": "000001,600000",
        "interval": "D",
        "time_mode": "lookback",
        "lookback_days": 3650,
        "parallel": false,
        "session_only": false
      }
    },
    {
      "id": "n2",
      "name": "复权计算",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd, os\n    # 0) 防御：上游 source_fetch 未产出标准 K 线（预览模式 / 本地无 TDX 数据）→ 造一份 sample\n    if df.empty or 'dt' not in df.columns or 'code' not in df.columns:\n        import numpy as np\n        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=1200)\n        rows = []\n        for c in ['000001', '600000']:\n            p = 10.0 if c == '000001' else 8.0\n            for d in dates:\n                p *= (1 + np.random.normal(0, 0.02))\n                rows.append({'code': c, 'dt': d, 'open': round(p*0.999,3),\n                             'high': round(p*1.01,3), 'low': round(p*0.99,3),\n                             'close': round(p,3), 'vol': int(np.random.randint(500,5000)),\n                             'amount': round(p*np.random.randint(500,5000),2)})\n        df = pd.DataFrame(rows)\n    # 1) 加载用户自维护的复权因子表；若 Excel 未准备，预览时自动回落到 baostock\n    fp = r'D:/data/adj_factor.xlsx'\n    if os.path.exists(fp):\n        adj = pd.read_excel(fp, sheet_name='复权因子', parse_dates=['dt'])\n        df = df.merge(adj[['code', 'dt', 'factor']], on=['code', 'dt'], how='left')\n        df['factor'] = df.groupby('code')['factor'].ffill().bfill()\n    else:\n        import baostock as bs\n        bs.login()\n        def to_bs(c):\n            s = str(c).zfill(6)\n            return ('sh.' + s) if s.startswith(('6','9')) else ('sz.' + s)\n        rows = []\n        code_min = (df['dt'].min() - pd.Timedelta(days=3650)).strftime('%Y-%m-%d')\n        code_max = df['dt'].max().strftime('%Y-%m-%d')\n        for c in df['code'].unique():\n            rs = bs.query_adjust_factor(code=to_bs(c), start_date=code_min, end_date=code_max)\n            while rs.next():\n                r = rs.get_row_data()\n                rows.append({'code': c, 'dt': r[1], 'fore': float(r[2]), 'back': float(r[3])})\n        bs.logout()\n        adj = pd.DataFrame(rows); adj['dt'] = pd.to_datetime(adj['dt'])\n        df = df.sort_values('dt'); adj = adj.sort_values('dt')\n        df = pd.merge_asof(df, adj, on='dt', by='code', direction='backward')\n        first = adj.groupby('code')[['fore','back']].first()\n        df = df.set_index('code')\n        for col in ['fore','back']:\n            df[col] = df[col].fillna(df.index.to_series().map(first[col]))\n        df = df.reset_index()\n        # 复用 factor 列的统一计算路径：fore 即前复权因子；后复权单独走 back\n        df['factor'] = df['fore']\n        df['back'] = df['back']\n    # 2) 计算前复权 / 后复权\n    cols = ['open', 'high', 'low', 'close']\n    if 'back' in df.columns:\n        # baostock 回落分支：fore/back 都齐\n        for c in cols:\n            df[c + '_qfq'] = (df[c] * df['fore']).round(3)\n            df[c + '_hfq'] = (df[c] * df['back']).round(3)\n    else:\n        # Excel 分支：factor 单列，last = 每 code 最后一个 factor\n        def _adj(g):\n            last = g['factor'].iloc[-1]\n            for c in cols:\n                g[c + '_hfq'] = (g[c] * g['factor']).round(3)\n                g[c + '_qfq'] = (g[c] * g['factor'] / last).round(3)\n            return g\n        df = df.groupby('code', group_keys=False).apply(_adj)\n    return df"
      }
    },
    {
      "id": "n3",
      "name": "写入后复权表",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}",
        "target_table": "kline_hfq",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": "code,dt,open_hfq,high_hfq,low_hfq,close_hfq,vol,amount"
      }
    },
    {
      "id": "n4",
      "name": "写入前复权表",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}",
        "target_table": "kline_qfq",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": "code,dt,open_qfq,high_qfq,low_qfq,close_qfq,vol,amount"
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"], "n2": ["n4"]}
}
```

### 11.3 复权因子 Excel (`adj_factor.xlsx`)

工作表名：`复权因子`（对应 `sheet_name='复权因子'`，也可改为 `0` 取第一个 sheet）。

| code | dt | factor |
|------|-----|--------|
| 000001 | 2024-01-02 | 1.0000 |
| 000001 | 2024-06-15 | 1.0200 |
| 000001 | 2025-06-14 | 1.0510 |
| ... | ... | ... |

- 只需在**除权除息日**填写一行，非除权日可留空（代码里用 `groupby+ffill` 自动向下填充）；
- `dt` 列单元格格式用「日期」即可，`pd.read_excel(parse_dates=['dt'])` 会自动解析；
- `factor` 计算口径建议：`factor[t] = factor[t-1] × (1 + 送转比例) / 除权比例`，与主流行情软件保持一致；
- **多股票场景**：同一个 sheet 里按 `code` 列区分即可，`groupby('code')` 会分别处理；
- 该 Excel 由用户自行维护，**本工具不内置**任何获取复权因子的第三方接口（合规约束：不内置私有协议/SDK/密钥）。

### 11.4 验证方式

- **前复权验证**：最新交易日的 `close_qfq` 应等于 TDX 原始 `close`（因为除以了 `factor[last]` 归一化）；
- **后复权验证**：长期持有收益 = `close_hfq[今日] / close_hfq[买入日] - 1`，应与券商复权计算器一致；
- **跨除权日连续性**：以 `000001` 为例，画出 `close_qfq` 时间序列，除权日处不应出现断崖。

---

## 12. TDX 本地日 K + baostock 自动复权（免维护 Excel）

**测试节点**: `source_fetch(tdx)` → `custom_python(baostock 复权)` → `target_write`
**说明**: 如果不想自维护复权因子 Excel，可用免费开源库 [baostock](http://baostock.com)（BSD 协议，无需注册/token）在线查询复权因子。本示例与示例 11 等价，区别是因子来源从 Excel 换成 baostock API。

> 合规说明：baostock 是开源免费接口，本项目不内置其 SDK，由用户在 `custom_python` 中按需 `import`。运行环境需自行 `pip install baostock`。

### 12.1 baostock 复权因子口径（实测）

`bs.query_adjust_factor` 返回字段：`code, dividOperateDate, foreAdjustFactor, backAdjustFactor, adjustFactor`。

| 字段 | 含义 | 最新值 |
|------|------|--------|
| `foreAdjustFactor` | 前复权因子 | **1.0**（基准） |
| `backAdjustFactor` | 后复权因子 | ≈ 十几（随年份累乘） |
| `adjustFactor` | 累计复权因子 | **等于 `backAdjustFactor`** |

公式：

```
前复权价 = 原始价 × foreAdjustFactor
后复权价 = 原始价 × backAdjustFactor
```

**注意事项**：
- 复权因子**仅在除权除息日**有记录，非除权日查不到——需用「≤ 该 K 线日期的最近一个因子」做前向填充（`ffill`）；
- baostock 股票代码格式为 `sh.600000` / `sz.000001`，需在代码里做 `code` → `bs_code` 的映射；
- 接口返回是字符串，需转 `float`。

### 12.2 工作流 JSON

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "拉取TDX日K",
      "type": "source_fetch",
      "parameters": {
        "source_type": "tdx",
        "source_config": "{\"data_dir\": \"D:/new_tdx64/vipdoc\"}",
        "codes": "000001,600000",
        "interval": "D",
        "time_mode": "lookback",
        "lookback_days": 3650,
        "parallel": false,
        "session_only": false
      }
    },
    {
      "id": "n2",
      "name": "baostock 复权",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd, numpy as np\n    # 0) 防御：上游 source_fetch 未产出标准 K 线（预览模式 / 本地无 TDX 数据）→ 造一份 sample\n    if df.empty or 'dt' not in df.columns or 'code' not in df.columns:\n        # 拉长到 1200 个交易日（约 5 年），以覆盖足够多的除权事件\n        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=1200)\n        codes = ['000001', '600000']\n        rows = []\n        for c in codes:\n            p = 10.0 if c == '000001' else 8.0\n            for d in dates:\n                p *= (1 + np.random.normal(0, 0.02))\n                rows.append({'code': c, 'dt': d, 'open': round(p*0.999,3),\n                             'high': round(p*1.01,3), 'low': round(p*0.99,3),\n                             'close': round(p,3), 'vol': int(np.random.randint(500,5000)),\n                             'amount': round(p*np.random.randint(500,5000),2)})\n        df = pd.DataFrame(rows)\n    import baostock as bs\n    bs.login()\n    # 1) 代码映射：6 位纯数字 -> sh./sz. 前缀\n    def to_bs(c):\n        s = str(c).zfill(6)\n        return ('sh.' + s) if s.startswith(('6','9')) else ('sz.' + s)\n    # 2) 按股票批量拉取复权因子（扩大查询窗口到近 10 年，以覆盖上市早期事件）\n    code_min = (df['dt'].min() - pd.Timedelta(days=3650)).strftime('%Y-%m-%d')\n    code_max = df['dt'].max().strftime('%Y-%m-%d')\n    rows = []\n    for c in df['code'].unique():\n        rs = bs.query_adjust_factor(code=to_bs(c),\n                                    start_date=code_min, end_date=code_max)\n        while rs.next():\n            r = rs.get_row_data()\n            rows.append({'code': c, 'dt': r[1],\n                         'fore': float(r[2]), 'back': float(r[3])})\n    bs.logout()\n    if not rows:\n        raise RuntimeError('baostock 未返回任何复权因子，请检查代码格式或网络')\n    adj = pd.DataFrame(rows)\n    adj['dt'] = pd.to_datetime(adj['dt'])\n    # 3) merge_asof 要求 on 列全局有序（不是按 by 分组有序），两边都先按 dt 排序\n    df = df.sort_values('dt')\n    adj = adj.sort_values('dt')\n    df = pd.merge_asof(df, adj, on='dt', by='code', direction='backward')\n    # 4) 防御：df 最早一段（早于该 code 第一个除权日）会 NaN，用该 code 最早因子填充\n    first = adj.groupby('code')[['fore', 'back']].first()\n    df = df.set_index('code')\n    for col in ['fore', 'back']:\n        df[col] = df[col].fillna(df.index.to_series().map(first[col]))\n    df = df.reset_index()\n    # 5) 应用复权公式\n    cols = ['open', 'high', 'low', 'close']\n    for c in cols:\n        df[c + '_qfq'] = (df[c] * df['fore']).round(3)\n        df[c + '_hfq'] = (df[c] * df['back']).round(3)\n    # 6) 保留原始未复权价格，方便验证\n    df = df.rename(columns={'open': 'open_raw', 'high': 'high_raw', 'low': 'low_raw', 'close': 'close_raw'})\n    return df"
      }
    },
    {
      "id": "n3",
      "name": "写入前复权表",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}",
        "target_table": "kline_qfq",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": "code,dt,open_qfq,high_qfq,low_qfq,close_qfq,vol,amount"
      }
    },
    {
      "id": "n4",
      "name": "写入后复权表",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}",
        "target_table": "kline_hfq",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": "code,dt,open_hfq,high_hfq,low_hfq,close_hfq,vol,amount"
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3", "n4"]}
}
```

> 💡 上一步 `custom_python` 同时产出了 `_qfq` 和 `_hfq` 两套列。如果也需要后复权表，在编辑器里**复制 n3 节点**，把 `target_table` 改成 `kline_hfq`，`columns` 改成 `code,dt,open_hfq,high_hfq,low_hfq,close_hfq,vol,amount`，再从 n2 连一条线过去即可（画布会呈现一分二的双路写入结构）。

### 12.3 与示例 11 的对比

| 维度 | 示例 11（Excel） | 示例 12（baostock） |
|------|----------------|-------------------|
| 因子来源 | 用户自维护 `adj_factor.xlsx` | baostock API 自动查询 |
| 离线可用 | ✅ | ❌ 需联网 |
| 数据覆盖 | 仅用户维护的标的 | A 股全市场（含指数/基金） |
| 额外依赖 | `openpyxl`（项目已有） | `pip install baostock` |
| 适用场景 | 内网/保密环境、因子口径自定义 | 个人量化、快速验证 |

### 12.4 验证方式

#### 基础验证：检查字段完整性

```bash
D:\data\duckdb.exe D:\data\stock_adj.duckdb
```

```sql
-- 查看前复权表结构和数据
.schema kline_qfq
SELECT * FROM kline_qfq LIMIT 5;

-- 查看后复权表结构和数据
.schema kline_hfq
SELECT * FROM kline_hfq LIMIT 5;

-- 确认数据量
SELECT code, COUNT(*) as cnt FROM kline_qfq GROUP BY code;
```

预期字段：
- **前复权表**：`code, dt, open_qfq, high_qfq, low_qfq, close_qfq, vol, amount`
- **后复权表**：`code, dt, open_hfq, high_hfq, low_hfq, close_hfq, vol, amount`

#### 准确性验证：与通达信客户端比对

**前复权验证**：
1. 打开通达信客户端，查看 `000001` 或 `600000` 的**前复权**日 K 线
2. 在 DuckDB 中执行：
   ```sql
   SELECT * FROM kline_qfq 
   WHERE code = '000001' 
   ORDER BY dt DESC LIMIT 5;
   ```
3. 比对最近交易日的 `close_qfq` 与通达信显示的收盘价，误差应在 **1e-3（0.001）** 以内

**后复权验证**：
1. 通达信切换到**后复权**模式
2. 在 DuckDB 中执行：
   ```sql
   SELECT * FROM kline_hfq 
   WHERE code = '000001' 
   ORDER BY dt DESC LIMIT 5;
   ```
3. 比对 `close_hfq` 与通达信显示值

**长期收益验证**：
```sql
-- 计算 000001 从最早日期到最新的后复权收益率
SELECT 
    code,
    MIN(dt) as start_date,
    MAX(dt) as end_date,
    (MAX(close_hfq) / MIN(close_hfq) - 1) * 100 as total_return_pct
FROM kline_hfq
WHERE code = '000001'
GROUP BY code;
```

这个收益率应与通达信后复权显示的区间涨幅一致。

**除权日连续性验证**：
```sql
-- 检查前复权价格序列，除权日不应出现断崖
SELECT dt, close_qfq, 
       close_qfq - LAG(close_qfq) OVER (PARTITION BY code ORDER BY dt) as daily_change
FROM kline_qfq
WHERE code = '000001'
ORDER BY dt DESC
LIMIT 30;
```

前复权价格序列应该是连续的（除了正常的日内波动），除权日不应出现大幅跳空。

---

## 13. baostock 直接获取复权 K 线（推荐）

**测试节点**: `custom_python(baostock)` → `filter` → `target_write`
**说明**: 直接使用 baostock 的 `query_history_k_data_plus` 接口获取已复权的 K 线数据，无需手动计算。

> **与示例12的区别**：
> - 示例12：TDX 本地数据 + 手动获取复权因子 + 手动计算
> - 示例13：直接用 baostock API 获取已复权数据，代码更简洁

### 13.1 baostock 复权参数

baostock 的 `query_history_k_data_plus` 接口支持通过 `adjustflag` 参数直接获取复权数据：

| adjustflag | 含义 | 说明 |
|------------|------|------|
| `"3"` | 不复权 | 原始价格数据 |
| `"2"` | 前复权 | 以当前价为基准，向前调整历史价格 |
| `"1"` | 后复权 | 以上市首日价为基准，向后调整当前价格 |

> ⚠️ **重要说明：baostock 后复权与同花顺/通达信的差异**
>
> 经实测，baostock 的后复权价与同花顺/通达信存在 **30% 左右的差异**（以 000001 平安银行为例）：
>
> | 数据源 | 复权因子 | 后复权价（2026-07-20）|
> |--------|---------|---------------------|
> | baostock | 124.91 | 1371.53 |
> | akshare（东财） | 150.73 | 1654.97 |
> | 同花顺 | 163.00 | 1789.73 |
>
> **差异原因**（经深度研究）：
> 1. **分红税假设不同**：同花顺可能用税前分红，baostock 可能用税后分红
> 2. **计算方法不同**：同花顺用递推法，baostock 用累积因子法
> 3. **数据质量问题**：baostock 在 2020-12-31 有 back 因子异常下降（119.96→99.79）
> 4. **历史事件覆盖不同**：早期除权除息事件可能有遗漏
>
> **结论**：baostock 的后复权是"动态后复权"（每个交易日用当时的累积因子），而通达信/同花顺是"静态后复权"（所有历史价用最新因子）。如果需要和行情软件一致的后复权数据，建议改用 akshare（`ak.stock_zh_a_daily(adjust="hfq")`，和同花顺差 8%）或通达信本地数据。
>
> 本示例保留 baostock 方案，因为：免费、无需额外依赖、适合学习测试。

### 13.2 工作流 JSON

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "baostock 获取K线数据",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd\n    import baostock as bs\n    \n    # 显式指定市场，避免代码冲突（000001 可以是上证指数也可以是平安银行）\n    CODES = [\n        ('sh', '000001'),  # 上证指数\n        ('sz', '000001'),  # 平安银行\n        ('sh', '600000'),  # 浦发银行\n    ]\n    START_DATE = '2020-01-01'\n    END_DATE = '2026-12-31'\n    FREQUENCY = 'd'\n    FIELDS = 'date,code,open,high,low,close,volume,amount,turn,pctChg'\n    \n    bs.login()\n    all_data = []\n    \n    for market, code in CODES:\n        bs_code = f'{market}.{code}'\n        \n        for adjust_type, adjust_flag in [('raw', '3'), ('qfq', '2'), ('hfq', '1')]:\n            rs = bs.query_history_k_data_plus(\n                bs_code, FIELDS,\n                start_date=START_DATE, end_date=END_DATE,\n                frequency=FREQUENCY, adjustflag=adjust_flag\n            )\n            while rs.error_code == '0' and rs.next():\n                row = rs.get_row_data()\n                all_data.append({\n                    'market': market,\n                    'code': code,\n                    'date': row[0],\n                    'open': float(row[2]) if row[2] else 0,\n                    'high': float(row[3]) if row[3] else 0,\n                    'low': float(row[4]) if row[4] else 0,\n                    'close': float(row[5]) if row[5] else 0,\n                    'volume': float(row[6]) if row[6] else 0,\n                    'amount': float(row[7]) if row[7] else 0,\n                    'turn': float(row[8]) if row[8] else None,\n                    'pctChg': float(row[9]) if row[9] else None,\n                    'adjust_type': adjust_type\n                })\n    \n    bs.logout()\n    df = pd.DataFrame(all_data)\n    df['date'] = pd.to_datetime(df['date'])\n    df = df.rename(columns={'date': 'dt'})\n    print(f'[baostock] 获取数据: {len(df)} 条')\n    return df"
      }
    },
    {
      "id": "n2",
      "name": "过滤不复权数据",
      "type": "filter",
      "parameters": {
        "mode": "keep",
        "conditions": [{"column": "adjust_type", "operator": "==", "value": "raw"}]
      }
    },
    {
      "id": "n3",
      "name": "写入不复权表",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}",
        "target_table": "kline_raw",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": "market,code,dt,open,high,low,close,volume,amount,turn,pctChg"
      }
    },
    {
      "id": "n4",
      "name": "过滤前复权数据",
      "type": "filter",
      "parameters": {
        "mode": "keep",
        "conditions": [{"column": "adjust_type", "operator": "==", "value": "qfq"}]
      }
    },
    {
      "id": "n5",
      "name": "写入前复权表",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}",
        "target_table": "kline_qfq",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": "market,code,dt,open,high,low,close,volume,amount,turn,pctChg"
      }
    },
    {
      "id": "n6",
      "name": "过滤后复权数据",
      "type": "filter",
      "parameters": {
        "mode": "keep",
        "conditions": [{"column": "adjust_type", "operator": "==", "value": "hfq"}]
      }
    },
    {
      "id": "n7",
      "name": "写入后复权表",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/stock_adj.duckdb\"}",
        "target_table": "kline_hfq",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": "market,code,dt,open,high,low,close,volume,amount,turn,pctChg"
      }
    }
  ],
  "connections": {"n1": ["n2", "n4", "n6"], "n2": ["n3"], "n4": ["n5"], "n6": ["n7"]}
}
```

### 13.3 写入的表

| 表名 | 说明 | 字段 |
|------|------|------|
| `kline_raw` | 不复权数据 | market, code, dt, open, high, low, close, volume, amount, turn, pctChg |
| `kline_qfq` | 前复权数据 | market, code, dt, open, high, low, close, volume, amount, turn, pctChg |
| `kline_hfq` | 后复权数据 | market, code, dt, open, high, low, close, volume, amount, turn, pctChg |

> `market` 字段用于区分交易所：`sh` = 上海，`sz` = 深圳。例如 `000001` 在上海是上证指数，在深圳是平安银行。

### 13.4 与示例12的对比

| 维度 | 示例12（TDX + 手动复权） | 示例13（baostock 直接获取） |
|------|------------------------|--------------------------|
| 数据来源 | 本地 TDX 文件 + baostock 复权因子 | baostock API 直接获取 |
| 联网要求 | 仅需复权因子查询 | 需要全程联网 |
| 代码复杂度 | 需要手动计算复权 | 直接获取，代码简洁 |
| 执行速度 | 本地数据快，复权计算需时间 | 受网络影响 |
| 数据字段 | open/high/low/close + 复权后缀 | 直接包含 turn, pctChg 等 |
| 适用场景 | 离线环境、大量数据 | 快速验证、少量标的 |

### 13.5 验证方式

```sql
-- 比较不复权和前复权的差异（注意：需要指定 market 区分同名代码）
SELECT 
    a.market, a.code, a.dt, 
    a.close as raw_close, 
    b.close as qfq_close,
    c.close as hfq_close,
    ROUND(b.close / a.close, 4) as qfq_factor,
    ROUND(c.close / a.close, 4) as hfq_factor
FROM kline_raw a
JOIN kline_qfq b ON a.market = b.market AND a.code = b.code AND a.dt = b.dt
JOIN kline_hfq c ON a.market = c.market AND a.code = c.code AND a.dt = c.dt
WHERE a.market = 'sz' AND a.code = '000001'  -- 平安银行
ORDER BY a.dt DESC
LIMIT 20;
```

---

## 14. 因子库 — MA 因子生产流水线

**测试节点**: `source_fetch` → `factor_compute` → `factor_write`
**说明**: 从数据源拉取日 K 线，计算 MA5/MA10/MA20 均线因子，写入 DuckDB 因子库。这是因子库的基础生产流程。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "拉取日 K 线",
      "type": "source_fetch",
      "parameters": {
        "source_type": "tdx",
        "source_config": "{\"data_dir\": \"D:/new_tdx64/vipdoc\"}",
        "codes": "000001,600000,000002",
        "interval": "D",
        "time_mode": "lookback",
        "lookback_days": 60,
        "parallel": false,
        "session_only": false
      }
    },
    {
      "id": "n2",
      "name": "计算 MA5 因子",
      "type": "factor_compute",
      "parameters": {
        "factor_id": "ma_5",
        "compute_type": "ma",
        "params_json": "{\"window\": 5}",
        "source_column": "close",
        "code_column": "code",
        "date_column": "dt"
      }
    },
    {
      "id": "n3",
      "name": "写入因子库",
      "type": "factor_write",
      "parameters": {
        "factor_id": "ma_5",
        "db_path": "D:/data/factor_data.duckdb",
        "write_mode": "upsert",
        "code_column": "code",
        "date_column": "dt",
        "value_column": "factor_value",
        "register_meta": true
      }
    }
  ],
  "connections": {
    "n1": ["n2"],
    "n2": ["n3"]
  }
}
```

**sample_data**:
```python
import pandas as pd
from datetime import datetime, timedelta

# 模拟 3 只股票的日 K 线数据（60 天）
codes = ['000001', '600000', '000002']
rows = []
for code in codes:
    base_price = {'000001': 10.0, '600000': 8.0, '000002': 12.0}[code]
    for i in range(60):
        dt = datetime(2024, 10, 1) + timedelta(days=i)
        if dt.weekday() >= 5:
            continue  # 跳过周末
        price = base_price * (1 + 0.02 * (i % 10) / 10)
        rows.append({
            'code': code,
            'dt': dt.strftime('%Y-%m-%d'),
            'open': price * 0.99,
            'high': price * 1.02,
            'low': price * 0.98,
            'close': price,
            'vol': 1000000 + i * 10000,
            'amount': price * 1000000,
        })
df = pd.DataFrame(rows)
```

**预期输出**:
- `factor_compute` 输出: `code, dt, factor_value`（MA5 均线值）
- `factor_write` 输出: 1 行汇总，`_factor_write_status=success`, `_factor_write_count=行数`
- DuckDB 中生成 `factor_ma_5` 表，包含所有股票的 MA5 数据
- `factor_registry` 表中注册 `ma_5` 因子元数据

---

## 15. 因子库 — 多因子批量生产

**测试节点**: `source_fetch` → `factor_compute(MACD)` → `factor_compute(RSI)` → `factor_write`
**说明**: 批量计算 MACD、RSI 等多个因子，通过工作流串联生产。实际使用中建议每个因子单独一条工作流，便于独立调度和维护。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "拉取日 K 线",
      "type": "source_fetch",
      "parameters": {
        "source_type": "tdx",
        "source_config": "{\"data_dir\": \"D:/new_tdx64/vipdoc\"}",
        "codes": "000001",
        "interval": "D",
        "time_mode": "lookback",
        "lookback_days": 120,
        "parallel": false,
        "session_only": false
      }
    },
    {
      "id": "n2",
      "name": "计算 MACD",
      "type": "factor_compute",
      "parameters": {
        "factor_id": "macd",
        "compute_type": "macd",
        "params_json": "{\"fast\": 12, \"slow\": 26, \"signal\": 9}",
        "source_column": "close"
      }
    },
    {
      "id": "n3",
      "name": "写入 MACD 因子",
      "type": "factor_write",
      "parameters": {
        "factor_id": "macd",
        "db_path": "D:/data/factor_data.duckdb",
        "write_mode": "upsert",
        "register_meta": true
      }
    },
    {
      "id": "n4",
      "name": "计算 RSI",
      "type": "factor_compute",
      "parameters": {
        "factor_id": "rsi_14",
        "compute_type": "rsi",
        "params_json": "{\"window\": 14}",
        "source_column": "close"
      }
    },
    {
      "id": "n5",
      "name": "写入 RSI 因子",
      "type": "factor_write",
      "parameters": {
        "factor_id": "rsi_14",
        "db_path": "D:/data/factor_data.duckdb",
        "write_mode": "upsert",
        "register_meta": true
      }
    }
  ],
  "connections": {
    "n1": ["n2", "n4"],
    "n2": ["n3"],
    "n4": ["n5"]
  }
}
```

**sample_data**:
```python
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 模拟单只股票 120 天日 K 线
np.random.seed(42)
rows = []
price = 10.0
for i in range(120):
    dt = datetime(2024, 6, 1) + timedelta(days=i)
    if dt.weekday() >= 5:
        continue
    price *= (1 + np.random.normal(0, 0.02))
    rows.append({
        'code': '000001',
        'dt': dt.strftime('%Y-%m-%d'),
        'open': price * 0.99,
        'high': price * 1.01,
        'low': price * 0.99,
        'close': price,
        'vol': 1000000,
        'amount': price * 1000000,
    })
df = pd.DataFrame(rows)
```

**预期输出**:
- 工作流分叉并行计算 MACD 和 RSI
- DuckDB 中生成 `factor_macd` 和 `factor_rsi_14` 两张表
- `factor_macd` 表: `code, dt, factor_value`（MACD 柱值）
- `factor_rsi_14` 表: `code, dt, factor_value`（RSI 值）

---

## 16. 因子库 — 波动率 + 收益率因子

**测试节点**: `source_fetch` → `factor_compute(return)` → `factor_write`
**说明**: 计算 1 日收益率和 20 日年化波动率因子。这类统计因子在量化策略中广泛使用。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "拉取日 K 线",
      "type": "source_fetch",
      "parameters": {
        "source_type": "tdx",
        "source_config": "{\"data_dir\": \"D:/new_tdx64/vipdoc\"}",
        "codes": "000001",
        "interval": "D",
        "time_mode": "lookback",
        "lookback_days": 100,
        "parallel": false,
        "session_only": false
      }
    },
    {
      "id": "n2",
      "name": "计算 1 日收益率",
      "type": "factor_compute",
      "parameters": {
        "factor_id": "ret_1d",
        "compute_type": "return",
        "params_json": "{\"window\": 1}",
        "source_column": "close"
      }
    },
    {
      "id": "n3",
      "name": "写入收益率因子",
      "type": "factor_write",
      "parameters": {
        "factor_id": "ret_1d",
        "db_path": "D:/data/factor_data.duckdb",
        "write_mode": "upsert",
        "register_meta": true
      }
    },
    {
      "id": "n4",
      "name": "计算 20 日波动率",
      "type": "factor_compute",
      "parameters": {
        "factor_id": "volatility_20",
        "compute_type": "volatility",
        "params_json": "{\"window\": 20}",
        "source_column": "close"
      }
    },
    {
      "id": "n5",
      "name": "写入波动率因子",
      "type": "factor_write",
      "parameters": {
        "factor_id": "volatility_20",
        "db_path": "D:/data/factor_data.duckdb",
        "write_mode": "upsert",
        "register_meta": true
      }
    }
  ],
  "connections": {
    "n1": ["n2", "n4"],
    "n2": ["n3"],
    "n4": ["n5"]
  }
}
```

**sample_data**:
```python
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 模拟日 K 线数据
np.random.seed(123)
rows = []
price = 50.0
for i in range(100):
    dt = datetime(2024, 8, 1) + timedelta(days=i)
    if dt.weekday() >= 5:
        continue
    price *= (1 + np.random.normal(0.0005, 0.025))  # 带漂移的随机游走
    rows.append({
        'code': '000001',
        'dt': dt.strftime('%Y-%m-%d'),
        'open': price * (1 + np.random.normal(0, 0.005)),
        'high': price * (1 + abs(np.random.normal(0, 0.01))),
        'low': price * (1 - abs(np.random.normal(0, 0.01))),
        'close': price,
        'vol': 5000000 + np.random.randint(-1000000, 1000000),
        'amount': price * 5000000,
    })
df = pd.DataFrame(rows)
```

**预期输出**:
- `ret_1d`: 1 日收益率（百分比）
- `volatility_20`: 20 日滚动年化波动率
- DuckDB 中生成对应的因子表

---

## 如何把示例导入到工作流编辑器

### 方式一：UI 按钮（推荐）

打开工作流编辑器，点击工具栏上的 **「📥 导入示例」** 按钮，在弹出列表中勾选需要的示例（支持全选），点击「导入选中」即可批量创建到工作流列表。

### 方式二：API 脚本（批量 / 自动化场景）

也可以通过 `POST /api/workflows/` 写入后端，适合 CI 或批量初始化：

```python
import requests

BASE = "http://localhost:8000"
API_KEY = ""  # 如开启了鉴权，填主面板右上角 API Key

workflow = {
    "name": "示例12: TDX+baostock 复权",
    "description": "本地 TDX 日 K + baostock 自动前/后复权",
    "workflow_json": {
        "nodes": [
            # ... 把示例 11/12 的 nodes 数组粘贴到这里
        ],
        "connections": {"n1": ["n2"], "n2": ["n3"], "n2": ["n4"]}
    }
}

headers = {"Content-Type": "application/json"}
if API_KEY:
    headers["Authorization"] = f"Bearer {API_KEY}"

res = requests.post(f"{BASE}/api/workflows/", json=workflow, headers=headers)
print(res.status_code, res.json())
```

### 维护说明

编辑器中「📥 导入示例」弹框读取的是 `backend/app/static/example_workflows.js`，由 `docs/example_workflows.md` 自动生成。若修改了 md 中的示例 JSON，需要重新生成 JS：

```bash
python scripts/regen_example_workflows_js.py
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

## 17. 官方插件 · 异常值处理（乌龙指 / 脏数据清洗）

**测试节点**: `custom_python` → `outlier_handler` → `target_write`
**说明**: 演示官方精选插件 `outlier_handler`。造一段含异常值的价格数据（第 10 行 5 倍 / 第 30 行 0.1 倍），用 MAD 方法截断到合理范围。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "生成含异常值数据",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd, numpy as np\n    np.random.seed(42)\n    n = 60\n    dates = pd.bdate_range(end='2026-07-22', periods=n)\n    price = 10 * np.cumprod(1 + np.random.normal(0, 0.02, n))\n    price[10] *= 5     # 乌龙指\n    price[30] *= 0.1   # 数据源错误\n    return pd.DataFrame({\n        'code': '000001', 'dt': dates,\n        'open': price * (1 + np.random.normal(0, 0.005, n)),\n        'high': price * (1 + np.abs(np.random.normal(0, 0.01, n))),\n        'low':  price * (1 - np.abs(np.random.normal(0, 0.01, n))),\n        'close': price,\n        'vol': np.random.randint(500, 5000, n).astype(float),\n    })"
      }
    },
    {
      "id": "n2",
      "name": "MAD 异常值截断",
      "type": "outlier_handler",
      "parameters": {
        "columns": "open,high,low,close",
        "method": "mad",
        "threshold": 3.5,
        "action": "clip"
      }
    },
    {
      "id": "n3",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/official_demo.db\"}",
        "target_table": "official_outlier_demo",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"]}
}
```

---

## 18. 官方插件 · 停牌日填充（A 股缺失数据处理）

**测试节点**: `custom_python` → `fill_suspended` → `target_write`
**说明**: 演示官方精选插件 `fill_suspended`。模拟 A 股停牌：故意删除第 5/15/30 个交易日的数据，用前值填充价格列、成交量填 0，并输出 `is_suspended` 停牌标记列。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "生成有停牌缺口数据",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd, numpy as np\n    np.random.seed(42)\n    dates = pd.bdate_range(end='2026-07-22', periods=60)\n    price = 10 * np.cumprod(1 + np.random.normal(0, 0.02, 60))\n    full = pd.DataFrame({\n        'code': '000001', 'dt': dates,\n        'open': price, 'high': price*1.01, 'low': price*0.99, 'close': price,\n        'vol': np.random.randint(500, 5000, 60).astype(float),\n    })\n    return full.drop([5, 15, 30]).reset_index(drop=True)"
      }
    },
    {
      "id": "n2",
      "name": "停牌日填充",
      "type": "fill_suspended",
      "parameters": {
        "code_column": "code",
        "date_column": "dt",
        "price_columns": "open,high,low,close",
        "volume_column": "vol"
      }
    },
    {
      "id": "n3",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/official_demo.db\"}",
        "target_table": "official_fill_suspended_demo",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"]}
}
```

---

## 19. 官方插件 · 未来收益标签（机器学习打标）

**测试节点**: `custom_python` → `label_future_return` → `target_write`
**说明**: 演示官方精选插件 `label_future_return`。基于收盘价生成未来 5 日收益率标签，支持三分类模式（涨=1 / 平=0 / 跌=-1），阈值 0.5%。ML 量化必备。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "生成价格数据",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd, numpy as np\n    np.random.seed(42)\n    n = 60\n    dates = pd.bdate_range(end='2026-07-22', periods=n)\n    price = 10 * np.cumprod(1 + np.random.normal(0, 0.02, n))\n    return pd.DataFrame({\n        'code': '000001', 'dt': dates,\n        'open': price * (1 + np.random.normal(0, 0.005, n)),\n        'high': price * (1 + np.abs(np.random.normal(0, 0.01, n))),\n        'low':  price * (1 - np.abs(np.random.normal(0, 0.01, n))),\n        'close': price,\n        'vol': np.random.randint(500, 5000, n).astype(float),\n    })"
      }
    },
    {
      "id": "n2",
      "name": "三分类标签(涨/平/跌)",
      "type": "label_future_return",
      "parameters": {
        "source_column": "close",
        "horizon": 5,
        "mode": "ternary",
        "threshold": 0.005,
        "label_column": "label"
      }
    },
    {
      "id": "n3",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/official_demo.db\"}",
        "target_table": "official_label_demo",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"]}
}
```

---

## 20. 官方插件 · 量价背离检测

**测试节点**: `custom_python` → `volume_price_divergence` → `target_write`
**说明**: 演示官方精选插件 `volume_price_divergence`。识别四种经典信号：顶背离（价涨量缩=1）/ 恐慌放量（价跌量增=-1）/ 底背离（价跌量缩=2）/ 无背离（0）。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "生成量价数据",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd, numpy as np\n    np.random.seed(42)\n    n = 60\n    dates = pd.bdate_range(end='2026-07-22', periods=n)\n    price = 10 * np.cumprod(1 + np.random.normal(0, 0.02, n))\n    # 注入一段背离：价涨量缩\n    vol = np.random.randint(500, 5000, n).astype(float)\n    vol[40:50] = vol[40:50] * 0.3\n    return pd.DataFrame({\n        'code': '000001', 'dt': dates,\n        'open': price * (1 + np.random.normal(0, 0.005, n)),\n        'high': price * (1 + np.abs(np.random.normal(0, 0.01, n))),\n        'low':  price * (1 - np.abs(np.random.normal(0, 0.01, n))),\n        'close': price,\n        'vol': vol,\n    })"
      }
    },
    {
      "id": "n2",
      "name": "量价背离检测",
      "type": "volume_price_divergence",
      "parameters": {
        "price_column": "close",
        "volume_column": "vol",
        "window": 5,
        "threshold": 0.3
      }
    },
    {
      "id": "n3",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/official_demo.db\"}",
        "target_table": "official_vp_demo",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"]}
}
```

---

## 21. 官方插件 · K 线形态识别（10 种经典形态）

**测试节点**: `custom_python` → `candlestick_pattern` → `target_write`
**说明**: 演示官方精选插件 `candlestick_pattern`。一次识别 10 种经典形态：十字星 / 锤头 / 射击之星 / 阳包阴 / 阴包阳 / 晨星 / 暮星 / 光头光脚 / 纺锤线 / 红三兵，每种形态输出独立信号列。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "生成K线数据",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd, numpy as np\n    np.random.seed(42)\n    n = 60\n    dates = pd.bdate_range(end='2026-07-22', periods=n)\n    price = 10 * np.cumprod(1 + np.random.normal(0, 0.02, n))\n    return pd.DataFrame({\n        'code': '000001', 'dt': dates,\n        'open': price * (1 + np.random.normal(0, 0.005, n)),\n        'high': price * (1 + np.abs(np.random.normal(0, 0.01, n))),\n        'low':  price * (1 - np.abs(np.random.normal(0, 0.01, n))),\n        'close': price,\n        'vol': np.random.randint(500, 5000, n).astype(float),\n    })"
      }
    },
    {
      "id": "n2",
      "name": "识别10种K线形态",
      "type": "candlestick_pattern",
      "parameters": {
        "open_column": "open",
        "high_column": "high",
        "low_column": "low",
        "close_column": "close",
        "body_ratio_threshold": 0.1,
        "patterns": ""
      }
    },
    {
      "id": "n3",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/official_demo.db\"}",
        "target_table": "official_pattern_demo",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"]}
}
```

---

## 22. 官方插件 · 最大回撤与回测三大指标

**测试节点**: `custom_python` → `max_drawdown` → `target_write`
**说明**: 演示官方精选插件 `max_drawdown`。输入净值序列，一次算完最大回撤、年化收益、年化波动、夏普比率、胜率、回撤起止日期等 9 个核心回测指标。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "生成净值序列",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd, numpy as np\n    np.random.seed(42)\n    n = 252  # 一年交易日\n    dates = pd.bdate_range(end='2026-07-22', periods=n)\n    # 模拟一个带回撤的净值曲线\n    ret = np.random.normal(0.0003, 0.015, n)\n    ret[50:70] = -0.02  # 注入一段回撤\n    nv = 1.0 * np.cumprod(1 + ret)\n    return pd.DataFrame({\n        'code': 'strategy_01', 'dt': dates,\n        'open': nv, 'high': nv*1.005, 'low': nv*0.995, 'close': nv,\n        'vol': np.random.randint(1000, 10000, n).astype(float),\n    })"
      }
    },
    {
      "id": "n2",
      "name": "计算回测三大指标",
      "type": "max_drawdown",
      "parameters": {
        "net_value_column": "close",
        "risk_free_rate": 0.02,
        "trading_days_per_year": 252,
        "output_prefix": "backtest"
      }
    },
    {
      "id": "n3",
      "name": "写入DuckDB",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"D:/data/official_demo.db\"}",
        "target_table": "official_backtest_demo",
        "batch_size": 5000,
        "on_duplicate": "replace",
        "columns": ""
      }
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"]}
}
```

---

## 23. 后复权处理工程化 — 嵌套循环 + 分片处理（大数据友好版）

**测试节点**: `set_variable` + `for_each`(嵌套) + `custom_python` + `wait`
**说明**: 采用嵌套循环架构：外层遍历 7 张表，内层遍历每个股票代码。每次只处理一只股票的数据，内存占用极低。从 baostock 拉取 fore+back 因子，输出未复权/前复权/后复权 3 张表。共 21 张目标表。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "设置表名列表",
      "type": "set_variable",
      "parameters": {
        "var_name": "tables",
        "var_value": "[\"dat_day\",\"dat_60mins\",\"dat_30mins\",\"dat_15mins\",\"dat_10mins\",\"dat_5mins\",\"dat_1mins\"]",
        "value_type": "json"
      }
    },
    {
      "id": "n2",
      "name": "遍历表（外层循环）",
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
      "name": "获取股票列表",
      "type": "custom_python",
      "parameters": {
        "code": "import duckdb\nimport pandas as pd\n\ndef process(df, context=None):\n    \"\"\"获取当前表的所有股票代码，存入 context['codes']\"\"\"\n    SOURCE_DB = 'C:/duckdb/quantifydata.duckdb'\n    current_table = context.get('current_table', 'dat_day') if context else 'dat_day'\n    \n    print(f'[INFO] 获取表 {current_table} 的股票列表...')\n    \n    try:\n        conn = duckdb.connect(SOURCE_DB, read_only=True)\n        rows = conn.execute(f'SELECT DISTINCT code FROM {current_table}').fetchall()\n        conn.close()\n        \n        # 归一化股票代码\n        codes = []\n        for r in rows:\n            c = str(r[0]).strip().upper()\n            if '.' in c:\n                codes.append(c)\n            elif len(c) == 6 and c.isdigit():\n                market = 'SH' if c.startswith(('6', '9')) else 'SZ'\n                codes.append(f'{c}.{market}')\n        codes = sorted(set(codes))\n        \n        # 存入 context 供内层 for_each 使用\n        if context:\n            context['codes'] = codes\n        \n        print(f'[INFO] {current_table}: 共 {len(codes)} 只股票')\n        \n        # 返回状态\n        return pd.DataFrame([{\n            'table': current_table,\n            'code_count': len(codes),\n            'status': 'ok'\n        }])\n    except Exception as e:\n        print(f'[ERROR] 获取股票列表失败: {e}')\n        return pd.DataFrame([{'table': current_table, 'error': str(e)}])"
      }
    },
    {
      "id": "n4",
      "name": "遍历股票（内层循环）",
      "type": "for_each",
      "parameters": {
        "items": "{{codes}}",
        "item_var": "current_code",
        "index_var": "code_index",
        "max_iterations": 10000
      }
    },
    {
      "id": "n5",
      "name": "处理单只股票复权",
      "type": "custom_python",
      "parameters": {
        "code": "import duckdb\nimport pandas as pd\nimport baostock as bs\n\ndef normalize_code(c):\n    c = str(c).strip().upper()\n    if '.' in c:\n        return c\n    if len(c) == 6 and c.isdigit():\n        market = 'SH' if c.startswith(('6', '9')) else 'SZ'\n        return f'{c}.{market}'\n    return c\n\ndef to_baostock_code(c):\n    c = str(c).strip().upper()\n    if '.' in c:\n        code, market = c.split('.')\n        return f'{market.lower()}.{code}'\n    c = c.zfill(6)\n    return ('sh.' + c) if c.startswith(('6', '9')) else ('sz.' + c)\n\ndef process(df, context=None):\n    \"\"\"处理单只股票的复权计算\"\"\"\n    SOURCE_DB = 'C:/duckdb/quantifydata.duckdb'\n    TARGET_DB = 'C:/duckdb/quantifydata_adj.duckdb'\n    \n    current_table = context.get('current_table', 'dat_day') if context else 'dat_day'\n    current_code = context.get('current_code', '') if context else ''\n    \n    if not current_code:\n        return pd.DataFrame([{'error': 'current_code is empty'}])\n    \n    code = normalize_code(current_code)\n    bare_code = code.split('.')[0] if '.' in code else code\n    \n    tbl_raw = current_table + '_raw'\n    tbl_qfq = current_table + '_qfq'\n    tbl_hfq = current_table + '_hfq'\n    \n    try:\n        # 1) 读取该股票的数据\n        src = duckdb.connect(SOURCE_DB, read_only=True)\n        chunk = src.execute(f'''\n            SELECT code, trade_time, open, high, low, close, vol, amount\n            FROM {current_table}\n            WHERE UPPER(code) = ?\n            ORDER BY trade_time\n        ''', [code]).fetchdf()\n        src.close()\n        \n        if chunk.empty:\n            return pd.DataFrame([{'code': code, 'status': 'skip', 'reason': 'no data'}])\n        \n        # 2) 转换数据类型\n        for c in ['open', 'high', 'low', 'close', 'amount']:\n            if c in chunk.columns and chunk[c].dtype == object:\n                chunk[c] = pd.to_numeric(chunk[c], errors='coerce')\n        if 'vol' in chunk.columns and chunk['vol'].dtype == object:\n            chunk['vol'] = pd.to_numeric(chunk['vol'], errors='coerce').astype('Int64')\n        \n        # 3) 拉取复权因子\n        lg = bs.login()\n        fore_factor = 1.0\n        back_factor = 1.0\n        \n        rs = bs.query_adjust_factor(\n            code=to_baostock_code(code),\n            start_date='2000-01-01',\n            end_date='2030-12-31'\n        )\n        factors = []\n        while rs.next():\n            r = rs.get_row_data()\n            if r[2] and r[2] != '' and r[3] and r[3] != '':\n                factors.append({'dt': r[1], 'fore': float(r[2]), 'back': float(r[3])})\n        bs.logout()\n        \n        # 4) 合并因子（日频因子广播到分钟级）\n        if factors:\n            factor_df = pd.DataFrame(factors)\n            factor_df['dt'] = pd.to_datetime(factor_df['dt'])\n            \n            chunk_dt = pd.to_datetime(chunk['trade_time'], utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)\n            chunk['day_key'] = chunk_dt.dt.floor('D').astype('int64') // (24 * 3600 * 10**9)\n            factor_df['day_key'] = factor_df['dt'].dt.floor('D').astype('int64') // (24 * 3600 * 10**9)\n            \n            merged = pd.merge_asof(\n                chunk[['day_key']].sort_values('day_key'),\n                factor_df[['day_key', 'fore', 'back']].sort_values('day_key'),\n                on='day_key',\n                direction='backward'\n            )\n            chunk['fore'] = merged['fore'].ffill().bfill().values\n            chunk['back'] = merged['back'].ffill().bfill().values\n        else:\n            chunk['fore'] = 1.0\n            chunk['back'] = 1.0\n        \n        # 5) 计算复权价格\n        chunk['open_qfq'] = (chunk['open'] * chunk['fore']).round(3)\n        chunk['high_qfq'] = (chunk['high'] * chunk['fore']).round(3)\n        chunk['low_qfq'] = (chunk['low'] * chunk['fore']).round(3)\n        chunk['close_qfq'] = (chunk['close'] * chunk['fore']).round(3)\n        chunk['open_hfq'] = (chunk['open'] * chunk['back']).round(3)\n        chunk['high_hfq'] = (chunk['high'] * chunk['back']).round(3)\n        chunk['low_hfq'] = (chunk['low'] * chunk['back']).round(3)\n        chunk['close_hfq'] = (chunk['close'] * chunk['back']).round(3)\n        \n        # 6) 写入目标表\n        tgt = duckdb.connect(TARGET_DB)\n        \n        # 建表（如果不存在）\n        tgt.execute(f'''\n            CREATE TABLE IF NOT EXISTS {tbl_raw} (\n                code VARCHAR, trade_time TIMESTAMPTZ,\n                open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,\n                vol BIGINT, amount DOUBLE\n            )\n        ''')\n        tgt.execute(f'''\n            CREATE TABLE IF NOT EXISTS {tbl_qfq} (\n                code VARCHAR, trade_time TIMESTAMPTZ,\n                open_qfq DOUBLE, high_qfq DOUBLE, low_qfq DOUBLE, close_qfq DOUBLE,\n                vol BIGINT, amount DOUBLE\n            )\n        ''')\n        tgt.execute(f'''\n            CREATE TABLE IF NOT EXISTS {tbl_hfq} (\n                code VARCHAR, trade_time TIMESTAMPTZ,\n                open_hfq DOUBLE, high_hfq DOUBLE, low_hfq DOUBLE, close_hfq DOUBLE,\n                vol BIGINT, amount DOUBLE\n            )\n        ''')\n        \n        # 写入数据\n        chunk_raw = chunk[['code', 'trade_time', 'open', 'high', 'low', 'close', 'vol', 'amount']].copy()\n        chunk_qfq = chunk[['code', 'trade_time', 'open_qfq', 'high_qfq', 'low_qfq', 'close_qfq', 'vol', 'amount']].copy()\n        chunk_hfq = chunk[['code', 'trade_time', 'open_hfq', 'high_hfq', 'low_hfq', 'close_hfq', 'vol', 'amount']].copy()\n        \n        tgt.execute(f'INSERT INTO {tbl_raw} SELECT *, ? as code FROM chunk_raw', [code])\n        tgt.execute(f'INSERT INTO {tbl_qfq} SELECT * FROM chunk_qfq')\n        tgt.execute(f'INSERT INTO {tbl_hfq} SELECT * FROM chunk_hfq')\n        tgt.close()\n        \n        row_count = len(chunk)\n        return pd.DataFrame([{\n            'table': current_table,\n            'code': code,\n            'rows': row_count,\n            'status': 'ok'\n        }])\n        \n    except Exception as e:\n        return pd.DataFrame([{'table': current_table, 'code': code, 'status': 'error', 'error': str(e)}])"
      }
    },
    {
      "id": "n6",
      "name": "股票间隔等待",
      "type": "wait",
      "parameters": {
        "seconds": 0.1,
        "mode": "delay"
      }
    },
    {
      "id": "n7",
      "name": "表间隔等待",
      "type": "wait",
      "parameters": {
        "seconds": 2,
        "mode": "delay"
      }
    }
  ],
  "connections": {
    "n1": ["n2"],
    "n2": ["n3"],
    "n3": ["n4"],
    "n4": ["n5"],
    "n5": ["n6"],
    "n6": ["n7"]
  }
}
```

### 23.1 节点架构（嵌套循环）

```
set_variable(tables = 7张表名)
  └─ for_each(表循环, current_table)
       ├─ custom_python(获取该表所有股票代码 → context['codes'])
       └─ for_each(股票循环, current_code)
            └─ custom_python(单只股票: 拉因子 + 计算复权 + 写入)
            └─ wait(0.1s, 股票间隔)
       └─ wait(2s, 表间隔)
```

| 节点 | 作用 | 设计考虑 |
|---|---|---|
| `set_variable` | 设置待处理的表名列表 | JSON 数组，外层 for_each 通过 `{{tables}}` 引用 |
| `for_each`(外层) | 遍历 7 张表，注入 `current_table` | 可视化看到每张表的进度 |
| `custom_python`(获取列表) | 查询当前表的所有股票代码 | 结果存入 `context['codes']` 供内层使用 |
| `for_each`(内层) | 遍历每只股票，注入 `current_code` | 细粒度进度可视化，单股票失败不影响其他 |
| `custom_python`(处理) | 单只股票的完整复权流程 | 内存占用极低，只处理一只股票的数据 |
| `wait`(股票间隔) | 每次股票处理间隔 0.1s | 避免请求过快 |
| `wait`(表间隔) | 每次表处理间隔 2s | 给系统喘息，可配合 GC |

### 23.2 性能对比

| 维度 | 旧设计（单循环） | 新设计（嵌套循环） |
|---|---|---|
| 循环层级 | 1 层（表） | 2 层（表 + 股票） |
| 单次处理量 | 整张表所有股票 | 单只股票 |
| 内存峰值 | 较高（虽然内部按code分批，但节点执行时间长） | 极低（只加载一只股票的数据） |
| 进度可视化 | 只能看到表级进度 | 可看到表级 + 股票级进度 |
| 错误恢复 | 一张表失败需整表重跑 | 一只股票失败只影响该股票 |
| 执行时间 | 单节点执行数小时 | 单节点执行毫秒级 |

### 23.3 输出结构

每种频率输出 3 张表到 `quantifydata_adj.duckdb`：

| 表名后缀 | 含义 | 价格列命名 |
|---|---|---|
| `_raw` | 未复权（原值透传） | open, high, low, close |
| `_qfq` | 前复权 | open_qfq, high_qfq, low_qfq, close_qfq |
| `_hfq` | 后复权 | open_hfq, high_hfq, low_hfq, close_hfq |

共 7 频率 x 3 类型 = **21 张目标表**。

### 23.4 数据量参考

| 表 | 行数 | 股票数 | 单股最大行数 |
|---|---|---|---|
| dat_day | 1423 万 | ~5000 | ~6000 |
| dat_60mins | 8144 万 | ~5000 | ~35000 |
| dat_30mins | 1.3 亿 | ~5000 | ~70000 |
| dat_15mins | 2.4 亿 | ~5000 | ~140000 |
| dat_10mins | 3.5 亿 | ~5000 | ~210000 |
| dat_5mins | 6.7 亿 | ~5000 | ~420000 |
| **dat_1mins** | **33 亿** | ~5000 | **~200万** |

### 23.5 风险与应对

| 风险 | 应对 |
|---|---|
| dat_1mins 全是 VARCHAR | 节点内 `pd.to_numeric(errors='coerce')` 自动转换 |
| baostock 限流 | 股票间隔 0.1s，表间隔 2s |
| 单股票数据量过大 | 当前设计已按股票拆分，单股最多 ~200万行可接受 |
| 中途失败 | 可从失败位置继续，已处理的股票不受影响 |

---

## 24. 循环遍历（for_each）— 遍历股票代码批量生成模拟数据

**测试节点**: `set_variable` + `for_each` + `custom_python` + `wait`
**说明**: 演示 `for_each` 节点的基本用法：外层用 `set_variable` 设置一组股票代码，`for_each` 逐个注入 `current_code` 到 context，下游 `custom_python` 读取当前代码生成 30 行模拟 K 线。每只股票处理完等待 0.2s 模拟 API 限流。最终合并为 120 行数据（4 只股票 × 30 行）。**零外部依赖，可直接运行**。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "设置股票代码列表",
      "type": "set_variable",
      "parameters": {
        "var_name": "codes",
        "var_value": "[\"000001\",\"600000\",\"000002\",\"300750\"]",
        "value_type": "json"
      }
    },
    {
      "id": "n2",
      "name": "遍历股票代码",
      "type": "for_each",
      "parameters": {
        "items": "{{codes}}",
        "item_var": "current_code",
        "index_var": "code_index",
        "max_iterations": 100
      }
    },
    {
      "id": "n3",
      "name": "生成该股票模拟K线",
      "type": "custom_python",
      "parameters": {
        "code": "import pandas as pd\nfrom datetime import datetime, timedelta\n\ndef process(df, context=None):\n    \"\"\"根据 context['current_code'] 生成 30 行模拟 K 线\"\"\"\n    ctx = context or {}\n    code = ctx.get('current_code', '000001')\n    idx = ctx.get('code_index', 0)\n\n    # 不同股票用不同的基准价，便于区分\n    base_prices = {'000001': 12.0, '600000': 8.5, '000002': 15.0, '300750': 220.0}\n    base = base_prices.get(code, 10.0 + idx)\n\n    base_time = datetime(2026, 8, 12, 9, 30)\n    rows = []\n    for i in range(30):\n        p = round(base + i * 0.01, 2)\n        rows.append({\n            'code': code,\n            'dt': base_time + timedelta(minutes=i),\n            'open': p,\n            'high': round(p + 0.05, 2),\n            'low':  round(p - 0.03, 2),\n            'close': round(p + 0.02, 2),\n            'volume': 1000 + i * 10,\n        })\n\n    print(f'[INFO] 生成 {code} 模拟K线 {len(rows)} 行')\n    return pd.DataFrame(rows)"
      }
    },
    {
      "id": "n4",
      "name": "等待0.2秒（模拟限流）",
      "type": "wait",
      "parameters": {
        "seconds": 0.2,
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

**预期输出**: 120 行 DataFrame，包含 4 只股票的模拟 K 线。字段：code / dt / open / high / low / close / volume。

**关键学习点**:

| 要点 | 说明 |
|---|---|
| `items` 三种写法 | JSON 数组 `["a","b"]`、逗号分隔 `a, b`、context 引用 `{{codes}}`（推荐） |
| `item_var` / `index_var` | 每轮迭代自动注入到 context，下游 `custom_python` 通过 `context.get('current_code')` 读取 |
| 下游子图被循环"包住" | `for_each` 会 BFS 找出它之后的所有节点作为循环体，本例中 n3 + n4 都会被重复执行 |
| 输出合并 | 每轮迭代的输出 DataFrame 会被 `pd.concat` 合并成一个总表 |
| 与 `custom_python` 搭配 | 当前只有 `custom_python` 节点能真正消费 context 变量；其他节点（source_fetch/target_write）的参数是字面值 |

---

## 25. 条件循环（loop）— 分页拉取直到没有下一页

**测试节点**: `set_variable`(多次) + `loop` + `custom_python` + `wait`
**说明**: 演示 `loop` 节点（while 循环）的经典场景 — 分页拉取。用 `set_variable` 初始化分页状态 `page=0`、`has_more=True`，`loop` 节点在每轮开始前求值 Python 表达式 `context.get('has_more') and context.get('page', 0) < 10`，下游 `custom_python` 模拟分页 API（共 5 页，每页 30 行，第 5 页拉完设 `has_more=False`）。循环自动退出，合并为 150 行数据。**零外部依赖，可直接运行**。

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "初始化页码",
      "type": "set_variable",
      "parameters": {
        "var_name": "page",
        "var_value": "0",
        "value_type": "number"
      }
    },
    {
      "id": "n2",
      "name": "初始化has_more",
      "type": "set_variable",
      "parameters": {
        "var_name": "has_more",
        "var_value": "true",
        "value_type": "json"
      }
    },
    {
      "id": "n3",
      "name": "条件循环（未结束则继续）",
      "type": "loop",
      "parameters": {
        "condition": "context.get('has_more', False) and context.get('page', 0) < 10",
        "max_iterations": 20
      }
    },
    {
      "id": "n4",
      "name": "模拟分页API拉取",
      "type": "custom_python",
      "parameters": {
        "code": "import pandas as pd\n\ndef process(df, context=None):\n    \"\"\"模拟分页 API：共 5 页，每页 30 行，拉完设 has_more=False\"\"\"\n    ctx = context or {}\n    page = ctx.get('page', 0)\n    total_pages = 5\n    rows_per_page = 30\n\n    # 生成当前页的数据（确定性，便于测试）\n    rows = []\n    for i in range(rows_per_page):\n        row_idx = page * rows_per_page + i\n        rows.append({\n            'page': page + 1,\n            'row_idx': row_idx,\n            'value': 100 + row_idx,\n            'batch': f'P{page+1}_R{i:02d}',\n        })\n\n    # 更新分页状态（影响下一轮 loop 条件求值）\n    next_page = page + 1\n    if ctx is not None:\n        ctx['page'] = next_page\n        ctx['has_more'] = next_page < total_pages\n\n    print(f'[INFO] 拉取第 {page+1}/{total_pages} 页，共 {len(rows)} 行，has_more={ctx[\"has_more\"]}')\n    return pd.DataFrame(rows)"
      }
    },
    {
      "id": "n5",
      "name": "等待0.1秒（请求间隔）",
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
    "n3": ["n4"],
    "n4": ["n5"]
  }
}
```

**预期输出**: 150 行 DataFrame（5 页 × 30 行）。字段：page / row_idx / value / batch。page 字段从 1 递增到 5。

**关键学习点**:

| 要点 | 说明 |
|---|---|
| 条件表达式 | Python 表达式，可引用 `context`，必须返回 True/False |
| 求值时机 | 每轮迭代**开始前**求值，False 时立即退出，不执行子图 |
| 状态更新位置 | 在子图内的 `custom_python` 里修改 context，下一轮条件求值就能看到新值 |
| 安全阀 | `max_iterations` 必填，防止条件写错导致死循环（默认 100） |
| 与 for_each 的差异 | for_each 遍历**已知列表**；loop 用于**事先不知道迭代次数**的场景（分页、重试、迭代收敛） |
| 表达式语法 | 支持 `context.get()`、`len()`、`int()`、`float()`；不要用 print / import 等副作用语句 |

**典型适用场景**:

| 场景 | 条件表达式示例 |
|---|---|
| 分页拉取 | `context.get('has_more', False)` |
| 重试直到成功 | `context.get('retry_count', 0) < 5 and not context.get('success', False)` |
| 迭代收敛 | `abs(context.get('last_delta', 1)) > 0.001` |
| 累积行数达标 | `context.get('total_rows', 0) < 100000` |

---


## 节点覆盖清单

| 节点类型 | 显示名称 | 覆盖示例 |
|---------|---------|---------|
| `source_fetch` | 数据源拉取 | 1, 2, 3, 7, 11, 12 |
| `target_write` | 写入目标数据库 | 1, 2, 3, 7, 8, 11, 12 |
| `column_rename` | 列重命名 | 2 |
| `expression` | 表达式计算 | 4, 6 |
| `filter` | 数据过滤 | 3, 5, 7, 9 |
| `sort` | 排序 | 5 |
| `group_by` | 分组聚合 | 5, 7 |
| `condition` | 条件分支 | 4, 6, 10 |
| `custom_python` | 自定义 Python 脚本 | 4, 10, 11, 12, 23, 24, 25 |
| `resample` | 周期重采样 | 2, 3, 7 |
| `ma` | 移动平均(MA/EMA) | 3, 6, 9 |
| `macd` | MACD 指标 | 2, 6, 9 |
| `rsi` | RSI 相对强弱 | 3, 6, 9 |
| `boll` | 布林带(BOLL) | 3, 6, 9 |
| `dedup` | 数据去重 | 5, 8 |
| `time_window` | 时间窗口分批 | 8 |
| `set_variable` | 变量赋值 | 23, 24, 25 |
| `for_each` | 循环遍历 | 23, 24 |
| `loop` | 条件循环 | 25 |
| `wait` | 等待延时 | 23, 24, 25 |
| `factor_compute` | 因子计算 | 14, 15, 16 |
| `factor_write` | 写入因子库 | 14, 15, 16 |
| `outlier_handler` | 异常值处理（官方） | 17 |
| `fill_suspended` | 停牌日填充（官方） | 18 |
| `label_future_return` | 未来收益标签（官方） | 19 |
| `volume_price_divergence` | 量价背离检测（官方） | 20 |
| `candlestick_pattern` | K线形态识别（官方） | 21 |
| `max_drawdown` | 最大回撤与回测指标（官方） | 22 |
