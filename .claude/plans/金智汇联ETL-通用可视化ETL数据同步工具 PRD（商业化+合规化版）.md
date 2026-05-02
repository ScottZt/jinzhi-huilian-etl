# 通用可视化ETL数据同步工具 PRD（商业化\+合规化版）

\# 一、文档说明

\#\# 1\.1 文档目的

明确通用可视化ETL数据同步工具的产品定位、核心功能、商业化模式、合规边界，为代码落地提供清晰需求规范，确保产品可商业化售卖（License模式）、完全合规（无侵权、无监管风险），同时适配量化用户等细分场景的使用需求，重点降低用户自定义脚本编写门槛，解决用户“不会写脚本”的核心痛点。

\#\# 1\.2 核心原则

\- 商业化：以License授权为核心变现模式，分层设计免费/付费功能，兼顾引流与盈利，降低售后成本，同时通过降低用户门槛提升转化率。

\- 合规化：去数据源绑定，不内置任何私有协议、SDK、密钥，彻底切割与金融数据源（通达信、CTP、QMT、Tushare等）的法律关联，责任边界清晰；内置SDK/API及大模型功能均不涉及第三方敏感内容。

\- 可落地：功能设计贴合技术实现逻辑，明确“开发者实现范围”与“用户自主操作范围”，便于Claude code快速落地开发，重点优化脚本生成相关功能的可实现性。

\- 通用性：聚焦ETL核心能力（连接、调度、清洗、入库），适配多场景，量化场景仅作为用户自定义场景之一，不绑定任何细分赛道；同时通过内置能力降低全场景用户的使用门槛。

\#\# 1\.3 目标用户

\- 核心用户：个人量化交易者、小量化团队（需同步行情数据至本地数据库，无专业脚本编写能力）。

\- 扩展用户：开发者、小工厂运维、个人站长、自媒体人（需各类数据同步、归集场景，希望简化脚本编写流程）。

\# 二、产品定位

\#\# 2\.1 产品名称

通用可视化ETL数据同步工具（暂命名，可后续迭代优化）

\#\# 2\.2 产品定位

跨平台（Windows\+Mac）桌面端通用ETL工具，提供可视化工作流、通用数据连接、数据清洗、调度入库、容错监控能力，核心优化脚本编写体验——内置工具专属SDK/API及轻量化大模型，支持用户通过自然语言指令，让大模型自动生成自定义脚本，无需用户手动编写复杂代码；支持用户自定义数据源连接、自定义抽取逻辑、自定义同步规则，不绑定任何第三方私有数据源，仅作为中立的数据处理载体，供用户按需适配各类数据同步场景（含量化数据同步）。

\#\# 2\.3 核心价值

\- 合规安全：用户自主对接数据源，开发者不触碰任何敏感协议/数据，规避侵权、监管风险；内置SDK/API及大模型仅提供脚本生成能力，不涉及第三方数据源核心逻辑。

\- 易用高效：可视化拖拽操作\+大模型自动生成脚本，彻底降低ETL使用门槛，解决用户“不会写脚本”的痛点；支持大数据量同步、断点续传，适配量化场景高频需求。

\- 灵活通用：支持自定义脚本、多类型数据源/入库目标，适配多行业数据同步场景，可长期迭代升级；内置SDK/API支持用户灵活扩展，大模型可适配不同场景的脚本生成需求。

\- 商业可控：闭源封装\+License授权，保护源码，实现稳定变现，同时降低售后维护成本；降低用户门槛可提升付费转化率及用户留存。

\# 三、商业化设计（核心落地重点）

\#\# 3\.1 变现模式

核心：免费基础版（引流）\+ 商业License授权版（盈利），配套增值服务（提升客单价）；其中内置SDK/API、大模型脚本生成功能作为核心增值点，区分免费/付费权限。

\#\# 3\.2 版本分层（功能边界清晰，便于代码落地）

\| 版本类型 \| 核心功能 \| 授权方式 \| 定位 \|

\| \-\-\- \| \-\-\- \| \-\-\- \| \-\-\- \|

