from fastapi import APIRouter
from typing import List, Optional
from pydantic import BaseModel
import uuid

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
    schema = TableSchema(
        table_name=body.table_name,
        database_type=body.database_type,
        fields=[FieldDefinition(**f) for f in body.fields],
        indexes=[IndexDefinition(**i) for i in body.indexes],
    )
    errors = schema_mgr.validate_schema(schema)
    if errors:
        return {"errors": errors}

    ddl = schema_mgr.generate_ddl(schema)
    return {"ddl": ddl}


@router.post("/apply")
async def apply_schema(body: ApplySchema):
    schema = TableSchema(
        table_name=body.table_name,
        database_type=body.database_type,
        fields=[FieldDefinition(**f) for f in body.fields],
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
                "fields": body.fields,
                "indexes": body.indexes,
            },
        }
        sqlite_repo.save_schema(record)
        return {"success": True, "message": msg, "schema_id": schema_id, "ddl": ddl}
    else:
        return {"success": False, "message": msg, "ddl": ddl}
