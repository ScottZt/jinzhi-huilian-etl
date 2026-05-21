import duckdb
import pandas as pd
from typing import Dict, Any, List


class DuckDBBulkLoader:

    def __init__(self, config: Dict[str, Any]):
        self.db_path = config.get("db_path", "")
        if not self.db_path:
            raise ValueError("db_path 为空")
        self.connection = None

    def connect(self):
        if not self.connection:
            self.connection = duckdb.connect(self.db_path, read_only=False)
        return self.connection

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def bulk_load(self, csv_path: str, table: str,
                  field_mappings: List[Dict[str, str]] = None) -> int:

        conn = self.connect()
        conn.execute(f"COPY {table} FROM '{csv_path}' (FORMAT CSV, HEADER TRUE)")
        return 0

    def batch_insert(self, df: pd.DataFrame, table: str,
                     field_mappings: List[Dict[str, str]] = None, batch_size: int = 0) -> int:

        conn = self.connect()
        conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
        return len(df)

    def check_connectivity(self) -> tuple[bool, str]:
        try:
            conn = self.connect()
            version = conn.execute("SELECT version()").fetchone()[0]
            ver = version.split("-")[0].strip() if version else version
            return True, f"已连接 DuckDB ({ver})"
        except Exception as e:
            return False, str(e)
