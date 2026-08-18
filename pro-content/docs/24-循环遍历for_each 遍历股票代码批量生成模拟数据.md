## 📋 示例24 详解：循环遍历（for_each）— 遍历股票代码批量生成模拟数据

### 🎯 目标

演示 `for_each` 节点的基本用法：外层用 `set_variable` 设置一组股票代码，`for_each` 逐个注入 `current_code` 到 context，下游 `custom_python` 读取当前代码生成 30 行模拟 K 线。每只股票处理完等待 0.2s 模拟 API 限流。最终合并为 120 行数据（4 只股票 × 30 行）。。

---

### 🔗 节点流程图

```
┌─ 设置股票代码列表 (set_variable)
  ┌─ 遍历股票代码 (for_each)
    ┌─ 生成该股票模拟K线 (custom_python)
      ┌─ 等待0.2秒（模拟限流） (wait)
```

---

### 📦 各节点详解

#### 1️⃣ n1: 设置股票代码列表

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n1` |
| 节点类型 | `set_variable` |
| 功能 | 设置变量 |
| 参数 | {"var_name": "codes", "var_value": "[\"000001\",\"600000\",\"000002\",\"300750\"]", "value_type": "json"} |

#### 2️⃣ n2: 遍历股票代码

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n2` |
| 节点类型 | `for_each` |
| 功能 | 循环遍历 |
| 参数 | {"items": "{{codes}}", "item_var": "current_code", "index_var": "code_index", "max_iterations": 100} |

#### 3️⃣ n3: 生成该股票模拟K线

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n3` |
| 节点类型 | `custom_python` |
| 功能 | 自定义 Python 脚本 |
| 参数 | {"code": "import pandas as pd\nfrom datetime import datetime, timedelta\n\ndef process(df, context=None):\n    \"\"\"根据 context['current_code'] 生成 30 行模拟 K 线\"\"\"\n    ctx = context or {}\n    code = |

#### 4️⃣ n4: 等待0.2秒（模拟限流）

| 配置项 | 说明 |
|-------|------|
| 节点 ID | `n4` |
| 节点类型 | `wait` |
| 功能 | 等待（控制频率） |
| 参数 | {"seconds": 0.2, "mode": "delay"} |

---

### 💡 使用场景

本示例适用于需要**演示 `for_each` 节点的基本用法：外层用 `set_variable` 设置一组股票代码，**的场景。

### ⚠️ 注意事项

1. 确保已配置对应的数据源连接
2. 根据实际数据调整参数配置
3. 大数据量时建议分批处理
