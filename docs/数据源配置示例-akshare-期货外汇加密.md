# AkShare 期货/外汇/加密货币 数据源配置教程

> **覆盖市场**: 国内期货、国际期货、外汇现货、加密货币现货
> **费用**: 完全免费，无需 API Key
> **依赖**: `akshare`（项目中已安装）

---

## 第一步：确认 akshare 已安装

```bash
cd backend
pip show akshare
```

如果未安装：

```bash
pip install akshare --upgrade
```

验证安装：

```bash
python -c "import akshare as ak; df = ak.stock_zh_a_hist(symbol='000001', period='daily', start_date='20240101', end_date='20240110'); print(df)"
```

---

## 第二步：国内期货数据源配置

### 期货日线行情（futures_zh_daily_sina）

在金智汇联 ETL 中操作：

1. 打开「数据源」页面 → 「新建数据源」 → 选 **🟢 AkShare 直连**
2. 点击「API 模板中心」→ 切换到 AkShare tab
3. 找到 **国内期货日线行情**，点击「使用此接口」
4. 或直接配置：

| 字段 | 示例值 | 说明 |
|------|--------|------|
| 请求体模板 | `{"func":"futures_zh_daily_sina","symbol":"V0"}` | symbol 为期货品种代码 |

**常用期货品种代码**:

| 代码 | 品种 | 交易所 |
|------|------|--------|
| V0 | PVC 期货 | 大商所 |
| M0 | 豆粕期货 | 大商所 |
| I0 | 铁矿石期货 | 大商所 |
| RB0 | 螺纹钢期货 | 上期所 |
| CU0 | 铜期货 | 上期所 |
| AU0 | 黄金期货 | 上期所 |
| AG0 | 白银期货 | 上期所 |
| IF0 | 沪深300股指期货 | 中金所 |

### 期货主力合约（futures_main_sina）

| 字段 | 示例值 | 说明 |
|------|--------|------|
| 请求体模板 | `{"func":"futures_main_sina","symbol":"V0"}` | 获取主力合约信息 |

---

## 第三步：外汇数据源配置

### 外汇现货实时报价（fx_spot_quote）

| 字段 | 示例值 | 说明 |
|------|--------|------|
| 请求体模板 | `{"func":"fx_spot_quote","symbol":"美元人民币"}` | 中文货币对名称 |

**常用货币对**:

| Symbol | 说明 |
|--------|------|
| 美元人民币 | USD/CNY |
| 欧元美元 | EUR/USD |
| 英镑美元 | GBP/USD |
| 美元日元 | USD/JPY |
| 澳元美元 | AUD/USD |
| 美元瑞郎 | USD/CHF |
| 美元加元 | USD/CAD |
| 新西兰美元 | NZD/USD |

### 外汇分钟行情（fx_swb_minute_sina）

| 字段 | 示例值 | 说明 |
|------|--------|------|
| 请求体模板 | `{"func":"fx_swb_minute_sina","symbol":"美元人民币"}` | 获取外汇分钟K线 |

---

## 第四步：加密货币数据源配置

### 加密货币现货行情（crypto_js_spot）

| 字段 | 示例值 | 说明 |
|------|--------|------|
| 请求体模板 | `{"func":"crypto_js_spot","symbol":"BTC"}` | 获取加密货币现货价格 |

**常用币种**:

| Symbol | 说明 |
|--------|------|
| BTC | 比特币 |
| ETH | 以太坊 |
| BNB | 币安币 |
| SOL | Solana |
| XRP | 瑞波币 |
| DOGE | 狗狗币 |
| ADA | 卡尔达诺 |
| DOT | Polkadot |

---

## 第五步：通过 API 模板中心快速配置

在金智汇联 ETL 的「API 模板中心」中：

1. 切换到 **🟢 AkShare** tab
2. 找到对应市场接口：
   - 行情分类下: 国内期货日线行情、期货主力合约信息
   - 行情分类下: 外汇现货实时报价、外汇分钟行情
   - 行情分类下: 加密货币现货行情
3. 点击「使用此接口」自动填充到数据源配置

---

## AkShare 各市场接口汇总

| 接口函数 | 覆盖市场 | 数据频率 | 免费 |
|----------|----------|----------|------|
| `stock_zh_a_hist` | A股 | 日/周/月 | ✅ |
| `stock_zh_a_spot_em` | A股实时 | 实时 | ✅ |
| `futures_zh_daily_sina` | 国内期货 | 日线 | ✅ |
| `futures_main_sina` | 期货主力 | 日线 | ✅ |
| `fx_spot_quote` | 外汇现货 | 实时报价 | ✅ |
| `fx_swb_minute_sina` | 外汇 | 分钟K线 | ✅ |
| `crypto_js_spot` | 加密货币 | 现货报价 | ✅ |
| `index_zh_a_hist_em` | A股指数 | 日/周/月 | ✅ |
| `fund_etf_hist_em` | ETF | 日/周/月 | ✅ |

---

## 常见问题

**Q: AkShare 需要 API Key 吗？**
A: 不需要。AkShare 是完全免费的开源 Python 库，数据来源于各大财经网站公开接口。

**Q: 为什么有时获取不到数据？**
A: AkShare 依赖第三方网站的数据接口，源站可能偶尔不稳定或调整接口。建议重试或稍后再试。

**Q: 期货品种代码从哪里查？**
A: 国内期货品种代码可在各期货交易所官网或新浪财经查询。AkShare 的 `futures_main_sina` 可以列出当前主力合约。

**Q: 外汇货币对为什么用中文？**
A: AkShare 的外汇接口使用中文货币对名称，如"美元人民币"而非"USDCNY"。这是新浪外汇数据源的设计。

**Q: 加密货币数据和 Binance 有什么区别？**
A: AkShare 的 crypto_js_spot 提供现货报价（单条记录），适合查看当前价格。Binance 提供完整历史K线数据（OHLCV），适合回测分析。两者可互补使用。

**Q: AkShare 支持期货/外汇的历史K线吗？**
A: 部分支持。`futures_zh_daily_sina` 提供期货日线历史，`fx_swb_minute_sina` 提供外汇分钟线。但数据完整性和时间跨度可能不如专业数据源。
