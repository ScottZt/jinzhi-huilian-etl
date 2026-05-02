"""
金智汇联ETL 工具 SDK — 合规设计：仅封装工具自身功能接口，不涉及任何第三方数据源。

版本：v1.0
适用版本：Professional / Personal / Free

使用示例：
    from etl_tool_sdk import DataConnector, DataCleaner, ScriptExecutor, LogHandler

    # 连接数据库
    conn = DataConnector()
    df = conn.read_from_mysql(host="localhost", port=3306, user="root",
                               password="xxx", database="mydb", query="SELECT * FROM users")

    # 数据清洗
    cleaner = DataCleaner()
    df_clean = cleaner.drop_duplicates(df)
    df_clean = cleaner.fillna(df_clean, {"col1": 0, "col2": "N/A"})

    # 写入目标
    conn.write_to_sqlite(df_clean, "output.db", "cleaned_table")

    # 日志记录
    LogHandler.info("ETL流程完成", extra={"rows": len(df_clean)})
"""

__version__ = "1.0.0"
__product__ = "金智汇联ETL"
__compliant__ = True

from etl_tool_sdk.connector import DataConnector
from etl_tool_sdk.cleaner import DataCleaner
from etl_tool_sdk.scheduler import WorkflowScheduler
from etl_tool_sdk.executor import ScriptExecutor
from etl_tool_sdk.logger import LogHandler
from etl_tool_sdk.license import LicenseManager
from etl_tool_sdk.config import SDKConfig, init_sdk

__all__ = [
    "DataConnector",
    "DataCleaner",
    "WorkflowScheduler",
    "ScriptExecutor",
    "LogHandler",
    "LicenseManager",
    "SDKConfig",
    "init_sdk",
]
