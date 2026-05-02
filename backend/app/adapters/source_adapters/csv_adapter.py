import pandas as pd
import chardet
from typing import Optional, Dict, Any, List
from pathlib import Path

class CSVAdapter:

    def __init__(self, config: Dict[str, Any]):
        self.file_path = config.get("file_path")
        self.encoding = config.get("encoding", "utf-8")
        self.delimiter = config.get("delimiter", ",")
        self.has_header = config.get("has_header", True)

    def detect_encoding(self, file_path: str) -> str:
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)
            result = chardet.detect(raw_data)
            return result['encoding']

    def detect_delimiter(self, file_path: str, encoding: str) -> str:
        with open(file_path, 'r', encoding=encoding) as f:
            first_line = f.readline()
            for delimiter in [',', '\t', ';', '|']:
                if delimiter in first_line:
                    return delimiter
        return ','

    def read_csv(self,
                 file_path: Optional[str] = None,
                 nrows: Optional[int] = None,
                 skiprows: Optional[int] = None) -> pd.DataFrame:

        path = file_path or self.file_path
        if not path:
            raise ValueError("file_path is required")

        if self.encoding == "auto":
            self.encoding = self.detect_encoding(path)

        if self.delimiter == "auto":
            self.delimiter = self.detect_delimiter(path, self.encoding)

        header = 0 if self.has_header else None

        df = pd.read_csv(
            path,
            encoding=self.encoding,
            delimiter=self.delimiter,
            header=header,
            nrows=nrows,
            skiprows=skiprows
        )

        return df

    def get_file_info(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        path = Path(file_path or self.file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        encoding = self.detect_encoding(str(path))
        delimiter = self.detect_delimiter(str(path), encoding)

        df_sample = pd.read_csv(
            str(path),
            encoding=encoding,
            delimiter=delimiter,
            nrows=100
        )

        total_lines = sum(1 for _ in open(str(path), 'r', encoding=encoding))

        return {
            "file_path": str(path),
            "file_size": path.stat().st_size,
            "encoding": encoding,
            "delimiter": delimiter,
            "total_rows": total_lines - (1 if self.has_header else 0),
            "columns": df_sample.columns.tolist(),
            "sample_data": df_sample.head(5).to_dict(orient='records')
        }

    def check_connectivity(self) -> tuple[bool, str]:
        try:
            path = Path(self.file_path)
            if not path.exists():
                return False, f"File not found: {self.file_path}"

            df = self.read_csv(nrows=1)
            return True, f"Successfully read CSV with {len(df.columns)} columns"
        except Exception as e:
            return False, str(e)
