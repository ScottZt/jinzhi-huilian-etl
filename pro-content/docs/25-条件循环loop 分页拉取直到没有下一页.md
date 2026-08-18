## 📋 示例25 详解：条件循环（loop）— 分页拉取直到没有下一页

### 🎯 目标

演示 `loop` 节点（while 循环）的经典场景 — 分页拉取。用 `set_variable` 初始化分页状态 `page=0`、`has_more=True`，`loop` 节点在每轮开始前求值 Python 表达式 `context.get('has_more') and context.get('page', 0) < 10`，下游 `custom_python` 模拟分页 API（共 5 页，每页 30 行，第 5 页拉完设 `has_more=False`）。循环自动退出，合并为 150 行数据。。

---

### 🔗 节点流程图

```
┌─ 初始化页码 (set_variable)
  ┌─ 初始化has_more (set_variable)
    ┌─ 条件循环（未结束则继续） (loop)
      ┌─ 模拟分页API拉取 (custom_python)
        ┌─ 等待0.1秒（请求间隔） (wait)
```

---

### 📦 各节点详解

#### 1️⃣ n1: 初始化页码

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `set_variable` |
| 功能 | 设置变量 |
| 参数 | {"var_name": "page", "var_value": "0", "value_type": "number"} |

#### 2️⃣ n2: 初始化has_more

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `set_variable` |
| 功能 | 设置变量 |
| 参数 | {"var_name": "has_more", "var_value": "true", "value_type": "json"} |

#### 3️⃣ n3: 条件循环（未结束则继续）

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `loop` |
| 功能 | 条件循环 |
| 参数 | {"condition": "context.get('has_more', False) and context.get('page', 0) < 10", "max_iterations": 20} |

#### 4️⃣ n4: 模拟分页API拉取

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n4` |
| 节点类型 | `custom_python` |
| 功能 | 自定义 Python 脚本 |
| 参数 | {"code": "import pandas as pd\n\ndef process(df, context=None):\n    \"\"\"模拟分页 API：共 5 页，每页 30 行，拉完设 has_more=False\"\"\"\n    ctx = context or {}\n    page = ctx.get('page', 0)\n    total_pages = 5\ |

#### 5️⃣ n5: 等待0.1秒（请求间隔）

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n5` |
| 节点类型 | `wait` |
| 功能 | 等待（控制频率） |
| 参数 | {"seconds": 0.1, "mode": "delay"} |

---

### 💡 使用场景

本示例适用于需要**演示 `loop` 节点（while 循环）的经典场景 — 分页拉取。用 `set_variable**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
