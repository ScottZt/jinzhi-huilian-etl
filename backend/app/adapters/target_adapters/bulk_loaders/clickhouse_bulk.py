import clickhouse_driver
import pandas as pd
from typing import Dict, Any, List


class ClickHouseBulkLoader:

    def __init__(self, config: Dict[str, Any]):
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 9000)
        self.user = config.get("user", "default")
        self.password = config.get("password", "")
        self.database = config.get("database", "default")
        self.client = None

    def connect(self):
        if not self.client:
            self.client = clickhouse_driver.Client(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
        return self.client

    def close(self):
        if self.client:
            self.client.disconnect()
            self.client = None

    def bulk_load(self, csv_path: str, table: str,
                  field_mappings: List[Dict[str, str]] = None) -> int:

        client = self.connect()
        client.execute(f"INSERT INTO {table} FROM INFILE '{csv_path}' FORMAT CSVWithNames")
        return 0

    def batch_insert(self, df: pd.DataFrame, table: str,
                     field_mappings: List[Dict[str, str]] = None, batch_size: int = 5000) -> int:

        client = self.connect()
        total_inserted = 0
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            records = batch.to_dict("records")
            client.execute(f"INSERT INTO {table}", records)
            total_inserted += len(records)
        return total_inserted

    def check_connectivity(self) -> tuple[bool, str]:
        try:
            client = self.connect()
            version = client.execute("SELECT version()")
            ver = version[0][0] if version else ""
            return True, f"已连接 ClickHouse ({ver})"
        except Exception as e:
            return False, str(e)
