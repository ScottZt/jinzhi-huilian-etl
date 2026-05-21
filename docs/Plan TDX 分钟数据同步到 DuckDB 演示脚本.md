                                                                                                                                                                                    
 Context                                                                                                                                                                                                                       用户希望通过通达信分钟数据源（本地文件和 mootdx 在线两种方式）将 K 线分钟数据同步到 DuckDB 数据库，演示完整的 
  ETL 流程：数据源创建 → 连接管理 → 数据流 → ETL 工作流 → 表结构。使用现有后端 API 触发，而非独立 CLI。

 实现方案

 创建 backend/examples/tdx_minute_sync_demo.py，通过 httpx 调用后端 REST API 完成以下流程：

 步骤概览

 1. 检查后端服务状态 (GET /health)
 2. 创建 K 线数据源 (POST /api/kline-sources/)
    ├─ TDX 模式: type="tdx", config={data_dir, interval="1min"}
    └─ Mootdx 模式: 先解锁私有功能 (POST /private/unlock), 再创建 type="mootdx"
 3. 测试数据源连接 (POST /api/kline-sources/{id}/test)
 4. 创建 DuckDB 目标连接 (POST /api/connections/)
 5. 测试目标连接 (POST /api/connections/{id}/test)
 6. 创建 DuckDB 目标表 (直接 duckdb.connect 执行 DDL)
 7. 创建同步任务 (POST /api/kline-sync-tasks/)
 8. 执行同步任务 (POST /api/kline-sync-tasks/{id}/run) + 轮询等待
 9. 验证结果 (直接 duckdb.connect 查询)

 关键设计决策

 表结构 — stock_minute_kline:
 CREATE TABLE IF NOT EXISTS stock_minute_kline (
     stock_code VARCHAR,
     trade_time TIMESTAMP,
     open_price DOUBLE,
     high_price DOUBLE,
     low_price DOUBLE,
     close_price DOUBLE,
     volume BIGINT,
     amount DOUBLE
 )

 字段映射（处理 TDX datetime → trade_time 的列名差异）:
 - TDX: code→stock_code, datetime→trade_time, open→open_price, high→high_price, low→low_price,
 close→close_price, volume→volume, amount→amount
 - Mootdx: code→stock_code, dt→trade_time, vol→volume（其余同 TDX）

 session_only: false — 避免 sync engine 对 dt 列的依赖问题（TDX 输出 datetime 列），同时首次运行时
 _fetch_existing_keys 返回空集，跳过 diff 逻辑。每次演示前 DROP 表确保干净状态。

 DuckDB 路径 — 用户提供的是 D:\04.量化\测试&演示\duckdb\duckdb.exe，脚本在该目录下创建 demo_data.db
 文件作为实际数据库。

 脚本配置

 脚本顶部可配置参数 + CLI 参数支持：
 - --mode tdx|mootdx (默认 tdx)
 - --data-dir <path> (TDX 数据目录，默认需要用户指定)
 - --codes <code1,code2> (股票代码，默认 ["000001", "600000"])
 - --lookback <days> (回看天数，默认 60)
 - --backend-url <url> (后端地址，默认 http://127.0.0.1:8080)

 涉及的关键文件

 ┌────────────────────────────────────────────────────────┬────────────────────────────────┐
 │                          文件                          │              作用              │
 ├────────────────────────────────────────────────────────┼────────────────────────────────┤
 │ backend/app/api/kline_sources.py                       │ 数据源 CRUD API                │
 ├────────────────────────────────────────────────────────┼────────────────────────────────┤
 │ backend/app/api/connections.py                         │ 连接管理 API                   │
 ├────────────────────────────────────────────────────────┼────────────────────────────────┤
 │ backend/app/api/kline_sync_tasks.py                    │ 同步任务 CRUD + 执行 API       │
 ├────────────────────────────────────────────────────────┼────────────────────────────────┤
 │ backend/app/core/kline_sync_engine.py                  │ ETL 同步引擎（拉源→差集→写入） │
 ├────────────────────────────────────────────────────────┼────────────────────────────────┤
 │ backend/app/adapters/source_adapters/tdx_adapter.py    │ 通达信本地文件解析             │
 ├────────────────────────────────────────────────────────┼────────────────────────────────┤
 │ backend/app/adapters/source_adapters/mootdx_adapter.py │ Mootdx 在线行情                │
 ├────────────────────────────────────────────────────────┼────────────────────────────────┤
 │ backend/app/core/connection_manager.py                 │ 连接管理 + DDL 执行            │
 ├────────────────────────────────────────────────────────┼────────────────────────────────┤
 │ backend/requirements.txt                               │ 已有 httpx, duckdb 依赖        │
 └────────────────────────────────────────────────────────┴────────────────────────────────┘

 验证方式

 1. 确保后端服务运行中（python backend/app/main.py 或启动 tray_app）
 2. TDX 模式：确保 data_dir 下有 .1min/.01/.lc1 分钟线文件
 3. Mootdx 模式：确保设置了 JZHL_MOOTDX_PASSWORD 环境变量
 4. 运行脚本：cd backend && python examples/tdx_minute_sync_demo.py --mode tdx --data-dir "你的TDX数据目录"    
 5. 观察输出：各步骤状态、同步行数、DuckDB 查询结果