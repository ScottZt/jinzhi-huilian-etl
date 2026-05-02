# QuantSync ETL — K线数据源增量同步方案

## 背景与目标

在现有 ETL 架构基础上，新增量化数据源（通达信、akshare、tushare）连接，将 K 线数据增量同步到 DuckDB 等目标数据库，并支持字段映射和 n8n 工作流式插件链（如 1分钟 → 30分钟 转换）。

参考项目 `D:\04.量化\jin-ce-zhi-suan` 中的 `HistoryDiffSyncService` 增量同步模式。

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (HTML/JS)                            │
│  · 连接管理（新增数据源tab）                                      │
│  · 同步任务管理（K线同步任务）                                     │
│  · 字段映射配置                                                  │
│  · n8n 工作流编辑器（拖拽节点）                                    │
│  · 任务执行监控                                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────────────┐
│                     FastAPI 后端                                 │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │  Connection  │   │    Tasks     │   │   Schemas API     │   │
│  │    API       │   │    API       │   │                   │   │
│  └──────┬───────┘   └──────┬───────┘   └──────────────────┘   │
│         │                  │                                     │
│  ┌──────▼──────────────────▼───────┐                           │
│  │      SQLite 元数据存储           │                           │
│  │  connections / tasks / schemas  │                           │
│  │  / workflows (n8n-style)        │                           │
│  └─────────────────────────────────┘                           │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  执行层 (Execution Layer)                 │   │
│  │                                                          │   │
│  │  ┌──────────────────┐    ┌─────────────────────────────┐ │   │
│  │  │  SourceAdapters  │    │   KLineSyncEngine          │ │   │
│  │  │  ┌────────────┐  │    │                             │ │   │
│  │  │  │ TdxAdapter │  │    │  1. 获取源数据 (df)         │ │   │
│  │  │  │ Akshare    │──┼────│  2. 查询目标已有keys         │ │   │
│  │  │  │ Tushare    │  │    │  3. Diff → 缺失数据         │ │   │
│  │  │  └────────────┘  │    │  4. 执行 n8n 工作流          │ │   │
│  │  │                  │    │  5. 字段映射                │ │   │
│  │  │  ┌────────────┐  │    │  6. 写入目标表               │ │   │
│  │  │  │ n8n Work   │──┼────│                             │ │   │
│  │  │  │ Flow Engine│  │    │                             │   │   │
│  │  │  └────────────┘  │    └─────────────────────────────┘ │   │
│  │  └──────────────────┘                                    │   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────────┐│   │
│  │  │            TargetAdapters + BulkLoaders              ││   │
│  │  │  DuckDB / PostgreSQL / MySQL / ClickHouse            ││   │
│  │  └──────────────────────────────────────────────────────┘│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              TaskScheduler (APScheduler)                   │   │
│  │  定时任务: cron表达式, 触发 KLineSyncEngine                │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、核心概念

### 2.1 标准化 K 线 DataFrame 格式

所有数据源适配器返回统一格式的 pandas DataFrame：

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | string | 股票代码，如 `600036.SH` |
| `dt` | datetime | 时间戳（UTC+8），1分钟K线为精确到分钟 |
| `open` | float | 开盘价 |
| `high` | float | 最高价 |
| `low` | float | 最低价 |
| `close` | float | 收盘价 |
| `vol` | float | 成交量 |
| `amount` | float | 成交额 |

对于日线：`dt` 精确到日末（`15:00:00`），无 `trade_time` 字段。

### 2.2 增量同步核心逻辑

参考 `HistoryDiffSyncService`，每个同步任务执行：

1. **拉取源数据** — 调用对应数据源适配器，按时间范围获取 K 线 DataFrame
2. **查询目标已有记录** — 连接目标数据库，查询 `(code, dt)` 的已存在 key
3. **计算差集** — `source_keys - existing_keys` = 需要写入的新记录
4. **n8n 工作流处理** — 将差集数据送入 n8n 风格工作流，依次经过重采样、过滤、指标计算等节点
5. **字段映射** — 将源字段映射到目标表字段（支持表达式、函数转换）
6. **批量写入** — 分批 UPSERT 到目标表

### 2.3 n8n 工作流集成方案

