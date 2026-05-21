金智汇联 ETL — 前台页面全链路手动测试教程                                                                                                                                                             
                                                                                                                                                                                                        
  ▎ 核心链路：连接管理 → 数据源配置 → 表结构(DDL) → ETL工作流 → K线同步任务 → 数据流(Pipeline) → AI脚本生成 → 数据验证                                                                                  
  ▎                                                                                                                                                                                                     
  ▎ 操作方式：全程通过 http://127.0.0.1:8080 页面操作，浏览器 F12 控制台作为辅助观察                                                                                                                                                                                                                                                                                                                            
  ---                                                                                                                                                                                                   
  前置：启动服务
                                                                                                                                                                                                        
  cd backend                                                                                                                                                                                            
  uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload

  浏览器打开 http://127.0.0.1:8080，按 F12 → Console 保持打开，方便观察网络请求和日志。

  ▎ 提示：F12 → Network 面板也可以随时查看每个 API 的 request/response。

  ---
  第 1 步：连接管理（创建 DuckDB 目标连接）

  左侧导航 → 点击「连接管理」

  操作：

  1. 点击 + 新建连接 按钮
  2. 填写表单：
    - 名称：本地DuckDB
    - 类型：选择 DuckDB
    - 数据库路径：D:/data/test_etl.db（可按需修改）
  3. 点击 保存
  4. 列表中会出现新连接，点击 「测试」 按钮

  控制台观察：

  F12 → Network → 查看 POST /api/connections/ 的 response → 记录返回的 "id" 值

  期望结果：测试连接返回 ✅ 绿色提示 已连接 DuckDB (1.x.x)

  ▎ 记住这个连接 ID，后续步骤称为 CONN_ID

  ---
  第 2 步：数据源配置（添加 TDX 数据源）

  左侧导航 → 点击「数据源」

  操作：

  1. 点击 + 新建数据源
  2. 填写表单：
    - 名称：通达信本地日线
    - 类型：选择 TDX（通达信）
    - 数据目录：填写本机通达信 vipdoc 路径（如 D:/new_tdx64/vipdoc）
  3. 点击 保存
  4. 列表中点击 「测试」 按钮
  5. 测试成功后，点击 「预览」 按钮查看样例数据

  控制台观察：

  F12 → Network → 查看 POST /api/kline-sources/{id}/test 的 response
  F12 → Network → 查看 GET /api/kline-sources/{id}/preview 的 response

  期望结果：
  - 测试：✅ 找到 N 个通达信数据文件
  - 预览：能看到 K 线样例数据（columns 包含 datetime/open/high/low/close/volume/amount）

  ▎ 记住这个数据源 ID，后续称为 SOURCE_ID

  无 TDX 数据时的替代方案：

  如果本机没有通达信数据，改用 AkShare：
  - 类型选 AkShare
  - request_template 中选择 stock_zh_a_hist 模板
  - 预览股票代码填 000001

  ---
  第 3 步：表结构定义（DDL 生成并应用到目标库）

  左侧导航 → 点击「表结构」

  操作：

  1. 点击 + 新建表结构
  2. 填写表单：
    - 表名：stock_kline
    - 数据库类型：选择 DuckDB
  3. 添加字段（点击 + 添加字段）：

  ┌─────────────┬─────────────┬──────┬──────────┐
  │   字段名    │    类型     │ 可空 │   备注   │
  ├─────────────┼─────────────┼──────┼──────────┤
  │ stock_code  │ VARCHAR(20) │ 否   │ 股票代码 │
  ├─────────────┼─────────────┼──────┼──────────┤
  │ trade_time  │ DATETIME    │ 否   │ 交易时间 │
  ├─────────────┼─────────────┼──────┼──────────┤
  │ open_price  │ DOUBLE      │ 是   │ 开盘价   │
  ├─────────────┼─────────────┼──────┼──────────┤
  │ high_price  │ DOUBLE      │ 是   │ 最高价   │
  ├─────────────┼─────────────┼──────┼──────────┤
  │ low_price   │ DOUBLE      │ 是   │ 最低价   │
  ├─────────────┼─────────────┼──────┼──────────┤
  │ close_price │ DOUBLE      │ 是   │ 收盘价   │
  ├─────────────┼─────────────┼──────┼──────────┤
  │ volume      │ DOUBLE      │ 是   │ 成交量   │
  ├─────────────┼─────────────┼──────┼──────────┤
  │ amount      │ DOUBLE      │ 是   │ 成交额   │
  └─────────────┴─────────────┴──────┴──────────┘

  4. 添加索引（点击 + 添加索引）：
    - 索引名：idx_code_time
    - 字段：选择 stock_code + trade_time
    - 唯一：勾选 ✅
  5. 先点击 预览DDL 查看生成的 SQL
  6. 确认后点击 保存
  7. 保存后，在表结构列表中找到刚创建的 stock_kline，点击 「应用到数据库」
    - 选择连接：选第 1 步创建的 本地DuckDB
    - 冲突策略：选择 覆盖（已存在则重建）

  控制台观察：

  F12 → Network → 查看 POST /api/schemas/preview-ddl 返回的 DDL SQL
  F12 → Network → 查看 POST /api/schemas/apply 返回的 success 状态

  验证表已创建：

  回到「连接管理」→ 找到 本地DuckDB → 点击 「查看表」 按钮

  期望结果：表列表中能看到 stock_kline

  ▎ 记住这个 Schema ID，后续称为 SCHEMA_ID

  ---
  第 4 步：ETL 工作流（创建 + 验证执行）

  左侧导航 → 点击「ETL工作流」

  操作 A：创建自定义工作流

  1. 点击 + 新建工作流
  2. 填写：
    - 名称：K线加工：30分钟 + MA + MACD
    - 描述：分钟线重采样到30分钟，计算MA5/MA10，再计算MACD
  3. 在编辑器中添加节点：
    - 节点 1：类型选 resample（重采样）
        - 参数：rule=30min, time_column=dt, group_column=code
    - 节点 2：类型选 ma（移动平均）
        - 参数：windows=5,10, source_column=close
    - 节点 3：类型选 macd（MACD指标）
        - 参数：fast=12, slow=26, signal=9, source_column=close
  4. 连接节点：节点1 → 节点2 → 节点3
  5. 点击 保存

  操作 B：运行预制工作流验证引擎

  1. 点击 导入预制工作流 按钮（如有）
  2. 或在列表中点击某个预制工作流的 「预览」 按钮

  操作 C：查看可用节点

  1. 点击 「查看节点列表」 按钮

  控制台观察：

  F12 → Network → 查看 POST /api/workflows/ 的创建 response，记录返回的 "id"
  F12 → Network → 查看 POST /api/workflows/{id}/preview 的执行结果
  F12 → Network → 查看 GET /api/workflows/nodes 返回的节点类型列表

  期望结果：
  - 预览返回 rows > 0，timings 显示每个节点耗时
  - 节点列表包含 resample、ma、macd、filter、sort、group_by 等

  ▎ 记住这个工作流 ID，后续称为 WF_ID

  ---
  第 5 步：K 线同步任务（创建 + 执行）

  左侧导航 → 点击「导入任务」（或在「总览」页快速入口进入）

  操作：

  1. 点击 + 新建同步任务
  2. 填写表单：
    - 任务名称：日线同步到DuckDB
    - 数据源连接：选择第 2 步创建的 通达信本地日线
    - 目标连接：选择第 1 步创建的 本地DuckDB
    - 目标表名：stock_kline
    - 股票代码：000001
    - K线周期：选择 D（日线）
    - 时间模式：回看模式，回看天数 30
    - 仅交易时段：取消勾选（日线不需要）
  3. 配置字段映射（展开「字段映射」区域）：

  ┌──────────┬─────────────┐
  │  源字段  │  目标字段   │
  ├──────────┼─────────────┤
  │ code     │ stock_code  │
  ├──────────┼─────────────┤
  │ datetime │ trade_time  │
  ├──────────┼─────────────┤
  │ open     │ open_price  │
  ├──────────┼─────────────┤
  │ high     │ high_price  │
  ├──────────┼─────────────┤
  │ low      │ low_price   │
  ├──────────┼─────────────┤
  │ close    │ close_price │
  ├──────────┼─────────────┤
  │ volume   │ volume      │
  ├──────────┼─────────────┤
  │ amount   │ amount      │
  └──────────┴─────────────┘

  4. 选择关联工作流（可选）：选择第 4 步创建的 K线加工：30分钟 + MA + MACD
  5. 重复策略：忽略（已存在则跳过）
  6. 点击 保存
  7. 列表中先点击 「Dry-run 预览」 确认有数据
  8. 预览正常后，点击 「执行」 按钮

  控制台观察：

  F12 → Network → 查看 POST /api/kline-sync-tasks/ 的创建 response，记录 "id"
  F12 → Network → 查看 POST /api/kline-sync-tasks/{id}/dry-run → rows_fetched > 0
  F12 → Network → 查看 POST /api/kline-sync-tasks/{id}/run → 加入队列
  F12 → Console → 等待几秒后刷新任务列表，查看执行记录

  期望结果：
  - Dry-run：返回 rows_fetched > 0，preview 有数据
  - 执行记录：status: success，rows_written > 0

  ▎ 记住这个任务 ID，后续称为 TASK_ID

  ---
  第 6 步：数据流 Pipeline（完整编排执行）

  左侧导航 → 点击「数据流 (Pipeline)」

  操作：

  1. 点击 + 新建数据流
  2. 填写：
    - 名称：全链路：TDX → 工作流 → DuckDB
    - 描述：从TDX拉取数据，经工作流加工，写入DuckDB
  3. 数据源配置：
    - 添加数据源：选择 通达信本地日线
    - 股票代码：000001
    - K线周期：D
    - 回看天数：15
  4. 目标配置：
    - 目标连接：选择 本地DuckDB
    - 目标表：stock_kline
  5. 工作流：选择第 4 步创建的 K线加工：30分钟 + MA + MACD
  6. 字段映射：同第 5 步的映射表
  7. 重复策略：忽略
  8. 定时表达式：留空（手动触发）
  9. 点击 保存
  10. 保存后点击 「预检查」 按钮
  11. 预检查通过后点击 「预览」 查看加工后数据
  12. 最后点击 「执行」

  控制台观察：

  F12 → Network → 查看 POST /api/pipelines/ 的创建 response，记录 "id"
  F12 → Network → 查看 POST /api/pipelines/{id}/precheck → ok: true
  F12 → Network → 查看 POST /api/pipelines/{id}/preview → 返回预览数据
  F12 → Network → 查看 POST /api/pipelines/{id}/run → 加入队列

  等待 10-20 秒后，刷新数据流页面，查看运行记录列表。

  期望结果：
  - 预检查：✅ ok: true
  - 预览：rows > 0，columns 包含加工后的字段
  - 运行记录：status: success，rows_written > 0

  ▎ 记住这个 Pipeline ID，后续称为 PIPELINE_ID

  ---
  第 7 步：数据验证（通过控制台确认写入结果）

  方法 A：页面查看

  左侧导航 → 点击「连接管理」→ 找到 本地DuckDB → 点击 「查看表」 → 点击 stock_kline 旁的 「查看字段」

  方法 B：F12 控制台执行（辅助验证）

  按 F12 → Console，粘贴执行：

  // 查看目标表中已有数据行数（通过连接 API）
  fetch('/api/connections/CONN_ID/tables')
    .then(r => r.json())
    .then(d => console.log('表列表:', d.tables));

  将 CONN_ID 替换为实际的连接 ID。

  方法 C：Python 本地验证（辅助）

  如果安装了 Python，在终端执行：

  python -c "
  import duckdb
  conn = duckdb.connect('D:/data/test_etl.db')
  print('表列表:', conn.execute('SHOW TABLES').fetchall())
  print('行数:', conn.execute('SELECT COUNT(*) FROM stock_kline').fetchone())
  print('前5行:')
  print(conn.execute('SELECT * FROM stock_kline LIMIT 5').fetchdf())
  conn.close()
  "

  期望结果：stock_kline 表中有数据，包含 stock_code、trade_time、价格字段等。

  ---
  第 8 步：AI 脚本生成

  左侧导航 → 点击「AI脚本生成」

  操作 A：查看 AI 状态

  1. 进入页面后，观察顶部的 AI 状态面板
  2. 确认 LLM 配置状态（未配置时使用模板回退模式）

  操作 B：生成脚本

  1. 在输入框中输入需求描述：
  将CSV文件数据同步到SQLite数据库，按日期字段过滤
  2. 点击 生成脚本
  3. 查看返回的 Python 脚本

  操作 C：生成 TDX 同步脚本

  1. 修改需求描述：
  从通达信读取日线数据，清洗后写入DuckDB数据库
  2. 点击 生成脚本
  3. 查看生成的脚本，确认使用了 etl_tool_sdk 和相关 API

  控制台观察：

  F12 → Network → 查看 POST /api/ai-script/generate 的 request/response
  F12 → Network → 查看 GET /api/ai-script/status 返回的配置状态

  期望结果：
  - 状态页显示 tier: free，remaining_today 有剩余次数
  - 生成返回 success: true，包含完整的 Python 脚本

  ---
  第 9 步：总览验证（检查全链路产物）

  左侧导航 → 点击「总览」

  操作：

  1. 查看 统计卡片：连接数、数据源数、工作流数、任务数、Pipeline 数
  2. 查看 最近同步记录：确认有成功的同步记录
  3. 查看 最近数据流执行记录

  控制台观察：

  F12 → Network → 查看 GET /api/kline-sync-tasks/records → 确认有成功记录
  F12 → Network → 查看 GET /api/pipelines/runs/all → 确认有成功记录

  期望结果：所有统计卡片数值 > 0，同步记录和 Pipeline 记录显示绿色成功状态。

  ---
  变量汇总表

  ┌─────────────┬─────────────────┬──────────────┐
  │    变量     │      含义       │ 在哪一步创建 │
  ├─────────────┼─────────────────┼──────────────┤
  │ CONN_ID     │ DuckDB 连接 ID  │ 第 1 步      │
  ├─────────────┼─────────────────┼──────────────┤
  │ SOURCE_ID   │ TDX 数据源 ID   │ 第 2 步      │
  ├─────────────┼─────────────────┼──────────────┤
  │ SCHEMA_ID   │ 表结构定义 ID   │ 第 3 步      │
  ├─────────────┼─────────────────┼──────────────┤
  │ WF_ID       │ 工作流 ID       │ 第 4 步      │
  ├─────────────┼─────────────────┼──────────────┤
  │ TASK_ID     │ K 线同步任务 ID │ 第 5 步      │
  ├─────────────┼─────────────────┼──────────────┤
  │ PIPELINE_ID │ 数据流 ID       │ 第 6 步      │
  └─────────────┴─────────────────┴──────────────┘

  ▎ 每次创建资源后，响应中会返回 id 字段，请记录这些 ID（可在 F12 → Network 中查看），后续步骤需要引用。

  ---
  控制台常用调试命令

  在 F12 Console 中可快速查看系统状态：

  // 查看所有连接
  fetch('/api/connections/').then(r=>r.json()).then(d=>console.table(d))

  // 查看所有数据源
  fetch('/api/kline-sources/').then(r=>r.json()).then(d=>console.table(d))

  // 查看所有工作流
  fetch('/api/workflows/').then(r=>r.json()).then(d=>console.table(d))

  // 查看所有同步任务
  fetch('/api/kline-sync-tasks/').then(r=>r.json()).then(d=>console.table(d))

  // 查看所有数据流
  fetch('/api/pipelines/').then(r=>r.json()).then(d=>console.table(d))

  // 查看最近同步记录
  fetch('/api/kline-sync-tasks/records?limit=5').then(r=>r.json()).then(d=>console.table(d))

  // 查看最近数据流执行记录
  fetch('/api/pipelines/runs/all?limit=5').then(r=>r.json()).then(d=>console.table(d))

  // 查看 AI 状态
  fetch('/api/ai-script/status').then(r=>r.json()).then(d=>console.log(d))