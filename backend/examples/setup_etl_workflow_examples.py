"""
金智汇联 ETL — ETL 工作流全流程示例初始化

通过后端 REST API 创建完整的示例工作流和数据流，展示如何使用新节点：
  数据源拉取 → 数据去重 → 指标计算 → 写入目标库

示例列表：
  1. TDX 分钟线 → 指标计算 → DuckDB
  2. TDX 增量同步 → 去重 + 均线 → DuckDB
  3. TDX 分钟线 → MACD + BOLL → DuckDB

用法：
  cd backend
  python examples/setup_etl_workflow_examples.py
"""

import httpx
import json
import os

BASE = "http://127.0.0.1:8080"

# DuckDB 文件路径
DUCKDB_DIR = r"D:\04.量化\测试&演示\duckdb"
DUCKDB_PATH = os.path.join(DUCKDB_DIR, "demo_data.db")

def print_ok(msg):
    print(f"  [OK] {msg}")

def print_info(msg):
    print(f"  [INFO] {sanitize(str(msg))}")

def print_err(msg):
    print(f"  [ERROR] {sanitize(str(msg))}")

def print_warn(msg):
    print(f"  [WARN] {sanitize(str(msg))}")

def sanitize(msg):
    return msg.replace("⚠", "!").replace("️", "")

def print_step(n, msg):
    print(f"\n{'='*60}")
    print(f"  步骤 {n}: {msg}")
    print(f"{'='*60}")


# ============================================================================
# Step 1: 查找已有资源
# ============================================================================
def get_existing_resources():
    print_step(1, "查找已有数据源和连接")
    sources = httpx.get(f"{BASE}/api/kline-sources/").json()
    conns = httpx.get(f"{BASE}/api/connections/").json()

    tdx_source = None
    duckdb_conn = None

    for s in sources:
        if s.get("type") == "tdx":
            tdx_source = s
            print_ok(f"找到 TDX 数据源: {s['name']}")

    for c in conns:
        if c.get("type") == "duckdb":
            duckdb_conn = c
            print_ok(f"找到 DuckDB 连接: {c['name']}")

    if not tdx_source:
        print_err("未找到 TDX 数据源，请先运行 tdx_minute_sync_demo.py")
        return None, None
    if not duckdb_conn:
        print_err("未找到 DuckDB 连接")
        return None, None

    return tdx_source, duckdb_conn


