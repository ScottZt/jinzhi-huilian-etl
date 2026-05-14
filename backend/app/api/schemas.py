from fastapi import APIRouter
from typing import List, Optional
from pydantic import BaseModel
import uuid
import re

from app.models.schema import TableSchema, FieldDefinition, IndexDefinition, FieldType
from app.core.schema_manager import SchemaManager
from app.core.connection_manager import ConnectionManager
from app.persistence import sqlite_repo

router = APIRouter()
schema_mgr = SchemaManager()
conn_mgr = ConnectionManager()


class SchemaCreate(BaseModel):
    table_name: str
    database_type: str
    fields: List[dict]
    indexes: List[dict] = []


class DDLPreview(BaseModel):
    table_name: str
    database_type: str
    fields: List[dict]
    indexes: List[dict] = []


class ApplySchema(BaseModel):
    schema_id: Optional[str] = None
    connection_id: str
    table_name: str
    database_type: str
    fields: List[dict]
    indexes: List[dict] = []
    on_exists: str = "fail"


class TableExistsCheck(BaseModel):
    connection_id: str
    table_name: str


def _normalize_fields(fields: List[dict]) -> List[dict]:
    # 向后兼容历史数据：旧版本保存的 VARCHAR 字段可能没有 length，统一补默认值。
    normalized: List[dict] = []
    for field in fields or []:
        item = dict(field)
        if str(item.get("type", "")).upper() == "VARCHAR":
            length = item.get("length")
            if length is None or str(length).strip() == "":
                item["length"] = 255
        normalized.append(item)
    return normalized


def _is_safe_identifier(name: str) -> bool:
    # 限制可执行 SQL 的对象名，避免覆盖模式下拼接 SQL 带来注入风险。
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(name or "")))


def _table_exists(conn_config, table_name: str) -> bool:
    # 统一复用连接管理器的表列表能力，跨库做存在性检查。
    tables = conn_mgr.get_tables(conn_config)
    target = str(table_name or "").lower()
    return any(str(t).lower() == target for t in tables)


def _build_drop_table_sql(db_type: str, table_name: str) -> str:
    # 各数据库统一使用 IF EXISTS 语义，避免重复删除抛错中断。
    db = str(db_type or "").lower()
    if db in ("mysql", "postgresql", "duckdb", "clickhouse"):
        return f"DROP TABLE IF EXISTS {table_name};"
    raise ValueError(f"Unsupported database type for overwrite: {db_type}")


@router.get("/", response_model=list)
async def get_all_schemas():
    return sqlite_repo.list_schemas()


@router.get("/{schema_id}")
async def get_schema(schema_id: str):
    data = sqlite_repo.get_schema(schema_id)
    if not data:
        return {"error": "Schema not found"}
    return data


@router.post("/")
async def create_schema(body: SchemaCreate):
    schema_id = str(uuid.uuid4())
    record = {
        "id": schema_id,
        "table_name": body.table_name,
        "database_type": body.database_type,
        "schema_json": {
            "table_name": body.table_name,
            "database_type": body.database_type,
            "fields": body.fields,
            "indexes": body.indexes,
        },
    }
    result = sqlite_repo.save_schema(record)
    return result


@router.put("/{schema_id}")
async def update_schema(schema_id: str, body: SchemaCreate):
    record = {
        "id": schema_id,
        "table_name": body.table_name,
        "database_type": body.database_type,
        "schema_json": {
            "table_name": body.table_name,
            "database_type": body.database_type,
            "fields": body.fields,
            "indexes": body.indexes,
        },
    }
    result = sqlite_repo.save_schema(record)
    return result


@router.delete("/{schema_id}")
async def delete_schema(schema_id: str):
    deleted = sqlite_repo.delete_schema(schema_id)
    return {"deleted": deleted}


