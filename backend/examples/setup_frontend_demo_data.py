"""
金智汇联 ETL — 前端示例数据初始化脚本

通过后端 REST API 创建完整的前端可展示示例：
  1. Pipeline (数据流) — 带目标存储 + 字段映射
  2. ETL 工作流 — 含过滤 + 重命名 + 技术指标
  3. 两者关联：Pipeline 引用 ETL 工作流

用法：
  cd backend
  python examples/setup_frontend_demo_data.py
"""

import httpx
import json

BASE = "http://127.0.0.1:8080"

def print_ok(msg):
    print(f"  [OK] {msg}")

def print_info(msg):
    print(f"  [INFO] {msg}")

def print_err(msg):
    print(f"  [ERROR] {msg}")

def print_step(n, msg):
    print(f"\n{'='*60}")
    print(f"  步骤 {n}: {msg}")
    print(f"{'='*60}")

# ============================================================================
# Step 1: 检查已有数据源和连接
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
            print_ok(f"找到 TDX 数据源: {s['name']} (id={s['id'][:8]}...)")

    for c in conns:
        if c.get("type") == "duckdb":
            duckdb_conn = c
            print_ok(f"找到 DuckDB 连接: {c['name']} (id={c['id'][:8]}...)")

    if not tdx_source:
        print_err("未找到 TDX 数据源，请先运行 tdx_minute_sync_demo.py")
        return None, None

    if not duckdb_conn:
        print_err("未找到 DuckDB 连接")
        return None, None

    return tdx_source, duckdb_conn


# ============================================================================
# Step 2: 创建 ETL 工作流 (过滤 → 重命名 → 移动均线 → 排序)
# ============================================================================
def create_etl_workflow():
    print_step(2, "创建 ETL 工作流: K线数据清洗与指标计算")

    workflow_json = {
        "nodes": [
            {
                "id": "node_filter",
                "type": "filter",
                "name": "数据过滤",
                "parameters": {
                    "mode": "keep",
                    "conditions": [
                        {"column": "open", "operator": "is_not_null"},
                        {"column": "close", "operator": "is_not_null"},
                    ],
                },
                "inputs": [],
                "position": {"x": 100, "y": 100},
            },
            {
                "id": "node_rename",
                "type": "column_rename",
                "name": "列重命名",
                "parameters": {
                    "renames": "code=stock_code,datetime=trade_time",
                },
                "inputs": ["node_filter"],
                "position": {"x": 300, "y": 100},
            },
            {
                "id": "node_ma",
                "type": "ma",
                "name": "移动均线计算",
                "parameters": {
                    "column": "close",
                    "periods": "5,10,20",
                },
                "inputs": ["node_rename"],
                "position": {"x": 500, "y": 100},
            },
            {
                "id": "node_sort",
                "type": "sort",
                "name": "按时间排序",
                "parameters": {
                    "columns": "stock_code,trade_time",
                    "ascending": "true,true",
                },
                "inputs": ["node_ma"],
                "position": {"x": 700, "y": 100},
            },
        ],
        "connections": {
            "node_filter": ["node_rename"],
            "node_rename": ["node_ma"],
            "node_ma": ["node_sort"],
        },
    }

    body = {
        "name": "K线数据清洗与指标计算",
        "description": "过滤空值 → 重命名列 → 计算 5/10/20 日均线 → 按股票代码和时间排序",
        "workflow_json": workflow_json,
    }

    resp = httpx.post(f"{BASE}/api/workflows/", json=body)
    data = resp.json()
    wf_id = data.get("id")
    print_ok(f"工作流已创建: id={wf_id}")
    print_info(f"  节点: 数据过滤 → 列重命名 → 移动均线(5/10/20日) → 排序")
    print_info(f"  可在前端 ETL工作流 页面编辑和查看")

    return wf_id


