import pandas as pd
import json
from typing import Optional, Dict, Any
from pathlib import Path


class JSONAdapter:

    def __init__(self, config: Dict[str, Any]):
        self.file_path = config.get("file_path")
        self.format = config.get("format", "records")

    def read_json(self, file_path: Optional[str] = None, nrows: Optional[int] = None) -> pd.DataFrame:
        path = file_path or self.file_path
        if not path:
            raise ValueError("file_path is required")

        df = pd.read_json(path, orient=self.format)
        if nrows:
            df = df.head(nrows)
        return df

    def get_file_info(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        path = Path(file_path or self.file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        df_sample = pd.read_json(str(path), orient=self.format)
        total_rows = len(df_sample)

        return {
            "file_path": str(path),
            "file_size": path.stat().st_size,
            "format": self.format,
            "total_rows": total_rows,
            "columns": df_sample.columns.tolist(),
            "sample_data": df_sample.head(5).to_dict(orient='records'),
        }

    def check_connectivity(self) -> tuple[bool, str]:
        try:
            path = Path(self.file_path)
            if not path.exists():
                return False, f"File not found: {self.file_path}"
            with open(path, 'r') as f:
                data = f.read(1000)
                json.loads(data)
            return True, "JSON file is valid"
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, str(e)