\| 免费基础版 \| 1\. 基础可视化工作流（单工作流）；2\. 通用数据库连接（MySQL、SQLite）；3\. 基础文件读取（CSV、TXT）；4\. 简单数据清洗（去重、空值处理）；5\. 基础定时调度（每日/ hourly）；6\. 基础日志记录；7\. 单任务运行，无并发；8\. 基础自定义Python脚本节点（仅支持简单代码，无高级权限）；9\. 内置基础SDK/API（仅开放基础数据流转、入库相关接口，无脚本生成能力）；10\. 大模型脚本生成（仅支持基础场景，每日限3次，无自定义优化能力）。 \| 永久免费，无License，无功能使用时长限制 \| 引流获客，满足轻度数据同步需求，培养用户习惯，展示核心便捷功能 \|

\| 付费License版（个人版） \| 包含免费版全部功能，新增：1\. 多工作流并发（≤5个）；2\. 高级数据库连接（DuckDB、PG）；3\. 二进制文件读取支持；4\. 通用HTTP接口连接（支持自定义Header、Token）；5\. 高级数据清洗（字段转换、哈希校验、差异比对）；6\. 断点续传、失败自动重试、事务保障；7\. 高级脚本沙箱（支持第三方库导入，无代码限制）；8\. 大数据量优化（分块入库、缓存加速）；9\. 后台驻留运行；10\. 版本更新权限；11\. 内置完整SDK/API（开放全部数据处理、调度、脚本生成相关接口，支持用户灵活调用）；12\. 大模型脚本生成（无次数限制，支持量化、产业等多场景脚本生成，可根据用户需求优化脚本）。 \| License授权（机器码绑定），支持：月卡（69元）、年卡（129元）、永久授权（199元） \| 核心盈利，满足个人量化用户、开发者高频使用需求，解决“不会写脚本”的核心痛点 \|

\| 付费License版（专业版） \| 包含个人版全部功能，新增：1\. 多工作流并发（无上限）；2\. 分布式任务调度；3\. 批量任务管理；4\. 高级监控告警（邮件/本地弹窗）；5\. 数据备份与恢复；6\. 专属技术支持（一对一调试）；7\. 量化专用工作流模板导入/导出；8\. 内置SDK/API定制化支持（可根据用户需求扩展接口功能）；9\. 大模型脚本生成（支持批量生成、脚本批量优化、自定义脚本模板训练）。 \| License授权（多设备绑定，≤3台），支持：年卡（599元）、永久授权（999元） \| 高客单价盈利，满足小团队、企业级轻度数据同步需求，提供更灵活的扩展能力 \|

\#\# 3\.3 License授权机制（技术落地要求）

\- 授权核心：基于设备机器码绑定，实现“一机一授权”（个人版）、“多机绑定”（专业版）。

\- 激活方式：支持在线激活（轻量联网校验，无隐私收集）、离线授权（生成授权文件，用户手动导入）。

\- 防盗版：代码闭源加壳封装，禁止破解、二次分发、转售授权，License过期后自动限制付费功能使用（保留免费版功能）；内置SDK/API及大模型功能需绑定License授权，未授权用户无法使用高级权限。

\- 售后：授权可转移（设备更换时，支持手动解绑旧设备、绑定新设备，每月限1次）；提供SDK/API使用文档、大模型脚本生成教程。

\#\# 3\.4 增值服务（辅助变现，提升收益）

\- 量化专用模板包：包含Tushare、CTP、通达信本地文件解析的脚本模板、工作流模板，售价99元/份（终身更新）；可配合大模型快速优化适配用户需求。

\- 一对一调试服务：针对用户自定义数据源对接、脚本编写、SDK/API调用、工作流配置的调试，199元/次（30分钟内）。

\- 专属社群：付费用户社群，提供问题答疑、模板分享、版本更新通知、SDK/API使用交流、大模型脚本优化技巧，99元/年。

\# 四、合规化设计（红线不可碰，代码落地必遵循）

\#\# 4\.1 核心合规底线（开发者必须严格遵循）

\- 不内置任何第三方私有协议、SDK、密钥：禁止封装mootdx、pytdx、CTP SDK、QMT组件、Tushare SDK，不预装任何与金融数据源相关的依赖；内置SDK/API仅为工具自身功能接口，不涉及任何第三方数据源逻辑。

\- 不提供任何现成数据源连接方案：不内置通达信、CTP、QMT、Tushare等数据源的对接逻辑、接口地址、配置参数；大模型脚本生成仅提供“代码模板”，数据源相关的接口、Token、密钥仍需用户自行填写。

