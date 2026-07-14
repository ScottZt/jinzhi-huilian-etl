<div align="center">
  <img src="./logo.png" alt="金智汇连ETL Logo" width="140" />
  <h1>金智汇连ETL · 通用数据 ETL 基座</h1>
  <p>可插拔的数据抽取、转换、加载框架，为量化投研与任意数据消费场景提供稳定底座。</p>
</div>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white" />
  <img alt="Framework" src="https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white" />
  <img alt="Frontend" src="https://img.shields.io/badge/UI-Dashboard-0A66C2?logo=googlechrome&logoColor=white" />
  <img alt="Status" src="https://img.shields.io/badge/Status-Active-success" />
  <img alt="License" src="https://img.shields.io/badge/License-AGPL--3.0-red" />
</p>

<p align="center">
  <span style="color:red"><b>⚠️ 当前 GitHub 发布是唯一官方版本，其他任何平台、论坛发布均非本人提供，注意风险甄别！</b></span>
</p>

---

## 🎯 定位

**金智汇连ETL** 是一个面向数据密集型应用的**通用 ETL 基座**。

它将数据的 **抽取（Extract）→ 转换（Transform）→ 加载（Load）** 三阶段解耦为标准流水线，既服务于量化投研场景，也可作为**任意数据消费场景的底座**——行情、财务、舆情、物联网、业务数据库，皆可接入。

> 不绑定数据源，不锁定输出端，专注把数据**稳定、可观测、可复用**地送到该去的地方。

---

## 🔁 ETL 三段式流水线

```
  ┌────────────┐     ┌────────────┐     ┌────────────┐
  │  Extract   │ ──▶ │ Transform  │ ──▶ │   Load     │
  │  数据抽取   │     │  清洗转换   │     │  加载输出   │
  └────────────┘     └────────────┘     └────────────┘
       ↓                   ↓                   ↓
  多源异构接入         标准化加工           多端消费分发
  行情/DB/API/文件     去重/对齐/派生        DB/文件/推送/实时流
```

每一段均为**可插拔组件**，按业务需要自由组合。

---

## ✨ 核心能力

### 🔌 Extract · 万物可接

- **关系型数据库**：MySQL / PostgreSQL / SQLite / Oracle
- **文件类**：CSV / Excel / JSON / Parquet / 日志
- **API 接口**：REST / GraphQL，内置鉴权与限流
- **消息队列**：Kafka / RabbitMQ（可选扩展）
- **自定义数据源**：实现标准接口即可接入

### ⚙️ Transform · 灵活可编

- **字段映射 / 类型转换 / 缺失值处理**
- **时间对齐与重采样**（tick → bar → 日频）
- **窗口计算 / 因子派生 / 聚合统计**
- **脚本化算子**：支持 Python 自定义函数热加载
- **流水线编排**：多算子 DAG 组合，顺序可配

### 📤 Load · 多端可送

- **落库**：关系型 DB / ClickHouse / DuckDB
- **落文件**：CSV / Parquet / HDF5
- **实时推送**：WebSocket / 消息队列
- **下游对接**：策略引擎、可视化、报表、模型训练
- **增量更新**：支持去重、upsert、分区覆盖

---

## 🧩 为什么选择它作为数据基座

| 痛点 | 金智汇连ETL 的做法 |
|------|----------------|
| 数据源五花八门，每次都要重写接入 | 统一 Source 接口，新增数据源**只写一个类** |
| 数据质量问题隐蔽，下游反复背锅 | Transform 阶段内置校验、监控、告警 |
| 消费端分散，一套数据多份拷贝 | Load 多端分发，**单一事实源** |
| 任务多了调度混乱 | 内置调度器 + Dashboard 可视化 |
| 扩展靠改源码，升级即冲突 | 插件化设计，**业务代码零侵入** |

---

## 🗺 架构概览

