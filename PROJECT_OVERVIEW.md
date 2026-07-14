# 金智汇联ETL — 项目全景文档

> 本文档用于 Claude Code 快速理解项目全貌，支撑后续调用 HyperFrames 生成项目介绍/宣传视频。

---

## 一、项目概要

| 字段 | 值 |
|------|-----|
| 项目名称 | 金智汇联ETL (JinZhiHuiLian ETL) |
| 产品定位 | 跨平台桌面端通用ETL数据同步工具 |
| 技术栈 | Python (FastAPI) + 原生前端 (HTML/CSS/JS) |
| 目标用户 | 个人量化交易者、小型量化团队、开发者、数据运维人员 |
| 核心卖点 | 可视化工作流 + AI自动生成脚本 + 合规License授权 |
| 合规原则 | 不内置任何第三方私有协议/SDK/密钥；数据源由用户自行对接 |

---

## 二、整体架构

```
┌────────────────────────────────────────────────────────────┐
│                     前端 (HTML/CSS/JS)                      │
│  index.html (主面板) │ workflow-editor.html (工作流编辑器)   │
└──────────────┬─────────────────────────┬──────────────────┘
               │ REST API                │ WebSocket (实时状态)
┌──────────────▼─────────────────────────▼──────────────────┐
│              FastAPI 后端 (app/)                           │
│  ┌────────────────────────────────────────────────────┐   │
│  │ API 路由层 (18个路由模块)                           │   │
│  │ connections │ tasks │ workflows │ pipelines │ ...   │   │
│  └──────────────────┬─────────────────────────────────┘   │
│                     ▼                                      │
│  ┌────────────────────────────────────────────────────┐   │
│  │ 核心引擎层 (core/)                                  │   │
│  │ workflow_engine  │ kline_sync_engine               │   │
│  │ ai_script_generator │ secure_exec (沙箱)            │   │
│  │ license_manager │ parallel_engine                   │   │
│  │ transform_engine │ execution_engine                 │   │
│  │ credential_manager │ bulk_import_engine             │   │
│  │ file_watcher │ report_generator                     │   │
│  └──────────────────┬─────────────────────────────────┘   │
│                     ▼                                      │
│  ┌────────────────────────────────────────────────────┐   │
│  │ 节点层 (nodes/) — 可插拔工作流节点                   │   │
│  │ source_fetch │ target_write │ filter │ resample     │   │
│  │ indicators(MA/MACD/RSI/BOLL) │ custom_python        │   │
│  └──────────────────┬─────────────────────────────────┘   │
│                     ▼                                      │
│  ┌────────────────────────────────────────────────────┐   │
│  │ 适配器层 (adapters/)                                │   │
│  │ 数据源: tdx │ mootdx │ akshare │ tushare            │   │
│  │         binance │ yfinance │ csv │ excel │ json     │   │
│  │ 目标: duckdb │ mysql │ postgresql │ clickhouse       │   │
│  └──────────────────┬─────────────────────────────────┘   │
│                     ▼                                      │
│  ┌────────────────────────────────────────────────────┐   │
│  │ SDK层 (etl_tool_sdk/) — 对外暴露接口                 │   │
│  │ DataConnector │ DataCleaner │ ScriptExecutor        │   │
│  │ WorkflowScheduler │ LogHandler │ LicenseManager      │   │
│  └────────────────────────────────────────────────────┘   │
│                     ▼                                      │
│  ┌────────────────────────────────────────────────────┐   │
│  │ 持久化层 (persistence/sqlite_repo)                  │   │
│  │ SQLite 存储连接配置、任务、工作流、License元数据      │   │
│  └────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

---

## 三、核心功能模块详解

### 3.1 数据源适配器 (Source Adapters)

| 适配器 | 说明 | 文件 |
|--------|------|------|
| TdxAdapter | 通达信本地 .day/.1min/.5min K线文件解析 | `tdx_adapter.py` |
| MootdxAdapter | Mootdx 分钟线数据源 | `mootdx_adapter.py` |
| AkShareAdapter | AkShare A股/期货/免费在线接口 | `akshare_adapter.py` |
| TushareAdapter | Tushare A股数据源（需Token） | `tushare_adapter.py` |
| BinanceAdapter | Binance 加密货币行情（免费） | `binance_adapter.py` |
| YfinanceAdapter | Yahoo Finance 多市场行情（免费） | `yfinance_adapter.py` |
| CsvAdapter | CSV文件读取 | `csv_adapter.py` |
| ExcelAdapter | Excel文件读取 | `excel_adapter.py` |
| JsonAdapter | JSON文件读取 | `json_adapter.py` |
| ParquetAdapter | Parquet文件读取 | `parquet_adapter.py` |

所有适配器继承 `KLineSourceAdapter` 基类，统一返回标准 DataFrame 格式：
`[code, dt, open, high, low, close, vol, amount]`

### 3.2 目标适配器 (Target Adapters) + 批量加载器

| 目标 | 批量加载器 | 说明 |
|------|-----------|------|
| DuckDB | `duckdb_bulk.py` | 本地OLAP数据库，默认目标 |
| MySQL | `mysql_bulk.py` | 关系型数据库 |
| PostgreSQL | `postgres_bulk.py` | 关系型数据库 |
| ClickHouse | `clickhouse_bulk.py` | 列式OLAP数据库 |

### 3.3 工作流节点 (Nodes) — n8n风格可视化DAG

| 节点类型 | 显示名称 | 分类 | 功能 |
|----------|----------|------|------|
| `source_fetch` | 数据源拉取 | 数据接入 | 按时间范围+代码拉K线，支持并行 |
| `target_write` | 写入目标数据库 | 数据输出 | 写入 DuckDB/MySQL/PG/ClickHouse |
| `filter` | 数据过滤 | 数据处理 | 多条件行过滤（>, <, ==, contains等） |
| `resample` | K线重采样 | 数据处理 | 分钟线→日线、5min→30min等 |
| `ma` | 移动平均(MA/EMA) | 指标计算 | 多窗口MA/EMA计算 |
| `macd` | MACD指标 | 指标计算 | DIF/DEA/MACD三值计算 |
| `rsi` | RSI相对强弱 | 指标计算 | RSI指标计算 |
| `boll` | 布林带(BOLL) | 指标计算 | 中轨/上轨/下轨 |
| `column_ops` | 列操作 | 数据处理 | 选择列、重命名、计算列 |
| `condition` | 条件分支 | 流程控制 | 按条件走不同分支 |
| `custom_python` | 自定义Python | 数据处理 | 沙箱内执行用户脚本 |
| `sort_group` | 排序分组 | 数据处理 | 排序、分组聚合 |
| `range_control` | 范围控制 | 数据处理 | 数值范围裁剪 |

### 3.4 K线同步引擎 (KLineSyncEngine)

**核心流程**:
```
拉取源数据 → 交易时段过滤 → 查询目标已有数据 → 计算差集
→ 可选工作流处理 → 字段映射 → 批量写入目标 → 记录日志
```

- 增量同步：基于 `(code, dt)` 复合键做差集比对
- 支持断点续传、失败重试
- 支持多工作流串联处理（transform pipeline）

### 3.5 AI脚本生成器 (AiScriptGenerator)

- 用户输入自然语言描述 → 自动生成适配 `etl_tool_sdk` 的Python脚本
- 内置合规检查：过滤交易、破解、逆向等违规请求
- LLM模式：调用 OpenAI 兼容 API
- 模板回退模式：无LLM时使用规则模板生成基础脚本
- 支持脚本优化指令（需付费版）
- 免费版每日限3次，付费版无限制

**支持的场景模板**:
- CSV → MySQL / SQLite / DuckDB
- HTTP API → 数据库
- Excel 处理
- 数据清洗脚本
- 定时调度脚本

### 3.6 安全沙箱 (Secure Exec)

- AST 级别验证：禁止 import、exec、eval、open 等危险操作
- `_SafeProxy` 对象代理：阻止 `__class__`、`__globals__` 等自省逃逸
- 代码大小限制：64KB
- 完整的 `__builtins__` 白名单控制

### 3.7 License 授权系统

| 版本 | 价格 | 工作流数 | 数据库 | AI生成 | 并发 | 核心特性 |
|------|------|----------|--------|--------|------|----------|
| Free | 免费 | 1 | MySQL, SQLite | 每日3次 | 1 | 基础功能 |
| Personal | 69元/月 | ≤5 | +DuckDB, PG | 无限 | 5 | HTTP连接器、断点续传 |
| Professional | 599元/年 | 无限 | +ClickHouse | 无限 | 无限 | 分布式调度、批量脚本 |

**授权机制**:
- 基于设备机器码绑定（CPU ID + 卷序列号 + 主机名 + 用户名）
- HMAC-SHA256 签名验证激活码
- 支持在线激活 + 离线 .lic 文件激活
- 支持解绑/重新授权

---

## 四、API 路由清单

| 路由前缀 | 功能 | 文件 |
|----------|------|------|
| `/api/connections` | 数据库连接管理 | `api/connections.py` |
| `/api/schemas` | 数据Schema管理 | `api/schemas.py` |
| `/api/auth` | 认证登录 | `api/auth.py` |
| `/api/tasks` | 同步任务CRUD | `api/tasks.py` |
| `/api/bulk-import` | 批量导入 | `api/bulk_import.py` |
| `/api/monitor` | 运行监控 | `api/monitor.py` |
| `/api/file-watchers` | 文件监听 | `api/file_watchers.py` |
| `/api/transforms` | 数据转换 | `api/transforms.py` |
| `/api/reports` | 报告生成 | `api/reports.py` |
| `/api/kline-sources` | K线数据源管理 | `api/kline_sources.py` |
| `/api/credentials` | 凭据管理 | `api/credentials.py` |
| `/api/kline-sync-tasks` | K线同步任务 | `api/kline_sync_tasks.py` |
| `/api/workflows` | 工作流管理 | `api/workflows.py` |
| `/api/pipelines` | Pipeline管理 | `api/pipelines.py` |
| `/api/license` | License激活/管理 | `api/license.py` |
| `/api/ai-script` | AI脚本生成 | `api/ai_script.py` |
| `/api/llm` | LLM配置 | `api/llm.py` |
| `/api/files` | 文件操作 | `api/file_utils.py` |

**中间件**:
- CORS 中间件
- API 限流中间件（500次/分钟/IP）
- API 审计日志中间件
- API 鉴权中间件

---

## 五、技术亮点（适合视频展示）

1. **可视化DAG工作流** — n8n风格拖拽编排，节点间DataFrame流转
2. **多数据源统一适配** — 6种行情数据源 + 5种文件格式，统一K线标准格式
3. **AI脚本自动生成** — 自然语言描述需求，自动生成SDK适配脚本
4. **安全沙箱执行** — AST验证 + 对象代理双重防护
5. **增量同步引擎** — 差集计算 + 断点续传 + 失败重试
6. **License商业授权** — 机器码绑定 + HMAC签名 + 分层权限
7. **多目标批量写入** — DuckDB/MySQL/PG/ClickHouse 分块批量导入
8. **技术指标计算** — MA/EMA/MACD/RSI/BOLL 等量化指标
9. **K线重采样** — 分钟线→小时线→日线灵活转换
10. **WebSocket实时推送** — 运行状态实时推送前端

---

## 六、文件结构速览

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # 配置
│   ├── bootstrap.py               # 启动引导
│   ├── tray_app.py                # 系统托盘应用
│   ├── api/                       # 18个API路由模块
│   ├── core/                      # 核心引擎（12个模块）
│   ├── nodes/                     # 工作流节点（11个模块）
│   ├── adapters/
│   │   ├── source_adapters/       # 10个数据源适配器
│   │   └── target_adapters/       # 4个目标适配器 + 批量加载器
│   ├── models/                    # Pydantic数据模型
│   ├── middleware/                # 中间件（限流、审计、鉴权）
│   ├── persistence/               # SQLite持久化
│   └── static/                    # 前端页面（index.html等）
├── etl_tool_sdk/                  # 对外SDK
│   ├── __init__.py                # 导出 8 个核心类
│   ├── connector.py               # DataConnector（读/写数据库/文件/HTTP）
│   ├── cleaner.py                 # DataCleaner（清洗/转换/校验）
│   ├── executor.py                # ScriptExecutor（沙箱执行）
│   ├── scheduler.py               # WorkflowScheduler（定时调度）
│   ├── logger.py                  # LogHandler（日志）
│   ├── license.py                 # LicenseManager（授权校验）
│   └── config.py                  # SDK配置
└── build.spec                     # PyInstaller打包配置
```