\- 不存储、不分发、不代理任何数据：软件仅负责数据流转、处理、入库，不存储用户数据源账号、Token、密钥，不缓存原始数据，不向第三方传输数据；大模型不存储用户生成的脚本及数据源相关信息，仅临时用于代码生成。

\- 不涉及任何金融相关操作：软件仅做数据同步，不做行情分发、交易下单、荐股、理财引流，不触碰任何金融监管红线；大模型脚本生成仅支持数据同步相关代码，禁止生成交易、荐股等违规代码。

\- 明确责任划分：通过用户协议、免责声明，明确用户对自身对接的数据源、账号权限、数据版权、合规使用承担全部责任，与开发者无关联；用户通过大模型生成的脚本，其合规性由用户自行审核、承担责任。

\#\# 4\.2 软件内合规文案（代码落地需嵌入）

\#\#\# 4\.2\.1 免责声明（关于页、安装协议必须包含）

1\. 本软件为通用数据处理ETL工具，仅提供数据流转、调度、清洗、入库的基础能力及脚本生成辅助功能，不绑定任何第三方数据源，不提供任何数据本身。

2\. 所有用户自行对接的第三方数据源（含金融、产业、办公等各类数据）、账号权限、Token密钥、接口协议，均由用户自行获取、自行管理，用户需严格遵守对应数据源的用户协议与相关法律法规，承担全部合规责任。

3\. 本软件与通达信、各券商、期货交易所、Tushare等任何第三方数据源主体无任何合作、关联关系，不负责用户数据源的合规性、稳定性、可用性。

4\. 禁止用户使用本软件从事破解、逆向、绕过第三方数据源技术保护措施等违规违法操作，若用户因违规使用产生任何法律责任，均由用户自行承担，与软件开发者无关。

5\. 软件内置SDK/API仅为工具自身功能接口，不涉及任何第三方数据源核心逻辑；大模型仅提供脚本生成辅助能力，生成的脚本需用户自行审核合规性，因脚本违规使用产生的法律责任，由用户自行承担。

\#\# 4\.3 内置SDK/API及大模型合规要求

\- 内置SDK/API：仅开放工具自身的数据处理、工作流调度、脚本执行、数据入库等核心接口，不包含任何第三方数据源的对接逻辑，接口文档需明确标注“仅用于本工具功能扩展，不提供数据源对接能力”。

\- 大模型：轻量化内置，仅用于生成数据同步相关的Python脚本，禁止生成涉及破解、逆向、金融交易、违规引流等相关代码；不收集、不存储用户的脚本内容、数据源信息，生成的脚本仅保存在用户本地设备，可由用户自行删除。

\# 五、核心功能补充（内置SDK/API\+大模型脚本生成，代码落地重点）

\#\# 5\.1 内置SDK/API（工具专属，不涉及第三方）

\#\#\# 5\.1\.1 核心定位

为用户提供工具自身功能的调用接口，支持用户通过代码扩展工具能力，或配合大模型生成的脚本，实现数据源对接、数据处理、工作流调度等操作，无需用户从零编写全部代码，降低开发门槛。

\#\#\# 5\.1\.2 接口分类（代码落地需实现）

1\. 数据连接接口：用于调用工具内置的数据库连接、文件读取、HTTP接口连接能力，用户无需重复编写连接代码，仅需传入相关参数（如数据库地址、文件路径、HTTP Header等）。

2\. 数据处理接口：用于调用工具内置的清洗、去重、字段转换、分块处理等能力，支持用户通过脚本调用，简化数据处理逻辑编写。

3\. 工作流调度接口：用于调用工具的定时调度、断点续传、失败重试等能力，支持用户通过脚本配置工作流触发条件、执行逻辑。

4\. 脚本执行接口：用于承接大模型生成的脚本，或用户自定义脚本，实现脚本与工具核心功能的联动，确保脚本可正常运行。

\#\#\# 5\.1\.3 权限控制

\- 免费版：仅开放基础数据连接、简单数据处理接口，无脚本执行接口高级权限，无法调用断点续传、大数据量优化等付费功能接口。

\- 付费版（个人/专业）：开放全部接口，支持用户灵活调用，专业版可提供接口定制化扩展支持。

