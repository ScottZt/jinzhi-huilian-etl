"""
AI 脚本生成器核心 — 合规设计：仅用于生成数据同步相关 Python 脚本，不涉及任何第三方数据源。
"""
import re
import json
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# 合规禁止词表
BANNED_PATTERNS = [
    r"交易", r"下单", r"买入", r"卖出", r"开仓", r"平仓",
    r"期货.*开", r"cta", r"掘金", r"米筐", r"优矿",
    r"破解", r"逆向", r"绕过.*验证", r"脱壳",
    r"荐股", r"选股.*策略", r"量化.*实盘",
    r"selenium.*爬", r"requests.*反爬",
    r"webdriver", r"scrape.*动态",
]

COMPLIANCE_WARNING = (
    "⚠️ 合规提示：生成的脚本仅供数据同步使用，不得用于交易、破解、逆向等违规场景。"
    "数据源的 API 地址、Token、密钥由用户自行填写，用户承担全部合规责任。"
)


class AiScriptGenerator:
    """
    AI 脚本生成器 — 将自然语言需求转换为适配 etl_tool_sdk 的 Python 脚本。

    合规说明：仅生成数据同步相关脚本，禁止生成交易、破解、逆向等违规代码。
    不收集、不存储用户的脚本内容或数据源信息。

    使用示例：
        gen = AiScriptGenerator()
        script, err = gen.generate(
            prompt="读取CSV文件，按price字段过滤大于100的行，写入SQLite数据库",
            tier="personal",
        )
        print(script)
    """

    def __init__(self):
        self._llm = None
        self._llm_config = None

    def _load_llm_config(self) -> Dict[str, Any]:
        """从 metadata 表加载 LLM 配置。"""
        try:
            from app.persistence import sqlite_repo
            cfg_json = sqlite_repo.get_metadata("ai_llm_config")
            if cfg_json:
                return json.loads(cfg_json)
        except Exception:
            pass
        return {}

    def _save_llm_config(self, config: Dict[str, Any]):
        """保存 LLM 配置到 metadata 表。"""
        try:
            from app.persistence import sqlite_repo
            sqlite_repo.save_metadata("ai_llm_config", json.dumps(config))
        except Exception as e:
            logger.error(f"Failed to save LLM config: {e}")

    def configure_llm(self, endpoint: str, api_key: str, model: str, **kwargs):
        """
        配置 LLM（OpenAI 兼容接口）。

        Args:
            endpoint: API 地址（如 "https://api.openai.com/v1"）
            api_key: API 密钥
            model: 模型名称（如 "gpt-4o-mini"）
        """
        config = {
            "endpoint": endpoint.rstrip("/"),
            "api_key": api_key,
            "model": model,
            **kwargs,
        }
        self._llm_config = config
        self._save_llm_config(config)

    def load_llm_config(self) -> Optional[Dict[str, Any]]:
        """加载已保存的 LLM 配置。"""
        return self._load_llm_config()

    def generate(
        self,
        prompt: str,
        tier: str = "free",
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Optional[str], int]:
        """
        生成脚本。

        Args:
            prompt: 自然语言需求描述
            tier: 授权等级（free/personal/professional）
            context: 额外上下文（如数据源类型、目标表名等）
        Returns:
            (script, error_message, remaining_count)
        """
        from app.core import license_manager as lm

        # 检查每日生成次数
        if tier == "free":
            remaining = lm.get_ai_daily_remaining()
            if remaining <= 0:
                return None, "免费版今日生成次数已用完（每日限3次）。请明日再试或升级至付费版。", 0
        else:
            remaining = -1  # 付费版无限制

        # 合规检查
        check_pass, check_msg = self._compliance_check(prompt)
        if not check_pass:
            return None, f"合规检查未通过：{check_msg}\n{COMPLIANCE_WARNING}", remaining

        # 生成脚本
        script, err = self._do_generate(prompt, tier, context or {})
        if err:
            return None, err, remaining

        # 增加计数
        if tier == "free":
            new_remaining = lm.increment_ai_count()
            remaining = new_remaining

        return script, None, remaining

    def _compliance_check(self, prompt: str) -> Tuple[bool, str]:
        """合规检查：禁止词过滤。"""
        prompt_lower = prompt.lower()
        for pattern in BANNED_PATTERNS:
            if re.search(pattern, prompt_lower):
                return False, f"检测到禁止词：{pattern}"
        return True, ""

    def _do_generate(
        self,
        prompt: str,
        tier: str,
        context: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        """实际执行脚本生成。优先用 LLM，回退到模板引擎。"""
        config = self._load_llm_config()

        if config and config.get("endpoint") and config.get("api_key"):
            return self._generate_via_llm(prompt, tier, context, config)
        else:
            return self._generate_via_template(prompt, tier, context)

    def _generate_via_llm(
        self,
        prompt: str,
        tier: str,
        context: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        """通过 LLM API 生成脚本。"""
        try:
            import requests
        except ImportError:
            return None, "requests 库不可用，无法调用 LLM API"

        system_prompt = self._build_system_prompt(tier)
        user_prompt = self._build_user_prompt(prompt, tier, context)

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        body = {
            "model": config.get("model", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
        }

        endpoint = config["endpoint"].rstrip("/")
        if "/chat/completions" not in endpoint:
            endpoint += "/chat/completions"

        try:
            resp = requests.post(
                endpoint, headers=headers, json=body, timeout=60,
            )
            if resp.status_code != 200:
                return None, f"LLM API 调用失败（{resp.status_code}）：{resp.text[:200]}"

            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # 提取代码块
            script = self._extract_code(content)
            if not script:
                return None, "LLM 返回内容中未找到有效脚本代码"

            return script, None

        except requests.exceptions.Timeout:
            return None, "LLM API 调用超时，请检查网络连接"
        except requests.exceptions.ConnectionError:
            return None, "LLM API 连接失败，请检查 endpoint 配置"
        except Exception as e:
            return None, f"LLM 调用异常：{str(e)}"

    def _build_system_prompt(self, tier: str) -> str:
        return f"""你是一个数据同步脚本生成助手，为金智汇联ETL工具生成Python脚本。

你的任务是：根据用户需求，生成使用 etl_tool_sdk 的 Python 脚本。

合规要求：
1. 仅生成数据同步相关脚本（读取、清洗、转换、入库）
2. 禁止生成交易、下单、荐股、破解、逆向等违规代码
3. 不内置任何第三方数据源 SDK，数据源参数由用户自行填写
4. 脚本中的敏感信息（IP、Token、密钥等）用占位符标注

输出格式：直接输出 Python 代码，用 ```python ... ``` 包裹。
生成的脚本必须可执行，使用 etl_tool_sdk 库。

脚本模板框架：
```python
# 金智汇联ETL AI 生成脚本
# 合规说明：脚本由大模型辅助生成，用户需自行审核合规性、自行填写数据源参数
from etl_tool_sdk import init_sdk, DataConnector, DataCleaner, ScriptExecutor, LogHandler

# 初始化 SDK
init_sdk()

# 连接数据源（用户自行配置）
conn = DataConnector()

# 读取数据（示例）
# df = conn.read_csv("your_file.csv")
# df = conn.read_from_mysql(host="localhost", port=3306, user="root", password="xxx", database="mydb", query="SELECT * FROM table")

# 数据清洗
cleaner = DataCleaner()

# 处理逻辑（根据需求生成）

# 写入目标
# conn.write_to_sqlite(df, "output.db", "table_name")

# 日志记录
LogHandler.info("ETL脚本执行完成", extra={{"rows": len(df)}})
```

根据用户需求填充具体逻辑。"""

    def _build_user_prompt(
        self,
        prompt: str,
        tier: str,
        context: Dict[str, Any],
    ) -> str:
        ctx_parts = []
        if context.get("source_type"):
            ctx_parts.append(f"数据源类型：{context['source_type']}")
        if context.get("target_type"):
            ctx_parts.append(f"目标类型：{context['target_type']}")
        if context.get("table_name"):
            ctx_parts.append(f"目标表名：{context['table_name']}")

        context_str = "\n".join(ctx_parts) if ctx_parts else "通用数据同步场景"

        return f"""需求：{prompt}

上下文：{context_str}

请生成完整可执行的 Python 脚本，适配 etl_tool_sdk。"""

    def _extract_code(self, content: str) -> Optional[str]:
        """从 LLM 输出中提取 Python 代码块。"""
        match = re.search(r"```python\s*(.*?)```", content, re.DOTALL)
        if match:
            return match.group(1).strip()

        match = re.search(r"```\s*(.*?)```", content, re.DOTALL)
        if match:
            code = match.group(1).strip()
            if code.startswith("python"):
                code = code[6:].strip()
            return code

        return None

    def _generate_via_template(
        self,
        prompt: str,
        tier: str,
        context: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        """模板引擎回退：当未配置 LLM 时，使用规则模板生成基础脚本。"""
        prompt_lower = prompt.lower()

        # 场景匹配（优先级：源格式 → 目标格式 → 通用）
        if "excel" in prompt_lower or "xlsx" in prompt_lower:
            script = self._template_excel_process(prompt, context)
        elif "http" in prompt_lower or "api" in prompt_lower:
            script = self._template_http_to_db(prompt, context)
        elif "duckdb" in prompt_lower:
            script = self._template_csv_to_duckdb(prompt, context)
        elif ("csv" in prompt_lower or "csv" in prompt) and ("mysql" in prompt_lower or " sql" in prompt_lower):
            script = self._template_csv_to_mysql(prompt, context)
        elif ("csv" in prompt_lower or "csv" in prompt) and "sqlite" in prompt_lower:
            script = self._template_csv_to_sqlite(prompt, context)
        elif "定时" in prompt or "schedule" in prompt_lower or "调度" in prompt:
            script = self._template_scheduled_sync(prompt, context)
        elif "清洗" in prompt or "过滤" in prompt or "filter" in prompt_lower:
            script = self._template_data_clean(prompt, context)
        else:
            script = self._template_generic(prompt, context)

        if script:
            return script, None
        return None, "未能理解需求，请尝试更详细的描述。"

    def _template_csv_to_mysql(self, prompt: str, context: Dict[str, Any]) -> str:
        table = context.get("table_name", "target_table")
        return f'''"""CSV → MySQL 数据同步脚本（大模型辅助生成）。"""
from etl_tool_sdk import init_sdk, DataConnector, DataCleaner, LogHandler

init_sdk()
conn = DataConnector()
cleaner = DataCleaner()

# 读取 CSV（请修改为实际文件路径）
try:
    df = conn.read_csv("input.csv")
except FileNotFoundError:
    print("错误：请修改脚本中的 CSV 文件路径")
    exit(1)

# 数据清洗（根据需求调整）
# 1. 去重
df = cleaner.drop_duplicates(df)
# 2. 空值处理（示例：数值列填0，字符串列填"N/A"）
numeric_cols = df.select_dtypes(include=["number"]).columns
for col in numeric_cols:
    df[col] = df[col].fillna(0)
df = df.fillna("N/A")

# 数据校验
report = cleaner.profile(df)
LogHandler.info("数据清洗完成", extra={{"rows": len(df), "cols": report["column_count"]}})

# 写入 MySQL（请修改连接参数）
try:
    conn.write_to_mysql(
        df,
        host="localhost", port=3306,
        user="root", password="YOUR_PASSWORD",
        database="mydb",
        table="{table}",
    )
    LogHandler.info("数据写入完成", extra={{"table": "{table}", "rows": len(df)}})
except Exception as e:
    LogHandler.error("写入失败", extra={{"error": str(e)}})

print(f"同步完成：{{len(df)}} 行数据")
'''

    def _template_csv_to_sqlite(self, prompt: str, context: Dict[str, Any]) -> str:
        table = context.get("table_name", "target_table")
        return f'''"""CSV → SQLite 数据同步脚本。"""
from etl_tool_sdk import init_sdk, DataConnector, DataCleaner, LogHandler

init_sdk()
conn = DataConnector()
cleaner = DataCleaner()

# 读取 CSV（请修改文件路径）
df = conn.read_csv("input.csv")

# 数据清洗
df = cleaner.drop_duplicates(df)

# 写入 SQLite（请修改数据库路径）
conn.write_to_sqlite(df, "output.db", "{table}")

LogHandler.info("同步完成", extra={{"rows": len(df), "table": "{table}"}})
'''

    def _template_http_to_db(self, prompt: str, context: Dict[str, Any]) -> str:
        table = context.get("table_name", "http_sync_table")
        return f'''"""HTTP API → 数据库同步脚本。"""
from etl_tool_sdk import init_sdk, DataConnector, DataCleaner, LogHandler

init_sdk()
conn = DataConnector()
cleaner = DataCleaner()

# HTTP 数据源（用户自行配置 API 参数）
# base_url: API 地址（请修改）
# headers: 认证信息（请修改）
try:
    df = conn.read_from_http(
        base_url="https://api.example.com/data",
        method="GET",
        headers={{"Authorization": "Bearer YOUR_TOKEN"}},
        response_path="data.items",
        column_mapping={{"t": "datetime", "o": "open", "h": "high", "l": "low", "c": "close", "v": "vol"}},
        timeout=30,
    )
except Exception as e:
    LogHandler.error("HTTP数据拉取失败", extra={{"error": str(e)}})
    exit(1)

# 数据清洗
df = cleaner.drop_duplicates(df)

# 写入 SQLite
conn.write_to_sqlite(df, "output.db", "{table}")

LogHandler.info("HTTP同步完成", extra={{"rows": len(df)}})
'''

    def _template_excel_process(self, prompt: str, context: Dict[str, Any]) -> str:
        return '''"""Excel 数据处理脚本。"""
from etl_tool_sdk import init_sdk, DataConnector, DataCleaner, LogHandler

init_sdk()
conn = DataConnector()
cleaner = DataCleaner()

# 读取 Excel（请修改文件路径和 sheet 名称）
df = conn.read_excel("input.xlsx", sheet_name="Sheet1")

# 数据清洗
df = cleaner.drop_duplicates(df)

# 写入 SQLite
conn.write_to_sqlite(df, "output.db", "excel_data")

LogHandler.info("Excel处理完成", extra={{"rows": len(df)}})
'''

    def _template_data_clean(self, prompt: str, context: Dict[str, Any]) -> str:
        return '''"""数据清洗脚本。"""
from etl_tool_sdk import init_sdk, DataConnector, DataCleaner, LogHandler

init_sdk()
conn = DataConnector()
cleaner = DataCleaner()

# 读取数据（请修改路径和查询）
df = conn.read_csv("input.csv")

# 清洗步骤（根据需求调整）
# 1. 去重
df = cleaner.drop_duplicates(df)

# 2. 空值填充
# df = cleaner.fillna(df, {{"col1": 0, "col2": "N/A"}}, strategy="value")

# 3. 过滤行（示例）
# df = cleaner.filter_rows(df, "price > 100")

# 4. 类型转换
# df = cleaner.cast_types(df, {{"price": "float64", "quantity": "int64"}})

# 输出
conn.write_to_csv(df, "output.csv")

# 数据质量报告
report = cleaner.profile(df)
print(f"处理完成：{report['row_count']} 行，{report['column_count']} 列")
LogHandler.info("清洗完成", extra=report)
'''

    def _template_scheduled_sync(self, prompt: str, context: Dict[str, Any]) -> str:
        return '''"""定时数据同步脚本（配合 WorkflowScheduler 使用）。"""
from etl_tool_sdk import init_sdk, DataConnector, DataCleaner, WorkflowScheduler, LogHandler

init_sdk()

def sync_task():
    """实际同步逻辑"""
    conn = DataConnector()
    cleaner = DataCleaner()

    # 读取数据
    df = conn.read_csv("input.csv")

    # 处理
    df = cleaner.drop_duplicates(df)

    # 写入
    conn.write_to_sqlite(df, "output.db", "synced_data")

    LogHandler.info("定时同步完成", extra={{"rows": len(df)}})

# 添加定时任务（每日 9:30 执行）
scheduler = WorkflowScheduler()
scheduler.add_cron_job(
    task_id="daily_sync",
    callback=sync_task,
    hour=9, minute=30,
)

print("定时任务已注册")
# 运行一次测试
sync_task()
'''

    def _template_csv_to_duckdb(self, prompt: str, context: Dict[str, Any]) -> str:
        table = context.get("table_name", "duckdb_table")
        return f'''"""CSV → DuckDB 数据同步脚本。"""
from etl_tool_sdk import init_sdk, DataConnector, DataCleaner, LogHandler

init_sdk()
conn = DataConnector()
cleaner = DataCleaner()

# 读取 CSV
df = conn.read_csv("input.csv")

# 清洗
df = cleaner.drop_duplicates(df)

# 写入 DuckDB（请修改数据库路径）
conn.write_to_duckdb(df, "mydb.duckdb", "{table}")

LogHandler.info("DuckDB同步完成", extra={{"rows": len(df)}})
'''

    def _template_generic(self, prompt: str, context: Dict[str, Any]) -> str:
        return f'''"""通用数据同步脚本。"""
from etl_tool_sdk import init_sdk, DataConnector, DataCleaner, ScriptExecutor, LogHandler

init_sdk()
conn = DataConnector()
cleaner = DataCleaner()

# === 步骤 1：读取数据 ===
# 方式 A: CSV
# df = conn.read_csv("your_file.csv")

# 方式 B: MySQL
# df = conn.read_from_mysql(host="localhost", port=3306, user="root", password="xxx", database="mydb", query="SELECT * FROM table")

# 方式 C: HTTP API
# df = conn.read_from_http(base_url="https://api.example.com", method="GET", headers={{}}, ...)

# === 步骤 2：数据清洗 ===
df = cleaner.drop_duplicates(df)
# df = cleaner.fillna(df, {{"col1": 0}})
# df = cleaner.filter_rows(df, "condition")

# === 步骤 3：写入目标 ===
# conn.write_to_sqlite(df, "output.db", "table_name")
# conn.write_to_mysql(df, host="...", ...)
# conn.write_to_duckdb(df, "db.duckdb", "table")

# === 步骤 4：日志 ===
LogHandler.info("同步完成", extra={{"rows": len(df)}})

print("脚本执行完成，请在数据源和目标配置处填入实际参数")
'''

    def optimize_script(
        self,
        script: str,
        instruction: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        优化已有脚本。

        Args:
            script: 现有脚本
            instruction: 优化指令（如"增加增量同步"、"添加数据校验"）
        Returns:
            (optimized_script, error)
        """
        check_pass, check_msg = self._compliance_check(instruction)
        if not check_pass:
            return None, f"合规检查未通过：{check_msg}"

        config = self._load_llm_config()
        if config and config.get("endpoint") and config.get("api_key"):
            return self._optimize_via_llm(script, instruction, config)
        else:
            return None, "优化功能需要配置 LLM API。请在设置中配置 OpenAI 兼容接口。"

    def _optimize_via_llm(
        self,
        script: str,
        instruction: str,
        config: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        """通过 LLM 优化脚本。"""
        try:
            import requests
        except ImportError:
            return None, "requests 库不可用"

        system_prompt = (
            "你是一个数据同步脚本优化助手。用户提供一个现有脚本和优化指令，"
            "你需要修改脚本以满足优化需求。输出只包含修改后的 Python 代码（```python ... ```）。"
            "禁止生成交易、破解等违规代码。"
        )

        user_prompt = f"""优化指令：{instruction}

现有脚本：
```python
{script}
```

请按优化指令修改脚本，只输出修改后的完整代码。"""

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }
        body = {
            "model": config.get("model", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
        }

        endpoint = config["endpoint"].rstrip("/")
        if "/chat/completions" not in endpoint:
            endpoint += "/chat/completions"

        try:
            resp = requests.post(endpoint, headers=headers, json=body, timeout=60)
            if resp.status_code != 200:
                return None, f"LLM 调用失败（{resp.status_code}）"

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            optimized = self._extract_code(content)
            return optimized, None
        except Exception as e:
            return None, f"LLM 调用异常：{str(e)}"