# ============================================================================
# Step 2: 创建 ETL 工作流
# ============================================================================
def create_workflows():
    print_step(2, "创建 ETL 工作流示例")
    workflows = []

    # === 工作流 1: TDX 分钟线 → 指标计算 ===
    wf1 = {
        "name": "TDX分钟线 → 指标计算",
        "description": "过滤空值 → 列重命名 → 计算5/10/20日均线 → 按时间排序",
        "workflow_json": {
            "nodes": [
                {
                    "id": "wf1_filter",
                    "type": "filter",
                    "name": "数据过滤",
                    "parameters": {
                        "mode": "keep",
                        "conditions": [
                            {"column": "open", "operator": "is_not_null"},
                            {"column": "close", "operator": "is_not_null"},
                        ],
                    },
                },
                {
                    "id": "wf1_rename",
                    "type": "column_rename",
                    "name": "列重命名",
                    "parameters": {
                        "renames": "code=stock_code,datetime=trade_time",
                    },
                },
                {
                    "id": "wf1_ma",
                    "type": "ma",
                    "name": "移动均线",
                    "parameters": {
                        "windows": "5,10,20",
                        "source_column": "close",
                        "use_ema": False,
                    },
                },
                {
                    "id": "wf1_sort",
                    "type": "sort",
                    "name": "按时间排序",
                    "parameters": {
                        "by": "stock_code,trade_time",
                        "ascending": True,
                    },
                },
            ],
            "connections": {
                "wf1_filter": ["wf1_rename"],
                "wf1_rename": ["wf1_ma"],
                "wf1_ma": ["wf1_sort"],
            },
        },
    }
    resp = httpx.post(f"{BASE}/api/workflows/", json=wf1)
    wf1_id = resp.json().get("id")
    workflows.append({"id": wf1_id, "name": wf1["name"]})
    print_ok(f"工作流已创建: {wf1['name']} (id={wf1_id[:8]}...)")

    # === 工作流 2: 增量同步 — 去重 + 均线 ===
    wf2 = {
        "name": "增量同步 — 去重 + 均线",
        "description": "数据去重 → 过滤空值 → 列重命名 → 计算均线 → 排序",
        "workflow_json": {
            "nodes": [
                {
                    "id": "wf2_dedup",
                    "type": "dedup",
                    "name": "数据去重",
                    "parameters": {
                        "mode": "keep_last",
                        "columns": "code,datetime",
                    },
                },
                {
                    "id": "wf2_filter",
                    "type": "filter",
                    "name": "数据过滤",
                    "parameters": {
                        "mode": "keep",
                        "conditions": [
                            {"column": "open", "operator": "is_not_null"},
                            {"column": "close", "operator": "is_not_null"},
                        ],
                    },
                },
                {
                    "id": "wf2_rename",
                    "type": "column_rename",
                    "name": "列重命名",
                    "parameters": {
                        "renames": "code=stock_code,datetime=trade_time",
                    },
                },
                {
                    "id": "wf2_ma",
                    "type": "ma",
                    "name": "移动均线",
                    "parameters": {
                        "windows": "5,10,20",
                        "source_column": "close",
                        "use_ema": False,
                    },
                },
                {
                    "id": "wf2_sort",
                    "type": "sort",
                    "name": "按时间排序",
                    "parameters": {
                        "by": "stock_code,trade_time",
                        "ascending": True,
                    },
                },
            ],
            "connections": {
                "wf2_dedup": ["wf2_filter"],
                "wf2_filter": ["wf2_rename"],
                "wf2_rename": ["wf2_ma"],
                "wf2_ma": ["wf2_sort"],
            },
        },
    }
    resp = httpx.post(f"{BASE}/api/workflows/", json=wf2)
    wf2_id = resp.json().get("id")
    workflows.append({"id": wf2_id, "name": wf2["name"]})
    print_ok(f"工作流已创建: {wf2['name']} (id={wf2_id[:8]}...)")

    # === 工作流 3: TDX 分钟线 → MACD + BOLL ===
    wf3 = {
        "name": "TDX分钟线 → MACD + BOLL",
        "description": "过滤空值 → 列重命名 → 均线 → MACD → 布林带 → 排序",
        "workflow_json": {
            "nodes": [
                {
                    "id": "wf3_filter",
                    "type": "filter",
                    "name": "数据过滤",
                    "parameters": {
                        "mode": "keep",
                        "conditions": [
                            {"column": "open", "operator": "is_not_null"},
                            {"column": "close", "operator": "is_not_null"},
                        ],
                    },
                },
                {
                    "id": "wf3_rename",
                    "type": "column_rename",
                    "name": "列重命名",
                    "parameters": {
                        "renames": "code=stock_code,datetime=trade_time",
                    },
                },
                {
                    "id": "wf3_ma",
                    "type": "ma",
                    "name": "移动均线",
                    "parameters": {
                        "windows": "5,10,20",
                        "source_column": "close",
                        "use_ema": False,
                    },
                },
                {
                    "id": "wf3_macd",
                    "type": "macd",
                    "name": "MACD指标",
                    "parameters": {
                        "fast": 12,
                        "slow": 26,
                        "signal": 9,
                        "source_column": "close",
                    },
                },
                {
                    "id": "wf3_boll",
                    "type": "boll",
                    "name": "布林带指标",
                    "parameters": {
                        "window": 20,
                        "std_mult": 2,
                        "source_column": "close",
                    },
                },
                {
                    "id": "wf3_sort",
                    "type": "sort",
                    "name": "按时间排序",
                    "parameters": {
                        "by": "stock_code,trade_time",
                        "ascending": True,
                    },
                },
            ],
            "connections": {
                "wf3_filter": ["wf3_rename"],
                "wf3_rename": ["wf3_ma"],
                "wf3_ma": ["wf3_macd"],
                "wf3_macd": ["wf3_boll"],
                "wf3_boll": ["wf3_sort"],
            },
        },
    }
    resp = httpx.post(f"{BASE}/api/workflows/", json=wf3)
    wf3_id = resp.json().get("id")
    workflows.append({"id": wf3_id, "name": wf3["name"]})
    print_ok(f"工作流已创建: {wf3['name']} (id={wf3_id[:8]}...)")

    return workflows


