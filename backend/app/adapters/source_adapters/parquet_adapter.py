import pandas as pd
from typing import Optional, Dict, Any
from pathlib import Path


class ParquetAdapter:

    def __init__(self, config: Dict[str, Any]):
        self.file_path = config.get("file_path")

    def read_parquet(self, file_path: Optional[str] = None, nrows: Optional[int] = None) -> pd.DataFrame:
        path = file_path or self.file_path
        if not path:
            raise ValueError("file_path is required")

        df = pd.read_parquet(path)
        if nrows:
            df = df.head(nrows)
        return df

    def get_file_info(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        path = Path(file_path or self.file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        df_sample = pd.read_parquet(str(path))
        total_rows = len(df_sample)

        return {
            "file_path": str(path),
            "file_size": path.stat().st_size,
            "total_rows": total_rows,
            "columns": df_sample.columns.tolist(),
            "dtypes": {c: str(df_sample[c].dtype) for c in df_sample.columns},
            "sample_data": df_sample.head(5).to_dict(orient='records'),
        }

    def check_connectivity(self) -> tuple[bool, str]:
        try:
            path = Path(self.file_path)
            if not path.exists():
                return False, f"File not found: {self.file_path}"
            df = pd.read_parquet(str(path))
            return True, f"Parquet file with {len(df)} rows, {len(df.columns)} columns"
        except Exception as e:
            return False, str(e)