\#\# 5\.2 工具内大模型脚本生成功能

\#\#\# 5\.2\.1 核心定位

轻量化内置大模型，用户通过自然语言描述需求（如“对接Tushare获取日线数据，同步到本地DuckDB”“读取通达信本地\.day文件，转换为CSV格式”），大模型自动生成适配工具内置SDK/API的Python脚本，用户无需手动编写代码，仅需修改脚本中的数据源参数（如Token、文件路径等）即可使用。

\#\#\# 5\.2\.2 核心功能（代码落地需实现）

1\. 自然语言交互：提供简洁的输入框，用户输入需求描述（支持量化、产业等多场景），大模型快速解析并生成脚本。

2\. 脚本适配：生成的脚本需适配工具内置SDK/API，可直接在工具的脚本节点中运行，无需用户额外修改代码结构。

3\. 脚本优化：支持用户输入优化需求（如“优化脚本，实现增量同步”“增加数据校验逻辑”），大模型对生成的脚本进行调整。

4\. 脚本保存与导入：生成的脚本可保存至本地，也可直接导入工具的脚本节点，支持批量生成、批量导入。

5\. 权限控制：

\- 免费版：每日限3次脚本生成，仅支持基础场景（如简单文件读取、数据库入库），无脚本优化功能。

\- 付费版（个人）：无次数限制，支持量化等多场景脚本生成，支持脚本优化、自定义需求适配。

\- 付费版（专业）：支持批量生成脚本、批量优化，可根据用户常用场景训练自定义脚本模板，提升生成效率。

\#\#\# 5\.2\.3 合规限制（代码落地必遵循）

\- 禁止大模型生成涉及破解、逆向、绕过第三方技术保护措施的代码。

\- 禁止大模型生成涉及金融交易、荐股、理财引流等违规代码。

\- 生成的脚本中，不包含任何第三方数据源的Token、接口地址等敏感信息，需用户自行填写。

\- 大模型不收集、不存储用户的需求描述、生成的脚本及任何数据源相关信息，仅临时用于代码生成，生成完成后自动清除缓存。

\#\#\# 5\.2\.4 大模型脚本生成示例（代码落地参考，已优化兼容性）

\#\#\#\# 示例1：量化场景 \- Tushare日线数据同步至本地DuckDB（适配工具内置SDK）

\#\#\#\#\#  用户自然语言需求

“对接Tushare获取沪深A股日线数据，筛选近30天数据，进行空值清洗，然后同步到本地DuckDB数据库，表名命名为a\_share\_daily，实现增量同步（只同步新增数据）”

\#\#\#\#\#  大模型自动生成的Python脚本（适配工具内置SDK，优化兼容性，规避接口解析问题）