# ============================================================================
# Step 3: 创建 Pipeline (数据流)
# ============================================================================
def create_pipelines(tdx_source, duckdb_conn, workflows):
    print_step(3, "创建数据流 (Pipeline)")
    pipelines = []

    wf1_id = workflows[0]["id"]  # TDX分钟线 → 指标计算
    wf2_id = workflows[1]["id"]  # 增量同步
    wf3_id = workflows[2]["id"]  # MACD + BOLL

    # === Pipeline 1: TDX 分钟线 → 指标计算 → DuckDB ===
    pl1 = {
        "name": "TDX 分钟线 → 指标计算 → DuckDB",
        "description": "从TDX读取1分钟线，经ETL工作流(过滤+重命名+均线计算+排序)后写入DuckDB",
        "pipeline_json": {
            "sources": [
                {
                    "connection_id": tdx_source["id"],
                    "params": {
                        "codes": ["000001", "600000"],
                        "interval": "1min",
                        "session_only": True,
                        "time_mode": "lookback",
                        "lookback_days": 30,
                    },
                },
            ],
            "workflow_id": wf1_id,
            "target": {
                "connection_id": duckdb_conn["id"],
                "table": "stock_minute_kline_with_ma",
            },
            "field_mappings": [
                {"source_field": "stock_code", "target_field": "stock_code"},
                {"source_field": "trade_time", "target_field": "trade_time"},
                {"source_field": "open", "target_field": "open_price"},
                {"source_field": "high", "target_field": "high_price"},
                {"source_field": "low", "target_field": "low_price"},
                {"source_field": "close", "target_field": "close_price"},
                {"source_field": "volume", "target_field": "volume"},
                {"source_field": "amount", "target_field": "amount"},
                {"source_field": "ma5", "target_field": "ma5"},
                {"source_field": "ma10", "target_field": "ma10"},
                {"source_field": "ma20", "target_field": "ma20"},
            ],
            "batch_size": 5000,
            "on_duplicate": "ignore",
        },
        "cron_expression": None,
    }
    resp = httpx.post(f"{BASE}/api/pipelines/", json=pl1)
    pl1_id = resp.json().get("id")
    pipelines.append({"id": pl1_id, "name": pl1["name"]})
    print_ok(f"数据流已创建: {pl1['name']}")
    print_info(f"  工作流: {workflows[0]['name']}")
    print_info(f"  目标表: stock_minute_kline_with_ma")

    # === Pipeline 2: TDX 增量同步 → DuckDB ===
    pl2 = {
        "name": "TDX 增量同步 → 去重 → DuckDB",
        "description": "从TDX读取1分钟线，先去重处理，再计算均线指标，最后写入DuckDB",
        "pipeline_json": {
            "sources": [
                {
                    "connection_id": tdx_source["id"],
                    "params": {
                        "codes": ["000001", "600000"],
                        "interval": "1min",
                        "session_only": True,
                        "time_mode": "lookback",
                        "lookback_days": 30,
                    },
                },
            ],
            "workflow_id": wf2_id,
            "target": {
                "connection_id": duckdb_conn["id"],
                "table": "stock_minute_kline_incremental",
            },
            "field_mappings": [
                {"source_field": "stock_code", "target_field": "stock_code"},
                {"source_field": "trade_time", "target_field": "trade_time"},
                {"source_field": "open", "target_field": "open_price"},
                {"source_field": "high", "target_field": "high_price"},
                {"source_field": "low", "target_field": "low_price"},
                {"source_field": "close", "target_field": "close_price"},
                {"source_field": "volume", "target_field": "volume"},
                {"source_field": "amount", "target_field": "amount"},
                {"source_field": "ma5", "target_field": "ma5"},
                {"source_field": "ma10", "target_field": "ma10"},
                {"source_field": "ma20", "target_field": "ma20"},
            ],
            "batch_size": 5000,
            "on_duplicate": "ignore",
        },
        "cron_expression": None,
    }
    resp = httpx.post(f"{BASE}/api/pipelines/", json=pl2)
    pl2_id = resp.json().get("id")
    pipelines.append({"id": pl2_id, "name": pl2["name"]})
    print_ok(f"数据流已创建: {pl2['name']}")
    print_info(f"  工作流: {workflows[1]['name']}")
    print_info(f"  目标表: stock_minute_kline_incremental")

    # === Pipeline 3: TDX 分钟线 → MACD + BOLL → DuckDB ===
    pl3 = {
        "name": "TDX 分钟线 → MACD + BOLL → DuckDB",
        "description": "从TDX读取1分钟线，计算MACD和布林带指标后写入DuckDB",
        "pipeline_json": {
            "sources": [
                {
                    "connection_id": tdx_source["id"],
                    "params": {
                        "codes": ["000001", "600000"],
                        "interval": "1min",
                        "session_only": True,
                        "time_mode": "lookback",
                        "lookback_days": 30,
                    },
                },
            ],
            "workflow_id": wf3_id,
            "target": {
                "connection_id": duckdb_conn["id"],
                "table": "stock_minute_kline_with_indicators",
            },
            "field_mappings": [
                {"source_field": "stock_code", "target_field": "stock_code"},
                {"source_field": "trade_time", "target_field": "trade_time"},
                {"source_field": "open", "target_field": "open_price"},
                {"source_field": "high", "target_field": "high_price"},
                {"source_field": "low", "target_field": "low_price"},
                {"source_field": "close", "target_field": "close_price"},
                {"source_field": "volume", "target_field": "volume"},
                {"source_field": "amount", "target_field": "amount"},
                {"source_field": "ma5", "target_field": "ma5"},
                {"source_field": "ma10", "target_field": "ma10"},
                {"source_field": "ma20", "target_field": "ma20"},
                {"source_field": "dif", "target_field": "macd_dif"},
                {"source_field": "dea", "target_field": "macd_dea"},
                {"source_field": "macd", "target_field": "macd_hist"},
                {"source_field": "boll_upper", "target_field": "boll_upper"},
                {"source_field": "boll_mid", "target_field": "boll_mid"},
                {"source_field": "boll_lower", "target_field": "boll_lower"},
            ],
            "batch_size": 5000,
            "on_duplicate": "ignore",
        },
        "cron_expression": None,
    }
    resp = httpx.post(f"{BASE}/api/pipelines/", json=pl3)
    pl3_id = resp.json().get("id")
    pipelines.append({"id": pl3_id, "name": pl3["name"]})
    print_ok(f"数据流已创建: {pl3['name']}")
    print_info(f"  工作流: {workflows[2]['name']}")
    print_info(f"  目标表: stock_minute_kline_with_indicators")

    return pipelines


