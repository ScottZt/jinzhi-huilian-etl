// 自动生成自 docs/example_workflows.md —— 勿手动编辑
// 重新生成: python scripts/regen_example_workflows_js.py
window.EXAMPLE_WORKFLOWS_DATA = {
  "filterChips": [
    "全部",
    "快速上手",
    "数据源",
    "指标",
    "策略信号",
    "数据处理",
    "进阶ETL",
    "复权",
    "因子库",
    "官方插件"
  ],
  "examples": [
    {
      "id": 1,
      "title": "数据源拉取 → 写入 DuckDB",
      "description": "从 tdx 本地数据拉取股票分钟线，写入 DuckDB。需要先确保本地有 TDX 数据。",
      "tags": [
        "快速上手",
        "数据源",
        "tdx"
      ]
    },
    {
      "id": 2,
      "title": "Binance 拉取 → 重命名 → 重采样 → MACD → 写入",
      "description": "测试加密货币数据源拉取，完整数据处理链路。",
      "tags": [
        "数据源",
        "指标",
        "数据处理",
        "binance"
      ]
    },
    {
      "id": 3,
      "title": "Yahoo Finance 拉取 → MA → RSI → BOLL → 过滤 → 写入",
      "description": "测试 yfinance 数据源 + 全部技术指标节点组合。",
      "tags": [
        "数据源",
        "指标",
        "数据处理",
        "yfinance"
      ]
    },
    {
      "id": 4,
      "title": "表达式计算 → 条件分支 → 自定义 Python",
      "description": "测试流程控制和高级自定义脚本能力。",
      "tags": [
        "策略信号",
        "数据处理"
      ]
    },
    {
      "id": 5,
      "title": "数据过滤 + 排序 + 分组聚合 + 去重",
      "description": "测试数据处理链路：过滤 → 排序 → 聚合 → 去重。",
      "tags": [
        "快速上手",
        "数据处理"
      ]
    },
    {
      "id": 6,
      "title": "EMA 指标 + 布林带 + 表达式交叉信号",
      "description": "测试 EMA + 布林带 + 自定义表达式组合策略信号。",
      "tags": [
        "指标",
        "策略信号"
      ]
    },
    {
      "id": 7,
      "title": "多股票代码并行拉取 → 过滤 → 重采样 → 分组汇总 → 写入",
      "description": "测试并行拉取能力 + 完整 ETL 流程。",
      "tags": [
        "数据源",
        "进阶ETL",
        "并行"
      ]
    },
    {
      "id": 8,
      "title": "时间窗口分批 + 去重(check_existing) + 写入",
      "description": "测试增量 ETL 场景：按时间窗口分批，排除已有数据后写入。",
      "tags": [
        "进阶ETL",
        "增量"
      ]
    },
    {
      "id": 9,
      "title": "全指标流水线（MA → EMA → MACD → RSI → BOLL → 综合过滤）",
      "description": "一条流水线测试全部技术指标，验证数据流通畅性。",
      "tags": [
        "指标",
        "数据处理"
      ]
    },
    {
      "id": 10,
      "title": "自定义 Python 脚本 — 复杂数据处理",
      "description": "测试自定义 Python 脚本节点的沙箱执行能力。",
      "tags": [
        "策略信号",
        "数据处理",
        "进阶ETL"
      ]
    },
    {
      "id": 11,
      "title": "TDX 本地日 K 复权（前复权 / 后复权）",
      "description": "通达信本地 `.day` 文件读出的是原始价。本示例演示如何基于用户自维护的「复权因子表」，在同一支流水里产出前复权 + 后复权两套价格，并写入 DuckDB 的两张表。",
      "tags": [
        "复权",
        "tdx"
      ]
    },
    {
      "id": 12,
      "title": "TDX 本地日 K + baostock 自动复权（免维护 Excel）",
      "description": "如果不想自维护复权因子 Excel，可用免费开源库 [baostock](http://baostock.com)（BSD 协议，无需注册/token）在线查询复权因子。本示例与示例 11 等价，区别是因子来源从 Excel 换成 baostock API。",
      "tags": [
        "复权",
        "tdx"
      ]
    },
    {
      "id": 13,
      "title": "baostock 直接获取复权 K 线（推荐）",
      "description": "直接使用 baostock 的 `query_history_k_data_plus` 接口获取已复权的 K 线数据，无需手动计算。",
      "tags": [
        "复权"
      ]
    },
    {
      "id": 14,
      "title": "因子库 — MA 因子生产流水线",
      "description": "从数据源拉取日 K 线，计算 MA5/MA10/MA20 均线因子，写入 DuckDB 因子库。这是因子库的基础生产流程。",
      "tags": [
        "因子库"
      ]
    },
    {
      "id": 15,
      "title": "因子库 — 多因子批量生产",
      "description": "批量计算 MACD、RSI 等多个因子，通过工作流串联生产。实际使用中建议每个因子单独一条工作流，便于独立调度和维护。",
      "tags": [
        "因子库"
      ]
    },
    {
      "id": 16,
      "title": "因子库 — 波动率 + 收益率因子",
      "description": "计算 1 日收益率和 20 日年化波动率因子。这类统计因子在量化策略中广泛使用。",
      "tags": [
        "因子库"
      ]
    },
    {
      "id": 17,
      "title": "官方插件 · 异常值处理（乌龙指 / 脏数据清洗）",
      "description": "演示官方精选插件 `outlier_handler`。造一段含异常值的价格数据（第 10 行 5 倍 / 第 30 行 0.1 倍），用 MAD 方法截断到合理范围。",
      "tags": [
        "官方插件",
        "数据处理",
        "异常值"
      ]
    },
    {
      "id": 18,
      "title": "官方插件 · 停牌日填充（A 股缺失数据处理）",
      "description": "演示官方精选插件 `fill_suspended`。模拟 A 股停牌：故意删除第 5/15/30 个交易日的数据，用前值填充价格列、成交量填 0，并输出 `is_suspended` 停牌标记列。",
      "tags": [
        "官方插件",
        "数据处理",
        "A股"
      ]
    },
    {
      "id": 19,
      "title": "官方插件 · 未来收益标签（机器学习打标）",
      "description": "演示官方精选插件 `label_future_return`。基于收盘价生成未来 5 日收益率标签，支持三分类模式（涨=1 / 平=0 / 跌=-1），阈值 0.5%。ML 量化必备。",
      "tags": [
        "官方插件",
        "因子库",
        "机器学习"
      ]
    },
    {
      "id": 20,
      "title": "官方插件 · 量价背离检测",
      "description": "演示官方精选插件 `volume_price_divergence`。识别四种经典信号：顶背离（价涨量缩=1）/ 恐慌放量（价跌量增=-1）/ 底背离（价跌量缩=2）/ 无背离（0）。",
      "tags": [
        "官方插件",
        "指标",
        "量价"
      ]
    },
    {
      "id": 21,
      "title": "官方插件 · K 线形态识别（10 种经典形态）",
      "description": "演示官方精选插件 `candlestick_pattern`。一次识别 10 种经典形态：十字星 / 锤头 / 射击之星 / 阳包阴 / 阴包阳 / 晨星 / 暮星 / 光头光脚 / 纺锤线 / 红三兵，每种形态输出独立信号列。",
      "tags": [
        "官方插件",
        "指标",
        "K线"
      ]
    },
    {
      "id": 22,
      "title": "官方插件 · 最大回撤与回测三大指标",
      "description": "演示官方精选插件 `max_drawdown`。输入净值序列，一次算完最大回撤、年化收益、年化波动、夏普比率、胜率、回撤起止日期等 9 个核心回测指标。",
      "tags": [
        "官方插件",
        "进阶ETL",
        "回测"
      ]
    },
    {
      "id": 23,
      "title": "后复权处理工程化 — 嵌套循环 + 分片处理（大数据友好版）",
      "description": "采用嵌套循环架构：外层遍历 7 张表，内层遍历每个股票代码。每次只处理一只股票的数据，内存占用极低。从 baostock 拉取 fore+back 因子，输出未复权/前复权/后复权 3 张表。共 21 张目标表。",
      "tags": [
        "复权",
        "进阶ETL",
        "大数据"
      ]
    },
    {
      "id": 24,
      "title": "循环遍历（for_each）— 遍历股票代码批量生成模拟数据",
      "description": "演示 `for_each` 节点的基本用法：外层用 `set_variable` 设置一组股票代码，`for_each` 逐个注入 `current_code` 到 context，下游 `custom_python` 读取当前代码生成 30 行模拟 K 线。每只股票处理完等待 0.2s 模拟 API 限流。最终合并为 120 行数据（4 只股票 × 30 行）。。",
      "tags": [
        "快速上手",
        "进阶ETL",
        "循环遍历",
        "for_each"
      ]
    },
    {
      "id": 25,
      "title": "条件循环（loop）— 分页拉取直到没有下一页",
      "description": "演示 `loop` 节点（while 循环）的经典场景 — 分页拉取。用 `set_variable` 初始化分页状态 `page=0`、`has_more=True`，`loop` 节点在每轮开始前求值 Python 表达式 `context.get('has_more') and context.get('page', 0) < 10`，下游 `custom_python` 模拟分页 API（共 5 页，每页 30 行，第 5 页拉完设 `has_more=False`）。循环自动退出，合并为 150 行数据。。",
      "tags": [
        "进阶ETL",
        "条件循环",
        "loop",
        "分页"
      ]
    }
  ]
};
// 兼容旧版：把 examples 也挂到 EXAMPLE_WORKFLOWS
window.EXAMPLE_WORKFLOWS = window.EXAMPLE_WORKFLOWS_DATA.examples;