```python
# 导入工具内置SDK（无需用户额外安装，工具自带，兼容Python3.7+）
from etl_tool_sdk import DataConnector, DataCleaner, DuckDBHandler, IncrementSync
import time

# 1. 配置Tushare参数（用户需自行填写个人Token，工具不存储，规避敏感信息泄露）
tushare_token = "请填写个人Tushare Token"  # 提示用户自行替换，需提前在Tushare平台获取
start_date = (time.strftime("%Y%m%d", time.localtime(time.time() - 30*24*3600)))  # 兼容处理，自动计算近30天日期（避免相对时间解析异常）

# 2. 调用工具SDK的HTTP连接接口，对接Tushare获取数据（适配HTTP请求规范，增加异常捕获，规避接口解析失败问题）
try:
    tushare_connector = DataConnector.http_connector(
        url="https://api.tushare.pro",  # 用户自行填写Tushare接口地址，若解析失败需检查网络或接口地址有效性
        headers={"Authorization": f"token={tushare_token}"},
        method="POST",
        data={"api_name": "daily", "params": {"ts_code": "", "start_date": start_date, "end_date": ""}, "fields": "ts_code,trade_date,open,high,low,close,vol"}
    )
    tushare_data = tushare_connector.get_data()  # 调用SDK接口，自动获取并解析数据为DataFrame（兼容DataFrame格式，避免数据类型异常）
except Exception as e:
    # 集成工具日志接口，记录异常，便于用户排查（如接口解析失败、网络异常等）
    from etl_tool_sdk import LogHandler
    log_handler = LogHandler()
    log_handler.error(f"Tushare数据获取失败，错误信息：{str(e)}，请检查Token有效性、接口地址或网络连接")
    raise  # 抛出异常，中断任务，避免无效数据流转

# 3. 调用工具SDK的数据清洗接口，处理空值（兼容不同数据格式，避免字段不存在报错）
cleaner = DataCleaner()
required_fields = ["trade_date", "open", "close"]
# 先校验字段是否存在，避免清洗时报错
missing_fields = [field for field in required_fields if field not in tushare_data.columns]
if missing_fields:
    raise ValueError(f"数据缺少必要字段：{missing_fields}，请检查Tushare接口返回数据格式")
cleaned_data = cleaner.drop_null(tushare_data, fields=required_fields)  # 按指定字段删除空值

# 4. 调用工具SDK的DuckDB连接接口，连接本地数据库（兼容Windows/Mac路径格式，避免路径解析异常）
duckdb_handler = DuckDBHandler(db_path="请填写本地DuckDB文件路径（Windows示例：D:\\data\\stock.db，Mac示例：/Users/xxx/data/stock.db）")  # 提示用户适配系统填写路径

# 5. 调用工具SDK的增量同步接口，实现新增数据同步（兼容DuckDB表操作，避免表不存在、字段类型不匹配报错）
increment_sync = IncrementSync(
    data=cleaned_data,
    db_handler=duckdb_handler,
    table_name="a_share_daily",
    increment_field="trade_date"  # 按交易日期作为增量判断字段，需确保该字段为字符串/日期类型
)
increment_sync.sync()  # 执行增量同步，自动跳过已存在数据，自动创建不存在的表

# 6. 调用工具SDK的日志接口，记录同步结果（集成到工具全局日志，兼容不同系统日志输出）
from etl_tool_sdk import LogHandler
log_handler = LogHandler()
log_handler.info(f"近30天A股日线数据同步完成，同步新增数据{len(increment_sync.new_data)}条")

```

\#\#\#\#\#  脚本说明

1\.  脚本完全适配工具内置SDK，所有核心操作（数据连接、清洗、增量同步、日志）均调用SDK接口，无需用户从零编写，兼容Python3\.7及以上版本，可直接在工具脚本节点运行。

2\.  新增异常捕获逻辑，针对Tushare接口解析失败、网络异常、字段缺失等常见问题做兼容处理，同时提示用户排查方向，解决“网页解析失败”相关适配问题。

3\.  敏感信息（Tushare Token、DuckDB路径）均提示用户自行填写，工具不内置、不存储，符合合规要求；路径提示适配Windows/Mac双系统，避免路径解析异常。

4\.  增量同步、数据清洗等高级功能，仅付费版用户可正常调用，免费版用户调用会提示“需升级License”，权限控制逻辑兼容SDK权限校验接口。

\#\#\#\# 示例2：基础场景 \- 通达信本地\.day文件解析并导入CSV（适配工具内置SDK，优化兼容性）

\#\#\#\#\#  用户自然语言需求

“读取本地通达信安装目录下的日线文件（\.day格式），解析为结构化数据，转换为CSV格式保存到本地文件夹，同时过滤掉成交量为0的数据”

\#\#\#\#\#  大模型自动生成的Python脚本（适配工具内置SDK，兼容双系统）