@router.post("/preview-ddl")
async def preview_ddl(body: DDLPreview):
    normalized_fields = _normalize_fields(body.fields)
    schema = TableSchema(
        table_name=body.table_name,
        database_type=body.database_type,
        fields=[FieldDefinition(**f) for f in normalized_fields],
        indexes=[IndexDefinition(**i) for i in body.indexes],
    )
    errors = schema_mgr.validate_schema(schema)
    if errors:
        return {"errors": errors}

    ddl = schema_mgr.generate_ddl(schema)
    return {"ddl": ddl}


@router.post("/check-table")
async def check_table_exists(body: TableExistsCheck):
    conn_data = sqlite_repo.get_connection(body.connection_id)
    if not conn_data:
        return {"error": "Connection not found", "exists": False}
    if not _is_safe_identifier(body.table_name):
        return {"error": "Invalid table name", "exists": False}

    from app.models.connection import ConnectionConfig
    conn_config = ConnectionConfig(
        id=conn_data["id"], name=conn_data["name"],
        type=conn_data["type"], config=conn_data["config"],
    )
    try:
        exists = _table_exists(conn_config, body.table_name)
        return {"exists": exists, "table_name": body.table_name}
    except Exception as e:
        return {"exists": False, "error": str(e)}


@router.post("/apply")
async def apply_schema(body: ApplySchema):
    normalized_fields = _normalize_fields(body.fields)
    schema = TableSchema(
        table_name=body.table_name,
        database_type=body.database_type,
        fields=[FieldDefinition(**f) for f in normalized_fields],
        indexes=[IndexDefinition(**i) for i in body.indexes],
    )
    errors = schema_mgr.validate_schema(schema)
    if errors:
        return {"errors": errors}

    conn_data = sqlite_repo.get_connection(body.connection_id)
    if not conn_data:
        return {"error": "Connection not found"}

    from app.models.connection import ConnectionConfig, ConnectionType
    conn_config = ConnectionConfig(
        id=conn_data["id"], name=conn_data["name"],
        type=conn_data["type"], config=conn_data["config"],
    )
    if not _is_safe_identifier(body.table_name):
        return {"success": False, "message": "Invalid table name"}

    on_exists = str(body.on_exists or "fail").lower()
    if on_exists not in ("fail", "skip", "overwrite"):
        return {"success": False, "message": f"Unsupported on_exists policy: {body.on_exists}"}

    try:
        exists = _table_exists(conn_config, body.table_name)
    except Exception as e:
        return {"success": False, "message": f"检查表是否存在失败: {e}"}

    if exists and on_exists == "skip":
        return {"success": True, "skipped": True, "message": f"表 {body.table_name} 已存在，已按策略跳过"}

    if exists and on_exists == "fail":
        return {"success": False, "table_exists": True, "message": f"表 {body.table_name} 已存在"}

    if exists and on_exists == "overwrite":
        try:
            drop_sql = _build_drop_table_sql(conn_config.type, body.table_name)
            drop_ok, drop_msg = conn_mgr.execute_ddl(conn_config, drop_sql)
            if not drop_ok:
                return {"success": False, "message": f"覆盖前删除旧表失败: {drop_msg}"}
        except Exception as e:
            return {"success": False, "message": f"覆盖前删除旧表失败: {e}"}

    ddl = schema_mgr.generate_ddl(schema)
    success, msg = conn_mgr.execute_ddl(conn_config, ddl)

    if success:
        schema_id = body.schema_id or str(uuid.uuid4())
        record = {
            "id": schema_id,
            "table_name": body.table_name,
            "database_type": body.database_type,
            "schema_json": {
                "table_name": body.table_name,
                "database_type": body.database_type,
                "fields": normalized_fields,
                "indexes": body.indexes,
            },
        }
        sqlite_repo.save_schema(record)
        return {"success": True, "message": msg, "schema_id": schema_id, "ddl": ddl}
    else:
        return {"success": False, "message": msg, "ddl": ddl}
