## 📋 示例4 详解：表达式计算 → 条件分支 → 自定义 Python

### 🎯 目标

测试流程控制和高级自定义脚本能力。

---

### 🔗 节点流程图

```
┌─ 计算涨跌幅 (expression)
  ┌─ 筛选上涨 (condition)
    ┌─ 自定义信号 (custom_python)
```

---

### 📦 各节点详解

#### 1️⃣ n1: 计算涨跌幅

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `expression` |
| 功能 | 表达式计算（自定义公式） |
| 参数 | {"target_column": "pct_change", "expression": "(df['close'] - df['open']) / df['open'] * 100"} |

#### 2️⃣ n2: 筛选上涨

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `condition` |
| 功能 | 条件分支（if/else） |
| 参数 | {"condition": "df['pct_change'] > 0", "branch": "true"} |

#### 3️⃣ n3: 自定义信号

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `custom_python` |
| 功能 | 自定义 Python 脚本 |
| 参数 | {"code": "def process(df):\n    df['signal'] = 0\n    df.loc[df['pct_change'] > 2, 'signal'] = 1\n    df.loc[df['pct_change'] < -2, 'signal'] = -1\n    return df"} |

---

### 💡 使用场景

本示例适用于需要**测试流程控制和高级自定义脚本能力。**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