n8n 的核心优势是**可视化拖拽编排 + 丰富的节点库**。对于 QuantSync ETL 的场景，有三种集成路径：

#### 方案 A：Python 原生 n8n 风格引擎（推荐）

用 Python 实现一套轻量级 n8n 风格的工作流引擎，前端渲染为 n8n 风格的可视化节点编辑器，后端按 DAG 顺序执行节点。

```
数据 → [重采样: 30min] → [过滤: 排除停牌] → [计算: MA5/MA10] → [过滤: 去重] → 结果
```

**节点类型**（对标 n8n）：
| 节点类别 | 节点 | 说明 |
|----------|------|------|
| **数据处理** | Resample Node | K线重采样（1min→5min/15min/30min/60min/D） |
| | Filter Node | 按条件过滤数据行（过滤停牌、异常值等） |
| | Sort Node | 按字段排序 |
| | Group By Node | 分组聚合 |
| **技术指标** | MA/EMA Node | 移动平均线计算 |
| | MACD Node | MACD 指标 |
| | RSI Node | 相对强弱指标 |
| | BOLL Node | 布林带指标 |
| **数据转换** | Column Rename | 列重命名（等价于字段映射） |
| | Expression Node | 自定义 Python 表达式 |
| | Merge/Join | 数据合并（如合并多个 code 的 DataFrame） |
| **流程控制** | Split Node | 按 code 拆分，分别处理后合并 |
| | Condition Node | 按条件分流（if-else 分支） |
| **I/O** | DB Query | 查询外部数据库补充数据 |
| | HTTP Request | 调用外部 API 获取数据 |

**数据流格式**：
- 节点间以 pandas DataFrame 传递
- 每个节点输出可以是主数据流 + 侧输出（如 MA 指标新列）
- 特殊节点（如 Split）会产生多路输出，对应 n8n 的 `Output 0, Output 1...`

**工作流定义**（存储为 JSON，n8n 兼容格式）：
```json
{
  "name": "30minK线转换",
  "nodes": [
    {
      "id": "node_resample",
      "name": "重采样到30分钟",
      "type": "kline_resample",
      "parameters": {
        "rule": "30min",
        "source_interval": "1min"
      },
      "position": [200, 300],
      "outputs": [{}]
    },
    {
      "id": "node_ma",
      "name": "计算MA5/MA10",
      "type": "kline_ma",
      "parameters": {
        "windows": [5, 10],
        "source_column": "close"
      },
      "position": [500, 300],
      "inputs": [{"node": "node_resample", "output": 0}],
      "outputs": [{}]
    },
    {
      "id": "node_filter",
      "name": "过滤NaN",
      "type": "filter",
      "parameters": {
        "conditions": [
          {"column": "open", "operator": "is_not_null"},
          {"column": "close", "operator": ">", "value": 0}
        ]
      },
      "position": [800, 300],
      "inputs": [{"node": "node_ma", "output": 0}],
      "outputs": [{}]
    }
  ],
  "connections": {
    "node_resample": [{"node": "node_ma"}],
    "node_ma": [{"node": "node_filter"}]
  }
}
```

**优势**：
- 无需部署 Node.js 服务，与现有 Python 架构无缝集成
- 前端可借用 n8n 的开源组件（`@n8n/chat` / 自画 Canvas 编辑器）
- 数据直接以 DataFrame 传递，无序列化开销
- 打包进单个 EXE，无外部依赖
- 节点可自由扩展，支持用户自定义 Python 脚本节点

**劣势**：
- 不能直接复用 n8n 现有 400+ 节点库
- 需要自己实现可视化编辑器（前端工作量）

#### 方案 B：n8n Webhook 外部服务

部署独立 n8n 服务，工作流以 n8n Webhook 为入口/出口：

```
Python Engine → POST JSON到n8n Webhook → n8n 处理 → POST 结果回Python
```

**优势**：直接复用 n8n 全部节点和 UI
**劣势**：需额外部署 n8n 服务（Docker/Node.js），与单 EXE 理念冲突

#### 方案 C：混合模式（n8n 设计 + Python 执行）

用户在本机 n8n 中创建/调试工作流，导出为 JSON，QuantSync 后端解析执行。