# ============================================================================
# Step 4: 创建 DuckDB 目标表
# ============================================================================
def create_duckdb_tables():
    print_step(4, "创建 DuckDB 目标表")
    try:
        import duckdb
        conn = duckdb.connect(DUCKDB_PATH, read_only=False)

        tables = {
            "stock_minute_kline_with_ma": [
                "stock_code VARCHAR",
                "trade_time TIMESTAMP",
                "open_price DOUBLE",
                "high_price DOUBLE",
                "low_price DOUBLE",
                "close_price DOUBLE",
                "volume BIGINT",
                "amount DOUBLE",
                "ma5 DOUBLE",
                "ma10 DOUBLE",
                "ma20 DOUBLE",
            ],
            "stock_minute_kline_incremental": [
                "stock_code VARCHAR",
                "trade_time TIMESTAMP",
                "open_price DOUBLE",
                "high_price DOUBLE",
                "low_price DOUBLE",
                "close_price DOUBLE",
                "volume BIGINT",
                "amount DOUBLE",
                "ma5 DOUBLE",
                "ma10 DOUBLE",
                "ma20 DOUBLE",
            ],
            "stock_minute_kline_with_indicators": [
                "stock_code VARCHAR",
                "trade_time TIMESTAMP",
                "open_price DOUBLE",
                "high_price DOUBLE",
                "low_price DOUBLE",
                "close_price DOUBLE",
                "volume BIGINT",
                "amount DOUBLE",
                "ma5 DOUBLE",
                "ma10 DOUBLE",
                "ma20 DOUBLE",
                "macd_dif DOUBLE",
                "macd_dea DOUBLE",
                "macd_hist DOUBLE",
                "boll_upper DOUBLE",
                "boll_mid DOUBLE",
                "boll_lower DOUBLE",
            ],
        }

        for table_name, columns in tables.items():
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            cols = ",\n    ".join(columns)
            conn.execute(f"CREATE TABLE {table_name} (\n    {cols}\n)")
            print_ok(f"表已创建: {table_name} ({len(columns)} 个字段)")

        conn.close()
    except Exception as e:
        print_err(f"创建表失败: {e}")
        return False
    return True


