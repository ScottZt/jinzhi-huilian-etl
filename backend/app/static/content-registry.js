// =====================================================================
// 金智汇联 ETL — 内容分级注册表
// =====================================================================
// 用于控制示例工作流在 UI 中的展示层级：
//   tier = "free"  → 可直接导入使用
//   tier = "pro"   → 展示截图预览 + 获取方式（需导入内容包）
//
// 所有代码功能完全开源，不做任何阉割。
// 专业版工作流 JSON 通过 .jspack 内容包交付，不内置于开源代码中。
// =====================================================================

window.CONTENT_REGISTRY = {

  // ==================== 全局获取方式 ====================
  // 内容包通过知识星球/闲鱼购买后获得 .jspack 文件
  acquisition: {
    zsxq: {
      label: "知识星球",
      icon: "🌟",
      url: "https://wx.zsxq.com/group/your-group-id",
      description: "加入知识星球会员，获取全部内容包 + 持续更新",
    },
    xianyu: {
      label: "闲鱼",
      icon: "🐟",
      keyword: "金智汇联ETL",
      description: "闲鱼搜索关键词，购买单次内容包",
    },
  },

  // ==================== 示例分级配置 ====================
  // 内置预设（6 个）来自后端 workflow_presets.py，始终免费
  // 以下 25 个文档示例全部为专业版内容，需导入 .jspack 内容包
  examples: {
    // -------- 所有文档示例均为专业版 --------
    1: {
      tier: "pro",
      screenshot: "screenshots/wf-01-tdx-duckdb.png",
      previewTags: ["TDX本地数据", "写入DuckDB", "快速上手"],
    },
    2: {
      tier: "pro",
      screenshot: "screenshots/wf-02-binance.png",
      previewTags: ["Binance拉取", "重采样", "MACD", "写入DuckDB"],
    },
    3: {
      tier: "pro",
      screenshot: "screenshots/wf-03-yfinance.png",
      previewTags: ["Yahoo拉取", "MA", "RSI", "BOLL", "写入DuckDB"],
    },
    4: {
      tier: "pro",
      screenshot: "screenshots/wf-04-expression-condition.png",
      previewTags: ["表达式计算", "条件分支", "自定义Python"],
    },
    5: {
      tier: "pro",
      screenshot: "screenshots/wf-05-filter-sort-group.png",
      previewTags: ["数据过滤", "排序", "分组聚合", "去重"],
    },
    6: {
      tier: "pro",
      screenshot: "screenshots/wf-06-ema-boll.png",
      previewTags: ["EMA", "布林带", "交叉信号", "表达式"],
    },
    7: {
      tier: "pro",
      screenshot: "screenshots/wf-07-parallel.png",
      previewTags: ["多股票并行", "过滤", "重采样", "分组汇总"],
    },
    8: {
      tier: "pro",
      screenshot: "screenshots/wf-08-window-batch.png",
      previewTags: ["时间窗口分批", "去重", "增量写入"],
    },
    9: {
      tier: "pro",
      screenshot: "screenshots/wf-09-full-indicators.png",
      previewTags: ["MA", "EMA", "MACD", "RSI", "BOLL", "综合过滤"],
    },
    10: {
      tier: "pro",
      screenshot: "screenshots/wf-10-custom-python.png",
      previewTags: ["自定义Python", "复杂数据处理"],
    },
    11: {
      tier: "pro",
      screenshot: "screenshots/wf-11-tdx-adj.png",
      previewTags: ["TDX本地日K", "前复权", "后复权"],
    },
    12: {
      tier: "pro",
      screenshot: "screenshots/wf-12-tdx-baostock.png",
      previewTags: ["TDX", "baostock", "自动复权"],
    },
    13: {
      tier: "pro",
      screenshot: "screenshots/wf-13-baostock.png",
      previewTags: ["baostock", "复权K线", "推荐方案"],
    },
    14: {
      tier: "pro",
      screenshot: "screenshots/wf-14-factor-ma.png",
      previewTags: ["因子库", "MA因子", "生产流水线"],
    },
    15: {
      tier: "pro",
      screenshot: "screenshots/wf-15-factor-batch.png",
      previewTags: ["多因子批量生产", "因子库管理"],
    },
    16: {
      tier: "pro",
      screenshot: "screenshots/wf-16-factor-vol.png",
      previewTags: ["波动率因子", "收益率因子"],
    },
    17: {
      tier: "pro",
      screenshot: "screenshots/wf-17-plugin-outlier.png",
      previewTags: ["官方插件", "异常值处理", "乌龙指清洗"],
    },
    18: {
      tier: "pro",
      screenshot: "screenshots/wf-18-plugin-suspended.png",
      previewTags: ["官方插件", "停牌日填充", "A股缺失数据"],
    },
    19: {
      tier: "pro",
      screenshot: "screenshots/wf-19-plugin-future-return.png",
      previewTags: ["官方插件", "未来收益标签", "机器学习打标"],
    },
    20: {
      tier: "pro",
      screenshot: "screenshots/wf-20-plugin-vol-price.png",
      previewTags: ["官方插件", "量价背离检测"],
    },
    21: {
      tier: "pro",
      screenshot: "screenshots/wf-21-plugin-candlestick.png",
      previewTags: ["官方插件", "K线形态识别", "10种经典形态"],
    },
    22: {
      tier: "pro",
      screenshot: "screenshots/wf-22-plugin-drawdown.png",
      previewTags: ["官方插件", "最大回撤", "回测三大指标"],
    },
    23: {
      tier: "pro",
      screenshot: "screenshots/wf-23-hfq-engineering.png",
      previewTags: ["后复权工程化", "嵌套循环", "大数据友好"],
    },
    24: {
      tier: "pro",
      screenshot: "screenshots/wf-24-for-each.png",
      previewTags: ["循环遍历", "for_each", "批量生成"],
    },
    25: {
      tier: "pro",
      screenshot: "screenshots/wf-25-loop.png",
      previewTags: ["条件循环", "loop", "分页拉取"],
    },
  },

  // ==================== 工具函数 ====================

  /**
   * 获取示例的层级配置
   * @param {number} exampleId
   * @returns {{ tier: "free"|"pro", screenshot?: string, previewTags?: string[], fromPack?: boolean }}
   */
  getExampleTier(exampleId) {
    const cfg = this.examples[exampleId];
    if (!cfg) return { tier: "free" };
    return { ...cfg, fromPack: cfg.tier === "pro" };
  },

  /**
   * 判断示例是否为付费内容
   */
  isPro(exampleId) {
    return this.getExampleTier(exampleId).tier === "pro";
  },

  /**
   * 判断示例是否需要从内容包获取（专业版示例）
   */
  needsPack(exampleId) {
    return this.isPro(exampleId);
  },
};

// 便捷引用
window._CR = window.CONTENT_REGISTRY;
