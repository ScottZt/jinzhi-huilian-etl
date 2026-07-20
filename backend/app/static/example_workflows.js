// 自动生成自 docs/example_workflows.md —— 勿手动编辑
// 重新生成: python scripts/regen_example_workflows_js.py
window.EXAMPLE_WORKFLOWS = [
  {
    "id": 1,
    "title": "数据源拉取 → 写入 DuckDB",
    "description": "从 tdx 本地数据拉取股票分钟线，写入 DuckDB。需要先确保本地有 TDX 数据。",
    "workflow": {
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
      "connections": {
        "n1": [
          "n2"
        ]
      }
    }
  },
  {
    "id": 2,
    "title": "Binance 拉取 → 重命名 → 重采样 → MACD → 写入",
    "description": "测试加密货币数据源拉取，完整数据处理链路。",
    "workflow": {
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
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n3"
        ],
        "n3": [
          "n4"
        ],
        "n4": [
          "n5"
        ]
      }
    }
  },
  {
    "id": 3,
    "title": "Yahoo Finance 拉取 → MA → RSI → BOLL → 过滤 → 写入",
    "description": "测试 yfinance 数据源 + 全部技术指标节点组合。",
    "workflow": {
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
              {
                "column": "rsi",
                "operator": "is_not_null",
                "value": ""
              },
              {
                "column": "boll_mid",
                "operator": "is_not_null",
                "value": ""
              }
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
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n3"
        ],
        "n3": [
          "n4"
        ],
        "n4": [
          "n5"
        ],
        "n5": [
          "n6"
        ]
      }
    }
  },
  {
    "id": 4,
    "title": "表达式计算 → 条件分支 → 自定义 Python",
    "description": "测试流程控制和高级自定义脚本能力。",
    "workflow": {
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
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n3"
        ]
      }
    }
  },
  {
    "id": 5,
    "title": "数据过滤 + 排序 + 分组聚合 + 去重",
    "description": "测试数据处理链路：过滤 → 排序 → 聚合 → 去重。",
    "workflow": {
      "nodes": [
        {
          "id": "n1",
          "name": "过滤空成交量",
          "type": "filter",
          "parameters": {
            "mode": "keep",
            "conditions": [
              {
                "column": "vol",
                "operator": "is_not_null",
                "value": ""
              },
              {
                "column": "vol",
                "operator": ">",
                "value": 0
              }
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
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n3"
        ],
        "n3": [
          "n4"
        ]
      }
    }
  },
  {
    "id": 6,
    "title": "EMA 指标 + 布林带 + 表达式交叉信号",
    "description": "测试 EMA + 布林带 + 自定义表达式组合策略信号。",
    "workflow": {
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
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n3"
        ],
        "n3": [
          "n4"
        ]
      }
    }
  },
  {
    "id": 7,
    "title": "多股票代码并行拉取 → 过滤 → 重采样 → 分组汇总 → 写入",
    "description": "测试并行拉取能力 + 完整 ETL 流程。",
    "workflow": {
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
              {
                "column": "close",
                "operator": "is_not_null",
                "value": ""
              },
              {
                "column": "vol",
                "operator": "is_not_null",
                "value": ""
              }
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
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n3"
        ],
        "n3": [
          "n4"
        ],
        "n4": [
          "n5"
        ]
      }
    }
  },
  {
    "id": 8,
    "title": "时间窗口分批 + 去重(check_existing) + 写入",
    "description": "测试增量 ETL 场景：按时间窗口分批，排除已有数据后写入。",
    "workflow": {
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
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n3"
        ]
      }
    }
  },
  {
    "id": 9,
    "title": "全指标流水线（MA → EMA → MACD → RSI → BOLL → 综合过滤）",
    "description": "一条流水线测试全部技术指标，验证数据流通畅性。",
    "workflow": {
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
              {
                "column": "ma_20",
                "operator": "is_not_null",
                "value": ""
              },
              {
                "column": "macd",
                "operator": "is_not_null",
                "value": ""
              },
              {
                "column": "rsi",
                "operator": "is_not_null",
                "value": ""
              }
            ]
          }
        }
      ],
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n3"
        ],
        "n3": [
          "n4"
        ],
        "n4": [
          "n5"
        ],
        "n5": [
          "n6"
        ]
      }
    }
  },
  {
    "id": 10,
    "title": "自定义 Python 脚本 — 复杂数据处理",
    "description": "测试自定义 Python 脚本节点的沙箱执行能力。",
    "workflow": {
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
      "connections": {
        "n1": [
          "n2"
        ]
      }
    }
  },
  {
    "id": 11,
    "title": "TDX 本地日 K 复权（前复权 / 后复权）",
    "description": "通达信本地 `.day` 文件读出的是原始价。本示例演示如何基于用户自维护的「复权因子表」，在同一支流水里产出前复权 + 后复权两套价格，并写入 DuckDB 的两张表。",
    "workflow": {
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
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n4"
        ]
      }
    }
  },
  {
    "id": 12,
    "title": "TDX 本地日 K + baostock 自动复权（免维护 Excel）",
    "description": "如果不想自维护复权因子 Excel，可用免费开源库 [baostock](http://baostock.com)（BSD 协议，无需注册/token）在线查询复权因子。本示例与示例 11 等价，区别是因子来源从 Excel 换成 baostock API。",
    "workflow": {
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
      "connections": {
        "n1": [
          "n2"
        ],
        "n2": [
          "n3"
        ]
      }
    }
  }
];
