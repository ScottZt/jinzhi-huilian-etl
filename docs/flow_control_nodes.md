# ETL 工作流基础控制节点使用手册

> 最后更新：2026-08-09

本文档介绍 ETL 工作流框架的**基础控制节点**，用于搭建复杂的多节点工作流。

---

## 目录

1. [概述](#概述)
2. [set_variable - 变量赋值](#set_variable---变量赋值)
3. [wait - 等待延时](#wait---等待延时)
4. [for_each - 循环遍历](#for_each---循环遍历)
5. [工作流全局上下文](#工作流全局上下文)
6. [最佳实践](#最佳实践)
7. [示例：多表批量处理](#示例多表批量处理)

---

## 概述

传统 ETL 工作流节点（如 `db_query`、`custom_python`、`target_write`）专注于**数据处理**，但缺少**流程控制**能力。当需要处理多张表、多个 code 时，只能把所有逻辑塞进单个 `custom_python` 节点，失去可视化优势。

**基础控制节点**解决了这个问题：

| 节点 | 作用 | 典型场景 |
|---|---|---|
| `set_variable` | 存储中间状态 | 保存表名列表、累计行数、循环索引 |
| `wait` | 延时执行 | API 限流、等待文件生成、避免 CPU 过载 |
| `for_each` | 循环遍历 | 遍历多张表、多个 code、批量处理 |

---

## set_variable - 变量赋值

**作用**：将值存储到工作流全局上下文（`context`），供下游节点读取。

### 参数

| 参数 | 类型 | 说明 | 示例 |
|---|---|---|---|
| `var_name` | text | 变量名 | `tables`、`counter`、`total_rows` |
| `var_value` | textarea | 变量值 | 根据 `value_type` 填写 |
| `value_type` | select | 值类型 | `string` / `number` / `json` / `expression` |

### 值类型说明

#### string（字符串）
直接填写字符串内容：
```
var_name: my_table
var_value: dat_day
```

#### number（数字）
填写数字（整数或浮点数）：
```
var_name: batch_size
var_value: 500000
```

#### json（JSON）
填写合法的 JSON 数组或对象：
```
var_name: tables
var_value: ["dat_day", "dat_60mins", "dat_30mins"]
```

#### expression（表达式）
填写 Python 表达式，可以引用 `context` 里的其他变量：
```
var_name: next_counter
var_value: context.get("counter", 0) + 1
```

### 使用示例

**示例 1：设置表名列表**
```json
{
  "id": "n1",
  "name": "设置表名",
  "type": "set_variable",
  "parameters": {
    "var_name": "tables",
    "var_value": "[\"dat_day\", \"dat_60mins\"]",
    "value_type": "json"
  }
}
```

**示例 2：累加计数器**
```json
{
  "id": "n2",
  "name": "累加行数",
  "type": "set_variable",
  "parameters": {
    "var_name": "total_rows",
    "var_value": "context.get('total_rows', 0) + len(df)",
    "value_type": "expression"
  }
}
```

---

## wait - 等待延时

**作用**：暂停工作流执行指定时间，常用于 API 限流、等待外部资源。

### 参数

| 参数 | 类型 | 说明 | 默认值 |
|---|---|---|---|
| `seconds` | number | 等待秒数（支持小数） | `1` |
| `mode` | select | 模式 | `delay` |
| `target_timestamp` | text | 目标时间戳（unix 秒） | 空 |

### 模式说明

#### delay（固定延时）
等待指定秒数：
```json
{
  "seconds": 0.5,
  "mode": "delay"
}
```

#### until_timestamp（等待到指定时间）
等待到指定的 unix 时间戳：
```json
{
  "mode": "until_timestamp",
  "target_timestamp": "1723161600"  // 2024-08-09 00:00:00
}
```

### 使用示例

**示例：API 调用间隔 100ms**
```
HTTP 请求 → wait(0.1s) → HTTP 请求 → wait(0.1s) → ...
```

---

## for_each - 循环遍历

**作用**：对列表逐项执行下游节点链，是构建复杂工作流的核心节点。

### 参数

| 参数 | 类型 | 说明 | 默认值 |
|---|---|---|---|
| `items` | textarea | 循环列表 | `["item1", "item2"]` |
| `item_var` | text | 当前项变量名 | `current_item` |
| `index_var` | text | 索引变量名 | `item_index` |
| `max_iterations` | number | 最大迭代次数 | `1000` |

### items 格式

#### JSON 数组
```json
["dat_day", "dat_60mins", "dat_30mins"]
```

#### 逗号分隔
```
dat_day, dat_60mins, dat_30mins
```

#### 从 context 读取
```
{{tables}}
```
（需要先用 `set_variable` 设置 `tables` 变量）

### 工作原理

1. 解析 `items` 列表
2. 对每项：
   - 注入 `context[item_var]` = 当前项
   - 注入 `context[index_var]` = 当前索引（从 0 开始）
   - 递归执行下游子图
3. 合并所有项的输出 DataFrame

### 下游节点读取当前项

下游节点通过 `context.get("current_item")` 读取当前项。

**注意**：`custom_python` 节点的 `process(df)` 函数没有 `context` 参数，需要通过其他方式读取（见下方"工作流全局上下文"章节）。

### 使用示例

**示例：遍历表名列表**
```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "设置表名",
      "type": "set_variable",
      "parameters": {
        "var_name": "tables",
        "var_value": "[\"dat_day\", \"dat_60mins\"]",
        "value_type": "json"
      }
    },
    {
      "id": "n2",
      "name": "遍历表",
      "type": "for_each",
      "parameters": {
        "items": "{{tables}}",
        "item_var": "current_table",
        "index_var": "table_index"
      }
    },
    {
      "id": "n3",
      "name": "查询当前表",
      "type": "db_query",
      "parameters": {
        "sql": "SELECT * FROM {{current_table}} LIMIT 10"
      }
    }
  ],
  "connections": {
    "n1": ["n2"],
    "n2": ["n3"]
  }
}
```

---

## 工作流全局上下文

### 什么是 context？

`context` 是一个 Python dict，贯穿整个工作流执行过程，所有节点都可以读写它。

### 特殊变量

引擎自动注入的特殊变量（以 `__` 开头）：

| 变量 | 说明 |
|---|---|
| `__workflow_json__` | 当前工作流的完整 JSON 定义 |
| `__current_node_id__` | 当前正在执行的节点 ID |

### 在 custom_python 中读取 context

`custom_python` 节点的 `process(df)` 函数签名没有 `context` 参数，但可以通过以下方式读取：

**方法 1：通过闭包（推荐）**
```python
def process(df):
    import pandas as pd
    # context 通过闭包注入（引擎在调用时自动注入）
    current_item = context.get("current_item")
    print(f"处理: {current_item}")
    return df
```

**方法 2：通过全局变量（不推荐）**
```python
# 在代码顶部定义
_CONTEXT = {}

def process(df):
    # 无法直接访问 context，需要用其他方法
    return df
```

**建议**：如果需要在 `custom_python` 中读取 context，改用 `db_query` 节点（支持 `{{variable}}` 语法）或在 `for_each` 之前用 `set_variable` 把值写入 DataFrame 列。

---

## 最佳实践

### 1. 变量命名规范

- 使用小写字母和下划线：`my_variable`
- 避免使用特殊字符或空格
- 不要以 `__` 开头（保留给引擎）

### 2. 防止死循环

- `for_each` 节点设置了 `max_iterations` 上限（默认 1000）
- 如果列表超过上限，会被截断并打印警告

### 3. 内存控制

- `for_each` 会合并所有项的输出 DataFrame
- 如果单项输出很大，可能导致内存峰值
- 建议：在循环内部用 `target_write` 写入数据库，而不是返回 DataFrame

### 4. 错误处理

- 当前版本没有 `try_catch` 节点（P1 计划中）
- 如果某项执行失败，`for_each` 会跳过该项，继续处理下一项
- 建议：在下游节点内部做异常捕获

---

## 示例：多表批量处理

### 场景

从 DuckDB 读取 3 张表（dat_day、dat_60mins、dat_30mins），对每张表执行相同的数据清洗逻辑，然后写入另一张表。

### 工作流结构

```
set_variable(tables)
  → for_each(current_table)
      → db_query(SELECT * FROM {{current_table}})
      → custom_python(清洗逻辑)
      → target_write(写入目标表)
      → wait(0.1s, 避免 CPU 过载)
```

### 工作流 JSON

```json
{
  "nodes": [
    {
      "id": "n1",
      "name": "设置表名列表",
      "type": "set_variable",
      "parameters": {
        "var_name": "tables",
        "var_value": "[\"dat_day\", \"dat_60mins\", \"dat_30mins\"]",
        "value_type": "json"
      }
    },
    {
      "id": "n2",
      "name": "遍历表",
      "type": "for_each",
      "parameters": {
        "items": "{{tables}}",
        "item_var": "current_table",
        "index_var": "table_index",
        "max_iterations": 10
      }
    },
    {
      "id": "n3",
      "name": "查询当前表",
      "type": "db_query",
      "parameters": {
        "db_type": "duckdb",
        "db_path": "C:/duckdb/quantifydata.duckdb",
        "sql": "SELECT * FROM {{current_table}} LIMIT 1000"
      }
    },
    {
      "id": "n4",
      "name": "数据清洗",
      "type": "custom_python",
      "parameters": {
        "code": "def process(df):\n    import pandas as pd\n    # 示例：删除空值\n    df = df.dropna()\n    return df"
      }
    },
    {
      "id": "n5",
      "name": "写入目标表",
      "type": "target_write",
      "parameters": {
        "target_type": "duckdb",
        "target_config": "{\"db_path\": \"C:/duckdb/output.duckdb\"}",
        "target_table": "cleaned_{{current_table}}",
        "on_duplicate": "replace"
      }
    },
    {
      "id": "n6",
      "name": "等待 0.1 秒",
      "type": "wait",
      "parameters": {
        "seconds": 0.1,
        "mode": "delay"
      }
    }
  ],
  "connections": {
    "n1": ["n2"],
    "n2": ["n3"],
    "n3": ["n4"],
    "n4": ["n5"],
    "n5": ["n6"]
  }
}
```

### 执行结果

工作流会依次处理 3 张表：
1. `dat_day` → `cleaned_dat_day`
2. `dat_60mins` → `cleaned_dat_60mins`
3. `dat_30mins` → `cleaned_dat_30mins`

每次处理间隔 0.1 秒，避免 CPU 过载。

---

## 附录：节点参数速查表

| 节点 | 参数 | 类型 | 必填 | 默认值 |
|---|---|---|---|---|
| **set_variable** | var_name | text | 是 | - |
| | var_value | textarea | 是 | - |
| | value_type | select | 否 | string |
| **wait** | seconds | number | 否 | 1 |
| | mode | select | 否 | delay |
| | target_timestamp | text | 否 | - |
| **for_each** | items | textarea | 是 | - |
| | item_var | text | 否 | current_item |
| | index_var | text | 否 | item_index |
| | max_iterations | number | 否 | 1000 |

---

## 常见问题

### Q: for_each 嵌套怎么实现？

A: 在 for_each 的下游子图里再放一个 for_each 节点：

```
for_each(tables)
  → for_each(codes)
      → custom_python(处理单个 code)
```

### Q: 如何在 for_each 中累加变量？

A: 用 `set_variable` 的 `expression` 模式：

```
for_each 下游 → set_variable(
  var_name: total_rows,
  var_value: context.get("total_rows", 0) + len(df),
  value_type: expression
)
```

### Q: for_each 的性能如何？

A: `for_each` 是串行执行，每次循环都会递归调用引擎。对于大数据量，建议：
- 单项数据量不要太大（< 100 万行）
- 在循环内部做 I/O（写入数据库），而不是返回 DataFrame
- 用 `wait` 节点控制节奏，避免 CPU 过载

---

## 更新日志

### 2026-08-09
- 初始版本：set_variable、wait、for_each 三个节点
- 工作流引擎新增 workflow_context 支持
