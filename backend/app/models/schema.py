from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class FieldType(str, Enum):
    VARCHAR = "VARCHAR"
    CHAR = "CHAR"
    DECIMAL = "DECIMAL"
    FLOAT = "FLOAT"
    DOUBLE = "DOUBLE"
    INT = "INT"
    BIGINT = "BIGINT"
    DATETIME = "DATETIME"
    DATE = "DATE"
    TEXT = "TEXT"
    JSON = "JSON"

class FieldDefinition(BaseModel):
    name: str
    type: FieldType
    length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    primary_key: bool = False
    nullable: bool = True
    description: Optional[str] = None

class IndexDefinition(BaseModel):
    name: str
    fields: List[str]
    unique: bool = False

class TableSchema(BaseModel):
    table_name: str
    fields: List[FieldDefinition]
    indexes: List[IndexDefinition] = []
    database_type: str