```
┌──────────────────────────────────────────────────────┐
│                    Dashboard / API                   │
│              （任务管理 · 监控 · 配置）                │
└────────────────────┬─────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│                  Scheduler 调度层                     │
│            （定时 / 事件触发 / 依赖编排）              │
└────────────────────┬─────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│                   ETL Pipeline                       │
│   Source  ──▶  Transform  ──▶  Sink  ──▶  Observer  │
└──────────────────────────────────────────────────────┘
```

- **调度层**：定时任务、依赖编排、失败重试
- **Pipeline**：ETL 三段执行主体
- **Observer**：运行指标采集、日志、告警
- **Dashboard/API**：统一入口，可视化与配置

---

## 🚀 快速开始

### 一键启动

**双击根目录 `start.bat` 即可启动**，无需手动安装依赖或配置环境。

启动成功后访问 Dashboard 即可开始使用。

### 手动启动（可选）

如需手动控制启动流程：

```bash
# 克隆仓库
git clone https://github.com/scottzt/jinhui-zhilian-etl.git
cd jinhui-zhilian-etl

# 安装依赖
pip install -r requirements.txt

# 启动后端（FastAPI）
uvicorn api.main:app --reload --port 8000

# 启动 Dashboard
streamlit run dashboard/app.py
```

### 一个最小 ETL 示例

```python
from jinhui_etl import Source, Transform, Sink, Pipeline

# 抽取：从 CSV 读取行情
src = Source.CSV("data/quotes.csv")

# 转换：字段标准化 + 缺失值填充 + 日频重采样
tfm = Transform.chain([
    Transform.rename(columns={"ts": "datetime", "px": "close"}),
    Transform.fillna({"close": "ffill"}),
    Transform.resample("1D"),
])

# 加载：写入 PostgreSQL
sink = Sink.PostgreSQL(dsn="postgresql://...", table="quotes_daily")

# 运行
Pipeline(src, tfm, sink).run()
```

---

## 🛠 技术栈

| 层级 | 选型 |
|------|------|
| 语言 | Python 3.8+ |
| 后端 API | FastAPI |
| 数据计算 | Pandas / NumPy / Polars（可选） |
| 调度 | APScheduler / Celery（可选） |
| 可视化 | Streamlit / ECharts |
| 存储 | SQLAlchemy（多后端适配） |
| 部署 | Docker / Docker Compose |

---

## 📦 适用场景

- 📈 **量化投研**：行情 / 财务 / 另类数据的统一接入与加工
- 🏢 **数据中台**：业务系统数据的汇聚、清洗、分发
- 🤖 **AI / 机器学习**：训练数据的标准化流水线
- 📊 **BI / 报表**：为下游分析提供干净的事实表
- 🔌 **系统集成**：异构系统间的数据同步

---

## 📸 预览

<div align="center">
  <img src="./docs/screenshot_dashboard.png" width="90%" alt="Dashboard"/>
  <img src="./docs/screenshot_pipeline.png" width="90%" alt="Pipeline"/>
</div>

---

## ⚖️ 免责声明

本项目按 **AS-IS** 提供，不承担任何因使用导致的数据损失或业务风险。

生产环境使用前请充分测试，关键路径建议加双校验。

---

## 🤝 贡献

欢迎 Issue 与 Pull Request。

新增数据源、Transform 算子、Sink 输出，均可通过插件形式贡献，无需改动核心代码。

若这个项目对你有帮助，欢迎 Star ✨ 支持一下！

---

## 📄 License

[AGPL-3.0](./LICENSE) © 硅基流码

> 本项目采用 **AGPL-3.0** 协议 —— 目前开源社区中最严格的许可协议。
> 任何使用、修改、衍生、甚至通过网络提供服务的方式，**都必须以相同协议开源全部源码**，包括服务端部署场景。
> 商业闭源使用请联系作者另行授权。

<div align="center">
  <sup>稳定 · 可观测 · 可复用 —— 让数据体面地抵达该去的地方。</sup>
</div>