# ============================================================================
# Step 5: 执行第一个 Pipeline 验证完整链路
# ============================================================================
def run_first_pipeline(pipelines):
    print_step(5, "执行第一个 Pipeline 验证完整链路")
    pl1_id = pipelines[0]["id"]
    print_info(f"执行: {pipelines[0]['name']}")

    resp = httpx.post(f"{BASE}/api/pipelines/{pl1_id}/run")
    print_ok(f"任务已加入后台队列: {resp.json().get('message', '')}")

    # 轮询等待完成
    import time
    start = time.time()
    while time.time() - start < 120:
        elapsed = int(time.time() - start)
        print(f"\r  已等待 {elapsed}s...", end="", flush=True)
        time.sleep(2)
        runs = httpx.get(f"{BASE}/api/pipelines/{pl1_id}/runs", params={"limit": 1}).json()
        if runs and runs[0].get("status") in ("success", "failed"):
            print()
            rec = runs[0]
            if rec["status"] == "success":
                print_ok(f"Pipeline 执行成功!")
                print_info(f"  读取: {rec.get('rows_read', 0)} 行")
                print_info(f"  写入: {rec.get('rows_written', 0)} 行")
                print_info(f"  耗时: {rec.get('duration', 0):.2f}s")
                return True
            else:
                print_err(f"Pipeline 执行失败: {rec.get('error_message', '未知错误')}")
                return False

    print()
    print_warn("执行超时，任务可能仍在运行中")
    return False


# ============================================================================
# 主流程
# ============================================================================
def main():
    print("=" * 60)
    print("  金智汇联 ETL — ETL 工作流全流程示例初始化")
    print("=" * 60)

    # Step 1
    tdx_source, duckdb_conn = get_existing_resources()
    if not tdx_source or not duckdb_conn:
        print_err("缺少必要资源，退出")
        return

    # Step 2
    workflows = create_workflows()

    # Step 3
    pipelines = create_pipelines(tdx_source, duckdb_conn, workflows)

    # Step 4
    if not create_duckdb_tables():
        print_err("目标表创建失败，退出")
        return

    # Step 5
    run_first_pipeline(pipelines)

    # 汇总
    print(f"\n{'='*60}")
    print("  初始化完成!")
    print(f"{'='*60}")
    print()
    print("  前端页面可查看以下内容:")
    print("  ┌─────────────────────────────────────────────────┐")
    print("  │ [ETL工作流]  3 个工作流                          │")
    print("  │   1. TDX分钟线 -> 指标计算                       │")
    print("  │   2. 增量同步 -> 去重 + 均线                     │")
    print("  │   3. TDX分钟线 -> MACD + BOLL                   │")
    print("  │                                                 │")
    print("  │ [数据流]     3 个 Pipeline                       │")
    print("  │   1. TDX 分钟线 -> 指标计算 -> DuckDB            │")
    print("  │   2. TDX 增量同步 -> 去重 -> DuckDB              │")
    print("  │   3. TDX 分钟线 -> MACD + BOLL -> DuckDB         │")
    print("  │                                                 │")
    print("  │ [表结构]     3 张 DuckDB 表                      │")
    print("  │   1. stock_minute_kline_with_ma                  │")
    print("  │   2. stock_minute_kline_incremental              │")
    print("  │   3. stock_minute_kline_with_indicators          │")
    print("  └─────────────────────────────────────────────────┘")
    print()
    print("  访问地址: http://localhost:8080")
    print()


if __name__ == "__main__":
    main()
