from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime

class ImportMode(str, Enum):
    INCREMENTAL = "incremental"
    FULL = "full"
    BULK_LOAD = "bulk_load"

class ImportStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

class FieldMapping(BaseModel):
    source_field: str
    target_field: str
    transform_expression: Optional[str] = None
    transform_type: Optional[str] = None

class BulkImportConfig(BaseModel):
    id: Optional[str] = None
    source_connection_id: str
    target_connection_id: str
    target_table: str
    file_path: Optional[str] = None
    field_mappings: List[FieldMapping] = []
    import_mode: ImportMode = ImportMode.INCREMENTAL
    batch_size: int = 5000
    parallel_threads: int = 1
    enable_checkpoint: bool = True

class BulkImportState(BaseModel):
    id: str
    config: BulkImportConfig
    file_path: str
    file_md5: str
    total_rows: int
    imported_rows: int = 0
    last_imported_index: int = 0
    status: ImportStatus = ImportStatus.PENDING
    error_at_row: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