---

## 七、数据流转示意（适合视频画面）

```
用户自然语言需求
       │
       ▼
┌─ AI脚本生成器 ─┐     ┌─ 可视化工作流编辑器 ─┐
│ "读取CSV过滤后   │     │  [拉取]→[过滤]→[指标]  │
│  写入DuckDB"    │     │  →[重采样]→[写入]      │
└───────┬────────┘     └────────┬───────────────┘
        │                       │
        ▼                       ▼
┌───────────────────────────────────────────┐
│         SDK 执行引擎 (etl_tool_sdk)        │
│  DataConnector → DataCleaner → TargetWrite│
│  [沙箱保护] [License校验]                  │
└───────────────────┬───────────────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  DuckDB / MySQL / PG  │
        │  / ClickHouse / 文件  │
        └───────────────────────┘
```

---

## 八、关键约束（开发时注意）

1. **合规红线**: 不内置任何第三方私有协议/SDK/密钥，所有数据源参数由用户自行填写
2. **Python版本**: 兼容 Python 3.7+
3. **系统**: Windows 10+ / macOS 12+
4. **前端**: 原生 HTML/CSS/JS（无框架依赖），暗色/亮色双主题
5. **数据库**: 配置和元数据全部存 SQLite
6. **通信**: REST API + WebSocket 实时推送
7. **打包**: PyInstaller 打包为单exe + static目录