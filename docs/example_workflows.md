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
        "code": "def process(df):\n    import pandas as pd, numpy as np\n    # 0) 防御：上游 source_fetch 未产出标准 K 线（预览模式 / 本地无 TDX 数据）→ 造一份 sample\n    if df.empty or 'dt' not in df.columns or 'code' not in df.columns:\n        # 拉长到 1200 个交易日（约 5 年），以覆盖足够多的除权事件\n        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=1200)\n        codes = ['000001', '600000']\n        rows = []\n        for c in codes:\n            p = 10.0 if c == '000001' else 8.0\n            for d in dates:\n                p *= (1 + np.random.normal(0, 0.02))\n                rows.append({'code': c, 'dt': d, 'open': round(p*0.999,3),\n                             'high': round(p*1.01,3), 'low': round(p*0.99,3),\n                             'close': round(p,3), 'vol': int(np.random.randint(500,5000)),\n                             'amount': round(p*np.random.randint(500,5000),2)})\n        df = pd.DataFrame(rows)\n    import baostock as bs\n    bs.login()\n    # 1) 代码映射：6 位纯数字 -> sh./sz. 前缀\n    def to_bs(c):\n        s = str(c).zfill(6)\n        return ('sh.' + s) if s.startswith(('6','9')) else ('sz.' + s)\n    # 2) 按股票批量拉取复权因子（扩大查询窗口到近 10 年，以覆盖上市早期事件）\n    code_min = (df['dt'].min() - pd.Timedelta(days=3650)).strftime('%Y-%m-%d')\n    code_max = df['dt'].max().strftime('%Y-%m-%d')\n    rows = []\n    for c in df['code'].unique():\n        rs = bs.query_adjust_factor(code=to_bs(c),\n                                    start_date=code_min, end_date=code_max)\n        while rs.next():\n            r = rs.get_row_data()\n            rows.append({'code': c, 'dt': r[1],\n                         'fore': float(r[2]), 'back': float(r[3])})\n    bs.logout()\n    if not rows:\n        raise RuntimeError('baostock 未返回任何复权因子，请检查代码格式或网络')\n    adj = pd.DataFrame(rows)\n    adj['dt'] = pd.to_datetime(adj['dt'])\n    # 3) merge_asof 要求 on 列全局有序（不是按 by 分组有序），两边都先按 dt 排序\n    df = df.sort_values('dt')\n    adj = adj.sort_values('dt')\n    df = pd.merge_asof(df, adj, on='dt', by='code', direction='backward')\n    # 4) 防御：df 最早一段（早于该 code 第一个除权日）会 NaN，用该 code 最早因子填充\n    first = adj.groupby('code')[['fore', 'back']].first()\n    df = df.set_index('code')\n    for col in ['fore', 'back']:\n        df[col] = df[col].fillna(df.index.to_series().map(first[col]))\n    df = df.reset_index()\n    # 5) 应用复权公式\n    cols = ['open', 'high', 'low', 'close']\n    for c in cols:\n        df[c + '_qfq'] = (df[c] * df['fore']).round(3)\n        df[c + '_hfq'] = (df[c] * df['back']).round(3)\n    return df"
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
    }
  ],
  "connections": {"n1": ["n2"], "n2": ["n3"]}
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

与示例 11 相同；另可直接与通达信客户端的「前复权/后复权」显示值逐日比对，误差应在 1e-3 以内。

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
| `custom_python` | 自定义 Python 脚本 | 4, 10, 11, 12 |
| `resample` | 周期重采样 | 2, 3, 7 |
| `ma` | 移动平均(MA/EMA) | 3, 6, 9 |
| `macd` | MACD 指标 | 2, 6, 9 |
| `rsi` | RSI 相对强弱 | 3, 6, 9 |
| `boll` | 布林带(BOLL) | 3, 6, 9 |
| `dedup` | 数据去重 | 5, 8 |
| `time_window` | 时间窗口分批 | 8 |