**优势**：利用 n8n UI 设计，Python 执行
**劣势**：需要维护 JSON schema 转换，n8n 的 JS 表达式无法在 Python 中执行

#### 决策

采用 **方案 A（Python 原生引擎）为主**，但接口设计兼容 n8n 的 JSON 格式。
前端参考 n8n 的 UI 风格，实现拖拽式节点编辑器。
后续如需扩展外部能力，可通过 `HTTP Request Node` 调用 n8n Webhook。

---

## 三、数据模型变更

### 3.1 新增 ConnectionType

```python
# app/models/connection.py
class ConnectionType(str, Enum):
    # 现有...
    TDX = "tdx"           # 通达信行情
    AKSHARE = "akshare"  # akshare 免费数据
    TUSHARE = "tushare"   # tushare Pro
```

### 3.2 工作流模型

```python
# app/models/workflow.py
class WorkflowConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    nodes: List[Dict[str, Any]]    # n8n 风格节点定义
    connections: Dict[str, Any]    # 节点连接关系
    created_at: str
    updated_at: str
```

SQLite 新增表：

```sql
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    workflow_json TEXT NOT NULL,    -- n8n 兼容格式
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 3.3 同步任务配置结构

```json
{
  "id": "uuid",
  "name": "1分钟K线同步到DuckDB（含30min转换）",
  "task_type": "kline_sync",
  "source_connection_id": "uuid",
  "target_connection_id": "uuid",
  "target_table": "kline_30min",
  "config_json": {
    "codes": ["600036.SH", "000001.SZ"],
    "start_date": "2020-01-01",
    "end_date": "2026-12-31",
    "time_mode": "lookback",
    "lookback_days": 10,
    "session_only": true,
    "workflow_id": "uuid_workflow_30min",
    "field_mappings": [
      {"source_field": "code", "target_field": "stock_code"},
      {"source_field": "dt", "target_field": "trade_time"},
      {"source_field": "open", "target_field": "open_price"},
      {"source_field": "close", "target_field": "close_price"},
      {"source_field": "ma5", "target_field": "ma_5"},
      {"source_field": "ma10", "target_field": "ma_10"}
    ],
    "on_duplicate": "ignore",
    "batch_size": 5000
  },
  "status": "pending",
  "cron_expression": "*/30 9-15 * * 1-5"
}
```

### 3.4 目标表 DDL 示例（DuckDB）

```sql
CREATE TABLE kline_1min (
    stock_code VARCHAR,
    trade_time TIMESTAMP,
    open_price DOUBLE,
    high_price DOUBLE,
    low_price DOUBLE,
    close_price DOUBLE,
    vol DOUBLE,
    amount DOUBLE,
    PRIMARY KEY (stock_code, trade_time)
);