```python
# 导入工具内置SDK（无需用户额外安装，工具自带，兼容Python3.7+）
from etl_tool_sdk import FileConnector, DataCleaner, CSVExporter
import os

# 1. 配置通达信.day文件路径（用户需自行填写，工具不内置任何通达信相关路径，适配双系统）
tdx_day_file_path = "请填写通达信.day文件路径（Windows示例：D:\\通达信\\T0002\\lday\\sh600000.day，Mac示例：/Users/xxx/通达信/T0002/lday/sh600000.day）"
output_csv_path = "请填写CSV输出路径（Windows示例：D:\\data\\tdx_daily.csv，Mac示例：/Users/xxx/data/tdx_daily.csv）"

# 2. 调用工具SDK的二进制文件读取接口，解析.day文件（仅提供解析能力，不涉及逆向破解，增加文件存在性校验）
if not os.path.exists(tdx_day_file_path):
    raise FileNotFoundError(f"通达信.day文件不存在，请检查路径是否正确：{tdx_day_file_path}")

file_connector = FileConnector.binary_file_connector(file_path=tdx_day_file_path)
tdx_data = file_connector.parse_tdx_day()  # SDK内置.day文件基础解析逻辑，不涉及通达信私有协议破解，兼容不同版本.day文件格式

# 3. 调用工具SDK的数据清洗接口，过滤成交量为0的数据（兼容数据类型，避免vol字段非数值类型报错）
cleaner = DataCleaner()
# 先转换vol字段为数值类型，避免过滤逻辑报错
tdx_data["vol"] = cleaner.convert_field_type(tdx_data, fields={"vol": "int"})["vol"]
cleaned_data = cleaner.filter_data(tdx_data, condition="vol > 0")  # 过滤成交量>0的数据

# 4. 调用工具SDK的CSV导出接口，保存解析后的数据（兼容双系统文件编码，避免中文乱码）
csv_exporter = CSVExporter(file_path=output_csv_path, encoding="utf-8-sig")  # utf-8-sig兼容Windows/Mac中文显示
csv_exporter.export(cleaned_data)

# 5. 记录同步日志（集成到工具全局日志，兼容不同系统日志输出）
from etl_tool_sdk import LogHandler
log_handler = LogHandler()
log_handler.info(f"通达信.day文件解析完成，过滤后数据{len(cleaned_data)}条，已保存至{output_csv_path}")

```

\#\#\#\#\#  脚本说明

1\.  脚本仅调用工具SDK的二进制文件解析接口，不内置通达信私有协议、不逆向破解，符合合规要求；新增文件存在性校验、字段类型转换，避免运行报错。

2\.  通达信文件路径、CSV输出路径均提示用户适配Windows/Mac双系统填写，避免路径解析异常；CSV导出采用utf\-8\-sig编码，解决双系统中文乱码问题，提升兼容性。

3\.  免费版用户可正常使用该脚本（基础文件解析、CSV导出为免费功能），无需升级License，兼容免费版SDK接口权限。

\#\# 5\.3 内置SDK核心接口示例（代码落地参考，已优化兼容性）

\#\#\# 5\.3\.1 接口通用说明

1\.  所有SDK接口均为工具专属，不涉及任何第三方数据源逻辑，仅封装工具自身核心能力，兼容Python3\.7及以上版本，适配Windows/Mac双系统。

2\.  接口调用需遵循License权限控制，免费版仅可调用基础接口，付费版可调用全部接口，权限校验逻辑统一，避免权限判断异常。

3\.  所有接口均提供异常捕获机制，调用失败时会返回标准化错误信息（如“接口调用权限不足”“文件路径不存在”“数据格式异常”），集成到工具全局日志，便于用户排查问题。

4\.  接口参数设计兼容常见数据格式，避免因参数类型、格式错误导致的调用失败，同时适配第三方库（如pandas、DuckDB）的常见版本，降低依赖冲突风险。

\#\#\# 5\.3\.2 核心接口示例（Python版，优化兼容性）

\#\#\#\# 1\. 数据连接接口（基础接口，免费版可调用，兼容双系统、多版本依赖）

```python
from etl_tool_sdk import DataConnector
import platform

# 1.1 数据库连接接口（MySQL），兼容不同MySQL版本（5.7+），增加连接超时处理
mysql_connector = DataConnector.db_connector(
    db_type="mysql",
    host="请填写数据库地址",
    port=3306,
    user="请填写数据库用户名",
    password="请填写数据库密码",
    db_name="请填写数据库名称",
    connect_timeout=30  # 增加连接超时，避免无限等待
)
# 测试连接，返回标准化结果，便于用户判断
connect_result = mysql_connector.test_connection()
if connect_result["status"] == "success":
    print("MySQL连接成功")
else:
    print(f"MySQL连接失败，错误信息：{connect_result['error_msg']}")
# 获取数据（返回DataFrame，兼容pandas1.0+版本）
mysql_data = mysql_connector.query_data(sql="select * from test_table limit 100")

# 1.2 基础文件连接接口（CSV/TXT），适配双系统路径、多编码格式
# 自动适配系统路径分隔符，避免Windows/Mac路径格式冲突
if platform.system() == "Windows":
    file_path = "D:\\data\\test.csv"
else:
    file_path = "/Users/xxx/data/test.csv"

file_connector = DataConnector.file_connector(
    file_path=file_path,
    file_type="csv",  # 支持csv、txt，自动识别文件格式
    encoding="auto"  # 自动识别编码，避免中文乱码（兼容utf-8、gbk、gb2312等）
)
# 读取文件数据，返回DataFrame，支持大文件分块读取（避免内存溢出）
file_data = file_connector.read_file(chunk_size=None)  # chunk_size=None表示一次性读取，可根据文件大小调整

```

