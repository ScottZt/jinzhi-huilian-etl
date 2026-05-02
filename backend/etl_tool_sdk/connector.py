"""
数据连接接口 — 合规设计：封装工具自身连接能力，支持用户自行配置的 HTTP 数据源，不内置任何第三方 SDK。
"""
import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import datetime

from etl_tool_sdk.license import LicenseManager
from etl_tool_sdk.config import SDKConfig


class DataConnector:
    """
    数据连接器 — 提供数据库连接、文件读取、HTTP 接口调用能力。

    合规说明：仅封装工具自身数据连接接口，不内置任何第三方数据源 SDK。
    HTTP 接口连接需用户自行配置 API 地址、Token、密钥，承担全部合规责任。

    使用示例：
        conn = DataConnector()

        # 读取 MySQL
        df = conn.read_from_mysql(host="localhost", user="root",
                                   password="xxx", database="mydb",
                                   query="SELECT * FROM orders")

        # 读取 CSV
        df = conn.read_csv("data/sales.csv")

        # HTTP API（用户自行配置）
        df = conn.read_from_http(
            base_url="https://api.example.com",
            method="POST",
            headers={"Authorization": "Bearer YOUR_TOKEN"},
            request_template={"codes": "000001", "start": "20240101"},
            response_path="data.klines",
            column_mapping={"t": "datetime", "o": "open", "h": "high"},
        )
    """

    def __init__(self):
        self._lm = LicenseManager()

    # ---- 数据库读取 ----

    def read_from_mysql(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        query: str,
        chunk_size: Optional[int] = None,
    ) -> pd.DataFrame:
        """从 MySQL 读取数据。

        Args:
            host/port/user/password/database: 连接参数
            query: SELECT 查询语句
            chunk_size: 分块读取大小（None 表示一次性读取）
        Returns:
            DataFrame
        """
        try:
            import pymysql
        except ImportError:
            raise RuntimeError("pymysql 库未安装，请运行: pip install pymysql")

        chunk_size = chunk_size or SDKConfig.CHUNK_SIZE
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=database, connect_timeout=10,
        )
        try:
            if chunk_size:
                chunks = []
                for chunk in pd.read_sql(query, conn, chunksize=chunk_size):
                    chunks.append(chunk)
                return pd.concat(chunks, ignore_index=True)
            return pd.read_sql(query, conn)
        finally:
            conn.close()

    def read_from_postgresql(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        query: str,
        chunk_size: Optional[int] = None,
    ) -> pd.DataFrame:
        """从 PostgreSQL 读取数据。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("db_postgresql")

        try:
            import psycopg2
        except ImportError:
            raise RuntimeError("psycopg2 库未安装，请运行: pip install psycopg2-binary")

        chunk_size = chunk_size or SDKConfig.CHUNK_SIZE
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, database=database,
        )
        try:
            if chunk_size:
                chunks = []
                for chunk in pd.read_sql(query, conn, chunksize=chunk_size):
                    chunks.append(chunk)
                return pd.concat(chunks, ignore_index=True)
            return pd.read_sql(query, conn)
        finally:
            conn.close()

    def read_from_duckdb(
        self,
        database: str = ":memory:",
        query: str = "SELECT * FROM read_csv_auto('data.csv')",
    ) -> pd.DataFrame:
        """从 DuckDB 读取数据。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("db_duckdb")

        try:
            import duckdb
        except ImportError:
            raise RuntimeError("duckdb 库未安装，请运行: pip install duckdb")

        conn = duckdb.connect(database)
        try:
            return conn.execute(query).fetchdf()
        finally:
            conn.close()

    def read_from_sqlite(self, db_path: str, query: str) -> pd.DataFrame:
        """从 SQLite 读取数据。"""
        return pd.read_sql(query, f"sqlite:///{db_path}")

    def read_from_clickhouse(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        query: str,
    ) -> pd.DataFrame:
        """从 ClickHouse 读取数据。需 Professional 授权。"""
        self._lm.check_feature_or_raise("db_clickhouse")

        try:
            from clickhouse_driver import Client
        except ImportError:
            raise RuntimeError("clickhouse_driver 库未安装，请运行: pip install clickhouse-driver")

        client = Client(host=host, port=port, database=database, user=user, password=password)
        result = client.execute(query)
        columns = [desc[0] for desc in client.execute("DESCRIBE TABLE (" + query + ")")]
        return pd.DataFrame(result, columns=columns)

    # ---- 文件读取 ----

    def read_csv(
        self,
        path: str,
        encoding: str = "utf-8",
        sep: str = ",",
        **kwargs,
    ) -> pd.DataFrame:
        """读取 CSV 文件。"""
        return pd.read_csv(path, encoding=encoding, sep=sep, **kwargs)

    def read_excel(
        self,
        path: str,
        sheet_name: str = 0,
        **kwargs,
    ) -> pd.DataFrame:
        """读取 Excel 文件。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("file_excel")
        return pd.read_excel(path, sheet_name=sheet_name, **kwargs)

    def read_json(
        self,
        path: str,
        orient: str = "records",
        **kwargs,
    ) -> pd.DataFrame:
        """读取 JSON 文件。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("file_json")
        return pd.read_json(path, orient=orient, **kwargs)

    def read_parquet(self, path: str, **kwargs) -> pd.DataFrame:
        """读取 Parquet 文件。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("file_parquet")
        return pd.read_parquet(path, **kwargs)

    # ---- HTTP 数据源（通用） ----

    def read_from_http(
        self,
        base_url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        request_template: Optional[Dict[str, Any]] = None,
        response_path: str = "",
        column_mapping: Optional[Dict[str, str]] = None,
        datetime_column: str = "datetime",
        timeout: int = 30,
        date_format: str = "%Y%m%d",
    ) -> pd.DataFrame:
        """
        从用户自行配置的 HTTP API 拉取数据。

        合规说明：本方法仅封装通用 HTTP 请求逻辑，数据源的 API 地址、Token、密钥
        均由用户自行填写。用户需严格遵守对应数据源的用户协议，承担全部合规责任。

        Args:
            base_url: API 基础地址
            method: HTTP 方法（GET/POST）
            headers: HTTP 请求头（如 Authorization 等）
            request_template: 请求体模板，f-string 格式，支持变量：
                {start_time}, {end_time}, {codes}, {interval}
            response_path: 响应数据路径（点分隔，如 "data.klines"）
            column_mapping: 列名映射，{"原始列名": "标准列名"}
            datetime_column: 时间字段列名
            timeout: 请求超时（秒）
            date_format: 日期格式
        Returns:
            DataFrame（含标准字段：datetime, open, high, low, close, vol, amount, code 等）
        """
        self._lm.check_feature_or_raise("http_connector")

        try:
            import requests
        except ImportError:
            raise RuntimeError("requests 库未安装")

        headers = headers or {}
        request_template = request_template or {}
        timeout = min(timeout, SDKConfig.HTTP_TIMEOUT)

        end_time = datetime.now()
        start_time = end_time - pd.Timedelta(days=30)

        start_str = start_time.strftime(date_format)
        end_str = end_time.strftime(date_format)

        codes_str = request_template.get("codes", "")
        interval_str = request_template.get("interval", "D")

        try:
            import json
            req_body_str = json.dumps(request_template)
            req_body_str = req_body_str.format(
                start_time=start_str,
                end_time=end_str,
                codes=codes_str,
                interval=interval_str,
            )
            req_body = json.loads(req_body_str)
        except (ValueError, KeyError):
            req_body = request_template

        if method.upper() == "GET":
            resp = requests.get(
                base_url, headers=headers,
                params=req_body if isinstance(req_body, dict) else None,
                timeout=timeout,
            )
        else:
            resp = requests.post(
                base_url, headers=headers, json=req_body, timeout=timeout,
            )

        resp.raise_for_status()
        data = resp.json()

        if response_path:
            for key in response_path.split("."):
                if key:
                    data = data.get(key, [])
        if not isinstance(data, list):
            data = data.get("data", data.get("result", []))
            if not isinstance(data, list):
                return pd.DataFrame()

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        if column_mapping:
            df = df.rename(columns=column_mapping)

        if datetime_column in df.columns:
            df[datetime_column] = pd.to_datetime(df[datetime_column], errors="coerce")

        return df

    def read_from_websocket(
        self,
        url: str,
        subscribe_message: Dict[str, Any],
        field_mapping: Optional[Dict[str, str]] = None,
        timeout: int = 10,
    ) -> pd.DataFrame:
        """
        从 WebSocket 连接读取实时数据。

        合规说明：需用户自行配置 WebSocket 地址和认证信息。

        Args:
            url: WebSocket 连接地址
            subscribe_message: 订阅消息（字典或 JSON 字符串）
            field_mapping: 字段映射
            timeout: 连接超时（秒）
        Returns:
            DataFrame（包含接收到的所有数据）
        """
        self._lm.check_feature_or_raise("http_connector")

        try:
            import websocket
        except ImportError:
            raise RuntimeError("websocket-client 库未安装，请运行: pip install websocket-client")

        import json

        results = []

        def on_message(ws, message):
            data = json.loads(message)
            results.append(data)

        def on_error(ws, error):
            pass

        def on_close(ws, *args):
            pass

        ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        import threading
        import time

        t = threading.Thread(target=ws.run_forever, kwargs={"timeout": timeout})
        t.start()
        time.sleep(1)

        if isinstance(subscribe_message, dict):
            ws.send(json.dumps(subscribe_message))
        else:
            ws.send(subscribe_message)

        time.sleep(min(timeout, 5))
        ws.close()
        t.join(timeout=2)

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        if field_mapping:
            df = df.rename(columns=field_mapping)
        return df

    # ---- 数据写入 ----

    def write_to_sqlite(self, df: pd.DataFrame, db_path: str, table: str, if_exists: str = "replace"):
        """写入 SQLite。"""
        from sqlalchemy import create_engine
        engine = create_engine(f"sqlite:///{db_path}")
        df.to_sql(table, engine, if_exists=if_exists, index=False)
        engine.dispose()

    def write_to_mysql(
        self,
        df: pd.DataFrame,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        table: str,
        if_exists: str = "replace",
        chunk_size: int = 1000,
    ):
        """批量写入 MySQL。"""
        import pymysql
        from sqlalchemy import create_engine

        engine = create_engine(
            f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        )
        df.to_sql(table, engine, if_exists=if_exists, index=False, chunksize=chunk_size)
        engine.dispose()

    def write_to_duckdb(
        self,
        df: pd.DataFrame,
        database: str,
        table: str,
        if_exists: str = "replace",
    ):
        """批量写入 DuckDB。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("db_duckdb")

        try:
            import duckdb
        except ImportError:
            raise RuntimeError("duckdb 库未安装")

        conn = duckdb.connect(database)
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df")
        conn.close()

    def write_to_csv(self, df: pd.DataFrame, path: str, **kwargs):
        """写入 CSV。"""
        df.to_csv(path, index=False, **kwargs)

    def write_to_excel(self, df: pd.DataFrame, path: str, sheet_name: str = "Sheet1", **kwargs):
        """写入 Excel。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("file_excel")
        df.to_excel(path, sheet_name=sheet_name, index=False, **kwargs)

    def write_to_json(self, df: pd.DataFrame, path: str, orient: str = "records", **kwargs):
        """写入 JSON。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("file_json")
        df.to_json(path, orient=orient, **kwargs)

    def write_to_parquet(self, df: pd.DataFrame, path: str, **kwargs):
        """写入 Parquet。需 Personal 及以上授权。"""
        self._lm.check_feature_or_raise("file_parquet")
        df.to_parquet(path, index=False, **kwargs)
