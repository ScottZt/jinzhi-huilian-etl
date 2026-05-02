import pymysql
import pandas as pd
from typing import Dict, Any, List
from pathlib import Path
import tempfile
import csv

class MySQLBulkLoader:

    def __init__(self, config: Dict[str, Any]):
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 3306)
        self.user = config.get("user")
        self.password = config.get("password")
        self.database = config.get("database")
        self.connection = None

    def connect(self):
        if not self.connection:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                local_infile=True
            )
        return self.connection

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def prepare_csv_for_load(self,
                            df: pd.DataFrame,
                            field_mappings: List[Dict[str, str]]) -> str:

        target_fields = [m['target_field'] for m in field_mappings]
        source_fields = [m['source_field'] for m in field_mappings]

        df_mapped = df[source_fields].copy()
        df_mapped.columns = target_fields

        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='', encoding='utf-8')
        df_mapped.to_csv(temp_file.name, index=False, quoting=csv.QUOTE_MINIMAL)
        temp_file.close()

        return temp_file.name

    def bulk_load(self,
                  csv_path: str,
                  table: str,
                  field_mappings: List[Dict[str, str]],
                  ignore_first_row: bool = True) -> int:

        conn = self.connect()
        cursor = conn.cursor()

        target_fields = [m['target_field'] for m in field_mappings]
        fields_str = ', '.join(target_fields)

        ignore_clause = "IGNORE 1 ROWS" if ignore_first_row else ""

        csv_path_normalized = csv_path.replace('\\', '/')

        sql = f"""
        LOAD DATA LOCAL INFILE '{csv_path_normalized}'
        INTO TABLE {table}
        FIELDS TERMINATED BY ','
        ENCLOSED BY '"'
        LINES TERMINATED BY '\\n'
        {ignore_clause}
        ({fields_str})
        """

        cursor.execute(sql)
        conn.commit()

        rows_affected = cursor.rowcount
        cursor.close()

        return rows_affected

    def batch_insert(self,
                    df: pd.DataFrame,
                    table: str,
                    field_mappings: List[Dict[str, str]],
                    batch_size: int = 5000) -> int:

        conn = self.connect()
        cursor = conn.cursor()

        target_fields = [m['target_field'] for m in field_mappings]
        source_fields = [m['source_field'] for m in field_mappings]

        df_mapped = df[source_fields].copy()
        df_mapped.columns = target_fields

        fields_str = ', '.join(target_fields)
        placeholders = ', '.join(['%s'] * len(target_fields))

        sql = f"INSERT INTO {table} ({fields_str}) VALUES ({placeholders})"

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
            cursor.execute("SELECT 1")
            cursor.close()
            return True, "MySQL connection successful"
        except Exception as e:
            return False, str(e)