\#\#\#\# 2\. 数据处理接口（基础接口免费版可调用，高级接口需付费，兼容多数据格式）

```python
from etl_tool_sdk import DataCleaner
import pandas as pd

# 模拟用户数据（兼容pandas不同版本的DataFrame格式）
data = pd.DataFrame({
    "field1": [1, 2, None, 4, 4],
    "field2": ["a", "b", "c", None, "b"],
    "field3": [1.1, 2.2, 3.3, 4.4, 4.4]
})

cleaner = DataCleaner()

# 2.1 基础清洗接口（免费版可调用），兼容空值、重复值的不同表现形式
data = cleaner.drop_null(data, fields=["field1", "field2"])  # 删除指定字段空值，兼容None、NaN等空值格式
data = cleaner.remove_duplicate(data, fields=["field1"])  # 按指定字段去重，兼容不同数据类型的重复值
# 字段类型转换，自动处理转换失败的异常（如无法转换为int的字段，返回原始值并提示）
data = cleaner.convert_field_type(data, fields={"field1": "int", "field3": "float"})

# 2.2 高级清洗接口（付费版可调用），兼容大数据量处理，避免内存溢出
data = cleaner.hash_check(data, field="field1")  # 哈希校验，确保数据完整性，兼容字符串、数值类型
data = cleaner.split_field(data, field="field2", separator=",", new_fields=["field2_1", "field2_2"])  # 字段拆分，兼容无分隔符的场景（返回原字段）

```

\#\#\#\# 3\. 工作流调度接口（付费版可调用，兼容双系统后台运行）

```python
from etl_tool_sdk import WorkflowScheduler
import platform

# 初始化工作流调度器，兼容双系统后台驻留（Windows用task scheduler，Mac用launchd）
scheduler = WorkflowScheduler(workflow_id="workflow_001", background=True)  # background=True表示后台运行

# 定义同步任务函数（兼容工具SDK接口，可被调度器正常调用）
def sync_task(param1, param2):
    from etl_tool_sdk import DataConnector, LogHandler
    log_handler = LogHandler()
    try:
        # 模拟数据同步操作
        connector = DataConnector.file_connector(file_path=param1)
        data = connector.read_file()
        log_handler.info(f"任务执行成功，读取数据{len(data)}条，参数param2：{param2}")
        return {"status": "success", "data_count": len(data)}
    except Exception as e:
        log_handler.error(f"任务执行失败，错误信息：{str(e)}")
        return {"status": "fail", "error_msg": str(e)}

# 配置定时调度（每日盘后16:30执行），兼容不同系统的cron表达式解析
scheduler.set_cron(
    cron_expression="0 30 16 * * ?",  # cron表达式，每日16:30，兼容Windows/Mac调度器
    task_func=sync_task,  # 同步任务函数（用户自定义或大模型生成，需适配SDK接口）
    task_params={"param1": "请填写文件路径", "param2": "同步任务参数"}  # 任务参数，支持多种数据类型
)

# 配置断点续传（付费版核心功能），兼容任务中断后恢复，避免数据重复同步
scheduler.enable_breakpoint_resume(
    task_id="task_001",
    resume_field="sync_time",  # 按同步时间作为断点标识，需确保该字段存在于任务结果中
    resume_path="请填写断点文件保存路径"  # 适配双系统路径，自动保存断点信息
)

# 启动调度，兼容双系统后台运行，避免进程退出
scheduler.start()

```

\#\#\#\# 4\. 脚本执行接口（付费版可调用，沙箱环境兼容多脚本类型）