# ============================================================================
# Step 3: 创建 Pipeline (数据流) — 带目标存储 + 工作流 + 字段映射
# ============================================================================
def create_pipeline(tdx_source, duckdb_conn, workflow_id):
    print_step(3, "创建数据流 (Pipeline): TDX → 工作流 → DuckDB")

    pipeline_json = {
        "sources": [
            {
                "connection_id": tdx_source["id"],
                "params": {
                    "codes": ["000001", "600000"],
                    "interval": "1min",
                    "session_only": True,
                },
            },
        ],
        "target": {
            "connection_id": duckdb_conn["id"],
            "table": "stock_minute_kline_enriched",
        },
        "workflow_id": workflow_id,
        "field_mappings": [
            {"source_field": "stock_code", "target_field": "stock_code", "transform": "direct"},
            {"source_field": "trade_time", "target_field": "trade_time", "transform": "direct"},
            {"source_field": "open", "target_field": "open_price", "transform": "direct"},
            {"source_field": "high", "target_field": "high_price", "transform": "direct"},
            {"source_field": "low", "target_field": "low_price", "transform": "direct"},
            {"source_field": "close", "target_field": "close_price", "transform": "direct"},
            {"source_field": "volume", "target_field": "volume", "transform": "direct"},
            {"source_field": "amount", "target_field": "amount", "transform": "direct"},
            {"source_field": "ma5", "target_field": "ma5", "transform": "direct"},
            {"source_field": "ma10", "target_field": "ma10", "transform": "direct"},
            {"source_field": "ma20", "target_field": "ma20", "transform": "direct"},
        ],
        "batch_size": 5000,
        "on_duplicate": "ignore",
    }

    body = {
        "name": "TDX 分钟K线 → ETL工作流 → DuckDB",
        "description": "从通达信读取1分钟线，经ETL工作流(过滤+重命名+均线计算+排序)后写入DuckDB",
        "pipeline_json": pipeline_json,
        "cron_expression": None,
    }

    resp = httpx.post(f"{BASE}/api/pipelines/", json=body)
    data = resp.json()
    pl_id = data.get("id")
    print_ok(f"数据流已创建: id={pl_id}")
    print_info(f"  数据源: {tdx_source['name']}")
    print_info(f"  工作流: K线数据清洗与指标计算")
    print_info(f"  目标: {duckdb_conn['name']} → stock_minute_kline_enriched")
    print_info(f"  字段映射: 11 个 (含 ma5/ma10/ma20 均线列)")
    print_info(f"  可在前端 数据流(Pipeline) 页面查看和编辑")

    return pl_id


# ============================================================================
# Step 4: 创建带目标表的 DuckDB 表
# ============================================================================
def create_enriched_table():
    print_step(4, "创建目标表: stock_minute_kline_enriched")

    try:
        import duckdb
        db_path = r"D:\04.量化\测试&演示\duckdb\demo_data.db"
        conn = duckdb.connect(db_path, read_only=False)
        conn.execute("DROP TABLE IF EXISTS stock_minute_kline_enriched")
        conn.execute("""
            CREATE TABLE stock_minute_kline_enriched (
                stock_code VARCHAR,
                trade_time TIMESTAMP,
                open_price DOUBLE,
                high_price DOUBLE,
                low_price DOUBLE,
                close_price DOUBLE,
                volume BIGINT,
                amount DOUBLE,
                ma5 DOUBLE,
                ma10 DOUBLE,
                ma20 DOUBLE
            )
        """)
        conn.close()
        print_ok("目标表已创建")
    except Exception as e:
        print_err(f"创建表失败: {e}")


# ============================================================================
# 主流程
# ============================================================================
def main():
    print("=" * 60)
    print("  金智汇联 ETL — 前端示例数据初始化")
    print("=" * 60)

    # Step 1
    tdx_source, duckdb_conn = get_existing_resources()
    if not tdx_source or not duckdb_conn:
        print_err("缺少必要资源，退出")
        return

    # Step 2
    workflow_id = create_etl_workflow()

    # Step 3
    pipeline_id = create_pipeline(tdx_source, duckdb_conn, workflow_id)

    # Step 4
    create_enriched_table()

    print(f"\n{'='*60}")
    print("  初始化完成!")
    print(f"{'='*60}")
    print()
    print("  前端页面可查看以下内容:")
    print("  [数据源]  ->  TDX 本地分钟数据")
    print("  [ETL工作流] -> K线数据清洗与指标计算 (4节点)")
    print("  [数据流]   -> TDX -> 工作流 -> DuckDB")
    print("  [连接管理] -> DuckDB Demo 目标库")
    print("  [表结构]  -> stock_minute_kline_enriched")
    print()
    print("  访问地址: http://localhost:8080")
    print()
    print("  关于 Mootdx 数据源:")
    print("    数据源页面 -> 点击 [新建数据源] -> 在弹窗中:")
    print("    1. 点击 [输入密码解锁] 输入密码")
    print("    2. 解锁后会出现 [Mootdx 私有分钟线] 选项")
    print("    3. 后端需设置环境变量 JZHL_MOOTDX_PASSWORD")
    print()


if __name__ == "__main__":
    main()
