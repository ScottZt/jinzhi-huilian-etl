## 📋 示例10 详解：自定义 Python 脚本 — 复杂数据处理

### 🎯 目标

测试自定义 Python 脚本节点的沙箱执行能力。

---

### 🔗 节点流程图

```
┌─ 自定义: K线形态识别 (custom_python)
  ┌─ 过滤十字星 (condition)
```

---

### 📦 各节点详解

#### 1️⃣ n1: 自定义: K线形态识别

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `custom_python` |
| 功能 | 自定义 Python 脚本 |
| 参数 | {"code": "def process(df):\n    # 识别十字星: 实体很小, 上下影线较长\n    body = abs(df['close'] - df['open'])\n    upper_shadow = df['high'] - df[['close', 'open']].max(axis=1)\n    lower_shadow = df[['close', 'ope |

#### 2️⃣ n2: 过滤十字星

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `condition` |
| 功能 | 条件分支（if/else） |
| 参数 | {"condition": "df['is_doji'] == True", "branch": "true"} |

---

### 💡 使用场景

本示例适用于需要**测试自定义 Python 脚本节点的沙箱执行能力。**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
