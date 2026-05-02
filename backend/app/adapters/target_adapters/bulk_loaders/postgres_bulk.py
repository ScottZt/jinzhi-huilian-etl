import psycopg2
import pandas as pd
import tempfile
import csv
from typing import Dict, Any, List


class PostgresBulkLoader:

    def __init__(self, config: Dict[str, Any]):
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 5432)
        self.user = config.get("user")
        self.password = config.get("password")
        self.database = config.get("database")
        self.connection = None

    def connect(self):
        if not self.connection:
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
        return self.connection

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def bulk_load(self, csv_path: str, table: str,
                  field_mappings: List[Dict[str, str]], ignore_first_row: bool = True) -> int:

        conn = self.connect()
        cursor = conn.cursor()

        target_fields = [m['target_field'] for m in field_mappings]
        fields_str = ', '.join(target_fields)

        with open(csv_path, 'r', encoding='utf-8') as f:
            cursor.copy_expert(
                f"COPY {table} ({fields_str}) FROM STDIN WITH CSV HEADER",
                f
            )

        conn.commit()
        rows_affected = cursor.rowcount
        cursor.close()
        return rows_affected

    def batch_insert(self, df: pd.DataFrame, table: str,
                     field_mappings: List[Dict[str, str]], batch_size: int = 5000) -> int:

        conn = self.connect()
        cursor = conn.cursor()

        target_fields = [m['target_field'] for m in field_mappings]
        source_fields = [m['source_field'] for m in field_mappings]

        df_mapped = df[source_fields].copy()
        df_mapped.columns = target_fields
        df_mapped = df_mapped.where(pd.notnull(df_mapped), None)

        placeholders = ', '.join(['%s'] * len(target_fields))
        sql = f"INSERT INTO {table} ({', '.join(target_fields)}) VALUES ({placeholders})"

        total_inserted = 0
        for i in range(0, len(df_mapped), batch_size):
            batch = df_mapped.iloc[i:i+batch_size]
            values = [tuple(row) for row in batch.values]
            cursor.executemany(sql, values)
            conn.commit()
            total_inserted += len(values)

        cursor.close()
        return total_inserted

    def check_connectivity(self) -> tuple[bool, str]:
        try:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            # 解析版本字符串，提取主要信息
            parts = version.split(",")
            server_version = parts[0].replace("PostgreSQL ", "").strip() if parts else version
            cursor.close()
            return True, f"已连接 PostgreSQL ({server_version})"
        except Exception as e:
            return False, str(e)