CREATE TABLE kline_30min (
    stock_code VARCHAR,
    trade_time TIMESTAMP,
    open_price DOUBLE,
    high_price DOUBLE,
    low_price DOUBLE,
    close_price DOUBLE,
    vol DOUBLE,
    amount DOUBLE,
    ma_5 DOUBLE,
    ma_10 DOUBLE,
    PRIMARY KEY (stock_code, trade_time)
);
```

---

## 四、新增文件清单

| 类别 | 文件路径 | 职责 |
|------|----------|------|
| 适配器 | `app/adapters/source_adapters/tdx_adapter.py` | 通达信 pytdx 行情接口 |
| 适配器 | `app/adapters/source_adapters/akshare_adapter.py` | akshare 免费数据接口 |
| 适配器 | `app/adapters/source_adapters/tushare_adapter.py` | tushare Pro 接口 |
| 引擎 | `app/core/kline_sync_engine.py` | K线增量同步核心逻辑 |
| 模型 | `app/models/workflow.py` | 工作流 Pydantic 模型 |
| 持久化 | `app/persistence/workflow_repo.py` | 工作流 SQLite CRUD |
| 引擎 | `app/core/workflow_engine.py` | n8n 风格工作流执行引擎 |
| 节点 | `app/nodes/__init__.py` | 节点注册表 |
| 节点 | `app/nodes/kline_resample.py` | K线重采样节点 |
| 节点 | `app/nodes/kline_indicators.py` | 技术指标节点（MA/EMA/MACD/RSI/BOLL） |
| 节点 | `app/nodes/filter.py` | 数据过滤节点 |
| 节点 | `app/nodes/sort_group.py` | 排序/分组聚合节点 |
| 节点 | `app/nodes/column_ops.py` | 列操作（重命名/表达式/衍生列） |
| 节点 | `app/nodes/condition.py` | 条件分支节点 |
| 节点 | `app/nodes/http_request.py` | HTTP 请求节点（可调用外部 API/n8n） |
| 节点 | `app/nodes/custom_python.py` | 自定义 Python 脚本节点 |
| API | `app/api/kline_sources.py` | 数据源连接 CRUD + 测试 |
| API | `app/api/kline_sync_tasks.py` | 同步任务 CRUD + 执行 |
| API | `app/api/workflows.py` | 工作流 CRUD + 预览执行 |
| 工具 | `app/utils/kline_normalizer.py` | K线数据标准化 |
| 工具 | `app/utils/duckdb_provider.py` | DuckDB upsert 工具 |

---

## 五、详细实现计划

### Phase 1: 数据源适配器

**TdxAdapter（通达信）**
- 使用 `pytdx` 库，连接本地通达信终端行情服务器
- 配置项：`host`（默认 `127.0.0.1`）、`port`（默认 `7709`）
- `fetch_kline`: 调用 `get_security_bars()` 获取历史K线
- 支持 1分钟、5分钟、15分钟、30分钟、60分钟、日线
- 返回标准 DataFrame（`code, dt, open, high, low, close, vol, amount`）

**AkshareAdapter**
- 使用 `akshare` 库，无需登录
- 配置项：无（或可选 `use_cache`）
- `fetch_kline`: 调用 `ak.stock_zh_a_hist_min_em()` 获取分钟数据
- 免费接口，有频率限制，需要加 retry + rate limit 保护

**TushareAdapter**
- 使用 `tushare` 库，需要 token
- 配置项：`token`
- `fetch_kline`: 调用 `pro.stk_mins()` 获取分钟数据，`pro.daily()` 获取日线
- 有积分限制，rate limit 保护
- 支持本地缓存避免重复请求

### Phase 2: n8n 风格工作流引擎

**WorkflowEngine.execute()** 流程：

```
输入: workflow_json + 初始 DataFrame
1. 解析 JSON，构建节点 DAG
2. 拓扑排序确定执行顺序
3. 从入口节点（无输入边）开始，传入初始 DataFrame
4. 按顺序执行每个节点：
   - 收集上游所有输出
   - 合并为输入 DataFrame
   - 调用节点.process(df, params) → 输出 DataFrame
5. 汇总出口节点的输出
6. 返回最终 DataFrame
```

**节点基类**：

```python
class BaseNode(ABC):
    node_type: str          # 节点类型标识
    display_name: str       # 前端显示名称
    category: str           # 节点分类（数据处理/技术指标/流程控制等）
    params_schema: dict     # 参数 schema（用于前端动态表单）

    @abstractmethod
    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        """执行节点处理，输入/输出均为 DataFrame"""

    def validate(self, params: dict) -> tuple[bool, str]:
        """验证参数是否合法"""