```python
from etl_tool_sdk import ScriptExecutor

# 初始化脚本执行器（沙箱环境，隔离用户脚本与工具核心代码，兼容不同Python脚本语法）
# sandbox=True开启沙箱，禁止用户脚本访问工具核心代码，提升安全性
executor = ScriptExecutor(sandbox=True, python_version="3.7+")  # 指定兼容的Python版本

# 执行大模型生成的脚本（脚本内容可从工具脚本节点获取，兼容SDK接口调用）
script_content = """
# 大模型生成的脚本内容（示例，兼容工具内置SDK）
from etl_tool_sdk import DataConnector, DuckDBHandler
try:
    connector = DataConnector.db_connector(db_type="duckdb", db_name="test.db")
    data = connector.query_data(sql="select * from a_share_daily limit 10")
    print(f"读取数据{len(data)}条")
except Exception as e:
    print(f"脚本执行异常：{str(e)}")
"""
# 执行脚本，返回标准化结果（兼容不同脚本执行状态，便于工具展示结果）
execute_result = executor.execute(script_content)
if execute_result["status"] == "success":
    print("脚本执行成功，同步数据条数：", execute_result.get("data_count", 0))
else:
    print("脚本执行失败，错误信息：", execute_result["error_msg"])

```

\#\#\# 5\.3\.3 SDK接口权限控制示例（代码落地需实现，兼容全版本License校验）

```python
from etl_tool_sdk import LicenseManager

# 初始化License管理器，兼容在线/离线授权校验，避免授权校验失败
license_manager = LicenseManager(offline_mode=False)  # offline_mode=False表示支持在线校验，True为离线模式

# 权限校验（工具启动时自动执行，兼容所有SDK接口，统一权限判断逻辑）
def check_sdk_permission(interface_name):
    try:
        # 获取当前License类型（免费/个人/专业），兼容不同授权方式（在线/离线）
        current_license = license_manager.get_license_type()
        # 基础接口（免费版可调用），兼容所有版本SDK
        basic_interfaces = ["db_connector", "file_connector", "drop_null", "remove_duplicate"]
        # 高级接口（付费版可调用），兼容个人版/专业版权限区分
        advanced_interfaces = ["hash_check", "breakpoint_resume", "script_executor", "increment_sync"]
        # 专业版专属接口，兼容专业版License校验
        pro_interfaces = ["batch_script_generate", "api_customize"]
        
        # 权限判断，逻辑清晰，避免权限判断异常
        if interface_name in basic_interfaces:
            return True, "权限正常"
        elif interface_name in advanced_interfaces and current_license in ["personal", "professional"]:
            return True, "权限正常"
        elif interface_name in pro_interfaces and current_license == "professional":
            return True, "权限正常"
        else:
            return False, f"当前License权限不足，需升级至{('付费版' if interface_name in advanced_interfaces else '专业版')}使用该功能"
    except Exception as e:
        # 授权校验异常处理（如License过期、授权文件损坏）
        return False, f"License校验异常：{str(e)}，请检查授权状态"

# 接口调用时校验权限，兼容所有SDK接口调用场景
permission, msg = check_sdk_permission("increment_sync")
if permission:
    # 执行增量同步操作，兼容SDK接口调用
    increment_sync.sync()
else:
    raise PermissionError(msg)

```

\#\#\# 5\.3\.4 兼容性补充说明（代码落地必看）

1\.  系统兼容性：所有SDK接口、脚本示例均适配Windows 10及以上、Mac OS 12及以上系统，避免系统相关的路径、进程、调度器兼容性问题。

2\.  依赖兼容性：SDK内置所需基础依赖（如pandas、DuckDB、requests等），无需用户额外安装，同时兼容这些依赖的常见版本（pandas1\.0\+、DuckDB0\.9\+、requests2\.20\+），降低依赖冲突风险。

3\.  接口兼容性：SDK接口参数设计采用默认值\+可选参数模式，后续版本迭代时可新增参数，不影响旧版本脚本、接口调用，保证向后兼容。

4\.  异常兼容性：所有接口、脚本均增加异常捕获逻辑，针对常见报错（如文件不存在、接口解析失败、权限不足、数据格式异常）返回标准化错误信息，便于用户排查，同时避免程序崩溃。

5\.  针对Tushare接口解析失败问题：脚本中已增加异常捕获和提示，用户需自行检查Tushare Token有效性、接口地址正确性及网络连接，工具不负责第三方接口的可用性，符合合规边界。

> （注：文档部分内容可能由 AI 生成）
