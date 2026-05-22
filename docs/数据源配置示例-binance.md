# Binance 数据源配置教程 — 免费加密货币行情数据

> **覆盖市场**: BTC、ETH 等 1000+ 加密货币交易对
> **费用**: 完全免费，公共行情无需 API Key
> **依赖**: `python-binance`

---

## 第一步：安装依赖

在金智汇联 ETL 后端环境中安装 python-binance：

```bash
cd backend
pip install python-binance
```

安装完成后验证：

```bash
python -c "from binance.client import Client; c = Client(); print(c.get_klines(symbol='BTCUSDT', interval='1d', limit=1))"
```

如果输出了类似 `[[1554595200000, '5182.76', ...]]` 的数据，说明安装成功。

---

## 第二步：注册 Binance（可选）

**公共行情不需要注册**，直接使用即可。但如果你需要更高频率的 API 调用限制，可以：

1. 访问 [binance.com](https://www.binance.com) 注册账号
2. 登录后进入 API 管理页面
3. 创建 API Key（仅用于提高调用频率限制，行情接口不需要）
4. 将 API Key 和 Secret 填入数据源配置（可选）

---

## 第三步：配置数据源

在金智汇联 ETL 中操作：

1. 打开「数据源」页面，点击「新建数据源」
2. 选择 **🪙 Binance** 类型卡片
3. 填写配置：

| 字段 | 示例值 | 说明 |
|------|--------|------|
| 交易对 | `BTCUSDT,ETHUSDT,BNBUSDT` | 逗号分隔，格式为基础资产+报价资产 |
| K线周期 | `1d`（日线） | 可选: 1m/5m/15m/30m/1h/4h/1d/1w |
| 预览交易对 | `BTCUSDT` | 用于预览和测试的单只代码 |
| API Key | 留空 | 可选，仅用于提高频率限制 |
| API Secret | 留空 | 可选，仅用于提高频率限制 |

4. 点击「测试连接」验证
5. 点击「预览K线样例」查看数据

---

## 常用交易对参考

| 类别 | 交易对 | 说明 |
|------|--------|------|
| BTC | BTCUSDT, BTCBUSD, BTCETH | 比特币兑USDT/BUSD/ETH |
| ETH | ETHUSDT, ETHBTC | 以太坊兑USDT/BTC |
| 主流币 | BNBUSDT, SOLUSDT, XRPUSDT, DOGEUSDT | 币安币/Solana/瑞波币/狗狗币 |
| 热门小币 | PEPEUSDT, WIFUSDT | MEME币等热门品种 |

**交易对格式规则**: 基础资产 + 报价资产，例如 `BTCUSDT` = BTC 兑 USDT。

---

## K线周期映射

| 系统值 | Binance 值 | 说明 |
|--------|------------|------|
| 1min | 1m | 1分钟 |
| 5min | 5m | 5分钟 |
| 15min | 15m | 15分钟 |
| 30min | 30m | 30分钟 |
| 60min | 1h | 1小时 |
| D | 1d | 日线 |
| 1w | 1w | 周线 |

---

## 常见问题

**Q: 需要 API Key 吗？**
A: 公共行情接口完全免费，无需 API Key 即可使用。

**Q: 调用频率限制是多少？**
A: 公共接口限制约 2400 权重/分钟。一般使用足够，如需更高限制可注册获取 API Key。

**Q: 返回空数据怎么办？**
A: 检查交易对是否拼写正确。Binance 交易对区分大小写，必须使用大写格式如 `BTCUSDT`。

**Q: 支持哪些时间范围的历史数据？**
A: Binance 提供自上线以来的完整历史K线数据。但 1 分钟K线仅保留最近 1-3 个月。

---

## API 模板中心

在「API 模板中心」的 Binance tab 下，可直接点击「使用此接口」自动填充配置：

- **klines**: K线数据（免费），自动设置交易对和周期
- **exchange_info**: 交易对列表，获取所有可交易币种