```

**内置节点实现**：

| 节点 | `node_type` | 输入 → 输出 | 说明 |
|------|-------------|-------------|------|
| KLineResample | `kline_resample` | 1min df → 30min df | pandas resample |
| KLineMA | `kline_ma` | df → df+MA列 | 移动平均 |
| KLineMACD | `kline_macd` | df → df+MACD列 | MACD 三值 |
| KLineRSI | `kline_rsi` | df → df+RSI列 | RSI 指标 |
| KLineBOLL | `kline_boll` | df → df+BOLL列 | 布林带 |
| Filter | `filter` | df → 过滤后 df | 条件过滤 |
| Sort | `sort` | df → 排序后 df | 排序 |
| GroupBy | `group_by` | df → 聚合后 df | 分组聚合 |
| ColumnRename | `column_rename` | df → 重命名列 | 列名替换 |
| Expression | `expression` | df → df+新列 | Python 表达式 |
| Condition | `condition` | df → df (分支) | 分流（未来支持多输出） |
| CustomPython | `custom_python` | 自定义 | 用户写 Python 代码 |

### Phase 3: K线同步引擎

**KLineSyncEngine.sync()** 流程：

```
输入: task_id
1. 从 sqlite_repo 获取任务配置
2. 加载源连接、目标连接
3. 解析时间范围 (start_time, end_time)
4. 加载数据源适配器，拉取源数据 df
5. 查询目标已有 keys (按 code+dt)
6. 计算差集 df_diff
7. 加载工作流，执行引擎 → df_workflow
8. 字段映射 → df_mapped (复用 TransformEngine)
9. Upsert 到目标表 (batch_size=5000)
10. 更新任务状态和统计
```

### Phase 4: API 和前端

**API 端点**：

```
# 数据源连接
POST   /api/kline-sources/              # 创建数据源连接
GET    /api/kline-sources/              # 列表
POST   /api/kline-sources/{id}/test     # 测试连接
GET    /api/kline-sources/{id}/codes    # 列出可用代码

# 同步任务
POST   /api/kline-sync-tasks/           # 创建同步任务
GET    /api/kline-sync-tasks/            # 列表
POST   /api/kline-sync-tasks/{id}/run   # 立即执行一次
GET    /api/kline-sync-tasks/{id}/records # 历史执行记录

