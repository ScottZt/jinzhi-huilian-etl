## 📋 示例9 详解：全指标流水线（MA → EMA → MACD → RSI → BOLL → 综合过滤）

### 🎯 目标

一条流水线测试全部技术指标，验证数据流通畅性。

---

### 🔗 节点流程图

```
┌─ MA均线 (ma)
  ┌─ EMA均线 (ma)
    ┌─ MACD (macd)
      ┌─ RSI (rsi)
        ┌─ 布林带 (boll)
          ┌─ 综合过滤 (filter)
```

---

### 📦 各节点详解

#### 1️⃣ n1: MA均线

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `ma` |
| 功能 | 计算移动平均线（MA/EMA） |
| 参数 | {"windows": "5,10,20", "source_column": "close", "use_ema": false} |

#### 2️⃣ n2: EMA均线

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `ma` |
| 功能 | 计算移动平均线（MA/EMA） |
| 参数 | {"windows": "12,26", "source_column": "close", "use_ema": true} |

#### 3️⃣ n3: MACD

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `macd` |
| 功能 | 计算 MACD 指标 |
| 参数 | {"fast": 12, "slow": 26, "signal": 9, "source_column": "close"} |

#### 4️⃣ n4: RSI

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n4` |
| 节点类型 | `rsi` |
| 功能 | 计算 RSI 指标 |
| 参数 | {"window": 14, "source_column": "close"} |

#### 5️⃣ n5: 布林带

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n5` |
| 节点类型 | `boll` |
| 功能 | 计算布林带（BOLL） |
| 参数 | {"window": 20, "std_mult": 2, "source_column": "close"} |

#### 6️⃣ n6: 综合过滤

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n6` |
| 节点类型 | `filter` |
| 功能 | 按条件过滤数据 |
| 参数 | {"mode": "keep", "conditions": [{"column": "ma_20", "operator": "is_not_null", "value": ""}, {"column": "macd", "operator": "is_not_null", "value": ""}, {"column": "rsi", "operator": "is_not_null", "v |

---

### 💡 使用场景

本示例适用于需要**一条流水线测试全部技术指标，验证数据流通畅性。**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
