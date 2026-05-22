from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum

class ConnectionType(str, Enum):
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    DUCKDB = "duckdb"
    CLICKHOUSE = "clickhouse"
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    PARQUET = "parquet"
    FOLDER_WATCH = "folder_watch"
    TDX = "tdx"
    AKSHARE = "akshare"
    TUSHARE = "tushare"
    BINANCE = "binance"
    YFINANCE = "yfinance"

class ConnectionConfig(BaseModel):
    id: Optional[str] = None
    name: str
    type: ConnectionType
    config: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True

class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