# 工作流（n8n 风格）
POST   /api/workflows/                  # 创建工作流
GET    /api/workflows/                  # 列表
GET    /api/workflows/{id}              # 获取详情
PUT    /api/workflows/{id}              # 更新工作流
DELETE /api/workflows/{id}              # 删除
POST   /api/workflows/{id}/preview      # 预览执行（返回前N行结果）
```

**前端页面**：

1. **数据源管理页** — 新增 tab，支持配置 Tdx/Akshare/Tushare 连接
2. **同步任务页** — 新建 K 线同步任务，选择源/目标、codes、时间范围、工作流、字段映射
3. **n8n 风格工作流编辑器** — 前端 Canvas 拖拽节点编辑器：
   - 左侧面板：节点列表（按分类展开）
   - 中间区域：节点画布 + 连线
   - 右侧面板：选中节点的参数配置
   - 点击"预览"可试运行，显示节点间的 DataFrame 数据
4. **执行记录** — 查看每次同步的 rows_read/written/errors，查看工作流各节点执行耗时

### Phase 5: 任务调度集成

- `TaskScheduler` 已支持 cron 表达式
- `KLineSyncEngine.sync()` 作为 task callback 传入
- 典型 cron：`*/5 9,10,11,13,14 * * 1-5`（交易时段每5分钟）
- 支持立即执行（manual run）

---

## 六、前端工作流编辑器实现思路

考虑到 n8n 的编辑器是 Vue 3 + 自研 Canvas 组件，直接复用困难。前端采用：

**方案**：基于 `React Flow` 或 `Vue Flow`（取决于前端当前框架）实现：

```
左侧节点面板          中间画布              右侧参数面板
┌──────────────┐   ┌────────────────────┐  ┌────────────────┐
│ 数据处理 ▼   │   │  ┌──────┐          │  │                │
│  · 重采样     │   │  │重采样 │─────┐  │  │ 重采样到30分钟  │
│  · 过滤       │   │  │30min │     │  │  │                │
│  · 排序       │   │  └──────┘     ▼  │  │ rule: 30min ▼  │
│  · 分组       │   │  ┌──────┐ ┌──────┐│  │ 应用           │
│              │   │  │过滤  │ │计算MA ││  │                │
│ 技术指标 ▼   │   │  └──────┘ └──────┘│  │                │
│  · MA        │   │                    │  │                │
│  · MACD      │   │                    │  │                │
│  · RSI       │   │                    │  │                │
│              │   │                    │  │                │
│ 流程控制 ▼   │   │                    │  │                │
│  · 条件分支   │   │                    │  │                │
│  · 自定义脚本 │   │                    │  │                │
└──────────────┘   └────────────────────┘  └────────────────┘
```

节点定义存储在 JS 侧，与后端节点类型一一对应。

---

## 七、依赖变更

```txt
# 新增依赖（数据源）
pytdx>=1.12              # 通达信行情接口
akshare>=1.13           # 免费财经数据
tushare>=1.4            # tushare Pro
```

这些依赖较重，考虑 lazy import，避免拖慢启动速度。

---

## 八、文件变更汇总

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 修改 | `app/models/connection.py` | 新增 TDX/AKSHARE/TUSHARE 枚举值 |
| 新增 | `app/models/workflow.py` | 工作流 Pydantic 模型 |
| 新增 | `app/adapters/source_adapters/tdx_adapter.py` | 通达信数据源适配器 |
| 新增 | `app/adapters/source_adapters/akshare_adapter.py` | akshare 数据源适配器 |
| 新增 | `app/adapters/source_adapters/tushare_adapter.py` | tushare 数据源适配器 |
| 新增 | `app/core/kline_sync_engine.py` | K线同步引擎 |
| 新增 | `app/core/workflow_engine.py` | n8n 风格工作流执行引擎 |
| 新增 | `app/persistence/workflow_repo.py` | 工作流 SQLite CRUD |
| 新增 | `app/nodes/__init__.py` | 节点注册表 |
| 新增 | `app/nodes/kline_resample.py` | K线重采样节点 |
| 新增 | `app/nodes/kline_indicators.py` | 技术指标节点 |
| 新增 | `app/nodes/filter.py` | 过滤节点 |
| 新增 | `app/nodes/sort_group.py` | 排序/分组节点 |
| 新增 | `app/nodes/column_ops.py` | 列操作节点 |
| 新增 | `app/nodes/condition.py` | 条件分支节点 |
| 新增 | `app/nodes/http_request.py` | HTTP 请求节点 |
| 新增 | `app/nodes/custom_python.py` | 自定义 Python 节点 |
| 新增 | `app/api/kline_sources.py` | 数据源 CRUD API |
| 新增 | `app/api/kline_sync_tasks.py` | 同步任务 CRUD API |
| 新增 | `app/api/workflows.py` | 工作流 CRUD API |
| 新增 | `app/utils/kline_normalizer.py` | K线标准化工具 |
| 新增 | `app/utils/duckdb_provider.py` | DuckDB upsert 工具 |
| 修改 | `app/main.py` | 注册新路由 |
| 修改 | `app/api/__init__.py` | 导出新 API 模块 |
| 修改 | `build.spec` | 新增 hidden imports: pytdx, akshare, tushare |

---

## 九、开发阶段建议

### 第一批（核心能力）
1. 3 个数据源适配器（Tdx/Akshare/Tushare）
2. 工作流引擎基类 + 节点注册表
3. K线同步引擎（基础增量逻辑 + 简单插件链）
4. 重采样节点（1min → 5min/15min/30min/60min/D）
5. 同步任务 API + 基础前端表单配置

### 第二批（可视化编辑）
1. 前端 n8n 风格工作流编辑器（Canvas 拖拽）
2. 工作流 CRUD API
3. 工作流预览执行
4. 技术指标节点（MA/EMA/MACD/RSI）

### 第三批（完善）
1. 过滤/排序/分组节点
2. 条件分支节点
3. 自定义 Python 脚本节点
4. HTTP 请求节点（可调用 n8n 外部 Webhook）
5. 节点执行统计与错误排查面板

---

## 十、风险与注意事项

1. **akshare 接口不稳定**: 可能有反爬限制，建议加 retry + cache
2. **tushare 积分限制**: 部分接口需要较高积分，连接失败时给出明确提示
3. **通达信本地客户端**: pytdx 需要客户端在线
4. **大数据量**: 全量历史同步时数据量很大，考虑分批处理 + 进度显示
5. **交易时段判断**: 需要处理 A 股交易规则（9:30-11:30, 13:00-15:00，周末/节假日）
6. **前端工作流编辑器**: Canvas 编辑器和节点表单是较大的前端工作量，建议用 React Flow / Vue Flow 开源组件加速
7. **自定义 Python 节点安全风险**: 用户输入的代码需要用沙箱限制（限制 import、文件系统访问等）
