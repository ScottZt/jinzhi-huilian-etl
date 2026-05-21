from fastapi import APIRouter
from typing import List, Optional
from pydantic import BaseModel
import uuid
import re
import json

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


class AIGenerateRequest(BaseModel):
    table_name: str
    database_type: str
    description: str
    json_sample: str = ""


class AIInferFromJsonRequest(BaseModel):
    table_name: str
    database_type: str
    json_sample: str


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


# ---------- AI Schema Helpers ----------

_JSON_TYPE_MAP = {
    "int": "INT", "integer": "INT", "long": "BIGINT", "bigint": "BIGINT",
    "float": "FLOAT", "double": "DOUBLE", "number": "DECIMAL",
    "str": "VARCHAR", "string": "VARCHAR", "text": "TEXT",
    "bool": "INT", "boolean": "INT",
    "date": "DATE", "datetime": "DATETIME", "timestamp": "DATETIME",
    "null": "VARCHAR",
}


def _infer_python_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        # 判断是否像时间戳
        if 1e9 < value < 2e10:
            return "datetime"
        if value > 2**31:
            return "bigint"
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        s = value.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            return "date"
        if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", s):
            return "datetime"
        if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", s):
            return "datetime"
        if len(s) > 255:
            return "text"
        return "str"
    if isinstance(value, (list, dict)):
        return "json"
    return "str"


def _infer_json_fields(json_sample: str) -> List[dict]:
    """从 JSON 样例规则推断字段结构。"""
    try:
        data = json.loads(json_sample)
    except Exception:
        return []

    if isinstance(data, list) and data:
        obj = data[0]
    elif isinstance(data, dict):
        obj = data
    else:
        return []

    fields = []
    for key, value in obj.items():
        py_type = _infer_python_type(value)
        schema_type = _JSON_TYPE_MAP.get(py_type, "VARCHAR")
        field = {
            "name": key,
            "type": schema_type,
            "nullable": value is None,
        }
        if schema_type == "VARCHAR" and isinstance(value, str):
            field["length"] = min(max(len(value) * 2, 50), 500)
        if schema_type == "DECIMAL":
            field["precision"] = 18
            field["scale"] = 4
        fields.append(field)
    return fields


_MD_TYPE_MAP = {
    "VARCHAR": "VARCHAR", "CHAR": "CHAR", "TEXT": "TEXT",
    "INT": "INT", "INTEGER": "INT", "BIGINT": "BIGINT",
    "FLOAT": "FLOAT", "DOUBLE": "DOUBLE", "DECIMAL": "DECIMAL", "NUMERIC": "DECIMAL",
    "DATETIME": "DATETIME", "TIMESTAMP": "DATETIME",
    "DATE": "DATE", "JSON": "JSON", "BOOL": "INT", "BOOLEAN": "INT",
    "STRING": "VARCHAR",
}


def _parse_markdown_table(text: str) -> List[dict]:
    """从 Markdown/ASCII 表格文本中解析字段定义。

    支持格式：
    | 字段名 | 类型 | 可空 | 备注 |
    ├─────────────┼─────────────┼──────┼──────────┤
    │ stock_code │ VARCHAR(20) │ 否 │ 股票代码 │
    """
    lines = text.strip().splitlines()
    fields = []

    # 识别分隔行（包含 ├、├─、+──、|--- 等）
    def _is_separator(line: str) -> bool:
        stripped = line.strip()
        return bool(re.match(r'^[\|+├┬┼─┐┌└┘]+[─┬┼┤├└┐┌┘\-\s]*$', stripped))

    # 提取数据行
    data_lines = []
    for line in lines:
        stripped = line.strip()
        if _is_separator(stripped):
            continue
        if '│' in stripped or (stripped.startswith('|') and stripped.endswith('|')):
            # 去掉边界符号
            if '│' in stripped:
                cells = stripped.strip('│').split('│')
            else:
                cells = stripped.strip('|').split('|')
            cells = [c.strip() for c in cells]
            if cells and any(c for c in cells):
                data_lines.append(cells)

    if len(data_lines) < 1:
        return []

    # 第一行为表头，找列索引
    headers = [h.lower() for h in data_lines[0]]
    name_idx = -1
    type_idx = -1
    null_idx = -1
    desc_idx = -1

    for i, h in enumerate(headers):
        if '字段' in h or 'name' in h or '列名' in h or '列' in h:
            name_idx = i
        elif '类型' in h or 'type' in h:
            type_idx = i
        elif '可空' in h or 'null' in h or '允许空' in h:
            null_idx = i
        elif '备注' in h or '说明' in h or '描述' in h or 'comment' in h or '备注' in h:
            desc_idx = i

    # 如果没找到表头，尝试按位置猜测（常见顺序：字段名、类型、可空、备注）
    if name_idx < 0:
        # 尝试匹配第一行中看起来像字段名的列
        for i, h in enumerate(headers):
            if i == 0:
                name_idx = i
                break
        if type_idx < 0 and len(headers) > 1:
            type_idx = 1
        if null_idx < 0 and len(headers) > 2:
            null_idx = 2
        if desc_idx < 0 and len(headers) > 3:
            desc_idx = 3

    for row in data_lines[1:]:
        if name_idx >= len(row):
            continue
        field_name = row[name_idx].strip()
        if not field_name:
            continue

        field_type_raw = row[type_idx].strip() if 0 <= type_idx < len(row) else ""
        # 从类型字符串中提取基础类型和长度，如 "VARCHAR(20)" → "VARCHAR", 20
        type_match = re.match(r"^([A-Za-z]+)(?:\((\d+)(?:,\s*(\d+))?\))?$", field_type_raw)
        if type_match:
            base_type = type_match.group(1).upper()
            length = int(type_match.group(2)) if type_match.group(2) else None
            precision = int(type_match.group(3)) if type_match.group(3) else None
        else:
            base_type = field_type_raw.upper()
            length = None
            precision = None

        schema_type = _MD_TYPE_MAP.get(base_type, "VARCHAR")
        nullable_text = row[null_idx].strip() if 0 <= null_idx < len(row) else ""
        nullable = nullable_text in ("是", "Yes", "yes", "Y", "y", "true", "True", "")

        description = row[desc_idx].strip() if 0 <= desc_idx < len(row) else ""

        field = {
            "name": field_name,
            "type": schema_type,
            "nullable": nullable,
        }
        if length and schema_type in ("VARCHAR", "CHAR"):
            field["length"] = length
        if precision and schema_type == "DECIMAL":
            field["precision"] = precision
            scale_match = re.search(r"\((\d+),\s*(\d+)\)", field_type_raw)
            if scale_match:
                field["scale"] = int(scale_match.group(2))
        if description:
            field["description"] = description

        fields.append(field)

    return fields


def _build_llm_schema_prompt(body: AIGenerateRequest) -> str:
    db_hint = body.database_type.lower()
    type_note = {
        "mysql": "MySQL 类型（VARCHAR/INT/BIGINT/DECIMAL/DATETIME/TEXT/JSON）",
        "postgresql": "PostgreSQL 类型（VARCHAR/INTEGER/BIGINT/NUMERIC/TIMESTAMP/TEXT/JSONB）",
        "duckdb": "DuckDB 类型（VARCHAR/INTEGER/BIGINT/DECIMAL/TIMESTAMP/VARCHAR/JSON）",
        "clickhouse": "ClickHouse 类型（String/Int32/Int64/Decimal/DateTime/Date）",
    }.get(db_hint, "通用 SQL 类型")

    json_hint = ""
    if body.json_sample:
        json_hint = f"\n\nJSON 数据样例:\n```json\n{body.json_sample[:3000]}\n```"

    return (
        f"你是一个数据库表结构设计助手。请根据以下描述生成表结构定义。\n\n"
        f"表名: {body.table_name}\n"
        f"目标数据库: {body.database_type}\n"
        f"表描述: {body.description}"
        f"{json_hint}\n\n"
        f"请严格输出一个 JSON 对象，不要输出其他说明。结构如下:\n"
        "{\n"
        '  "fields": [\n'
        '    {"name": "字段名", "type": "字段类型", "nullable": true/false, '
        '"description": "字段说明", "primary_key": true/false, '
        '"length": 数字(VARCHAR时), "precision": 数字(DECIMAL时), "scale": 数字(DECIMAL时)}\n'
        "  ],\n"
        '  "indexes": [\n'
        '    {"name": "索引名", "fields": ["字段1"], "unique": false}\n'
        "  ]\n"
        "}\n\n"
        f"要求:\n"
        f"1. 字段类型请使用 {type_note}\n"
        f"2. 合理设置主键（通常是有唯一标识意义的字段）\n"
        f"3. 时间字段使用 DATETIME 类型\n"
        f"4. 金额/价格等小数使用 DECIMAL 类型\n"
        f"5. 根据业务场景给出合理的索引建议\n"
        f"6. VARCHAR 类型必须给出 length 值\n"
    )


def _call_llm_for_schema(prompt: str) -> dict:
    """调用已配置的 LLM 生成 schema JSON。"""
    cfg = sqlite_repo.get_active_llm_config()
    if not cfg:
        raise RuntimeError("请先在 AI 设置中配置并启用模型")
    if not cfg.get("base_url"):
        raise RuntimeError("请先在 AI 设置中填写 base_url")

    from app.api.llm import _is_local_free_provider, _resolve_effective_api_key, _build_llm_headers, _extract_first_json_object, _consume_cloud_demo_quota_if_needed

    if (not _is_local_free_provider(cfg)) and (not _resolve_effective_api_key(cfg)):
        raise RuntimeError("请先在 AI 设置中配置 API Key")

    quota = _consume_cloud_demo_quota_if_needed(cfg)
    if not quota.get("ok"):
        raise RuntimeError(quota.get("error", "额度不足"))

    import requests
    base_url = cfg["base_url"].rstrip("/")
    model = cfg.get("model", "Qwen/Qwen2.5-7B-Instruct")

    resp = requests.post(
        f"{base_url}/chat/completions",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "你是数据库表结构设计助手。只输出一个 JSON 对象。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        },
        headers=_build_llm_headers(cfg),
        timeout=(12, 90),
    )
    if resp.status_code != 200:
        raise RuntimeError(f"LLM 返回错误：HTTP {resp.status_code}")

    data = resp.json()
    content = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
    parsed = _extract_first_json_object(content)
    if not parsed:
        raise RuntimeError("模型未返回可解析的 JSON，请重试")
    return parsed


@router.post("/ai-generate")
async def ai_generate_schema(body: AIGenerateRequest):
    """AI 辅助生成表结构：用户提供描述（+可选 JSON/表格样例），LLM 或规则生成。"""
    if not body.description.strip():
        return {"error": "请提供表描述信息"}

    # 优先尝试规则解析 JSON 或 Markdown 表格样例
    fields = []
    indexes = []
    if body.json_sample.strip():
        fields = _infer_json_fields(body.json_sample.strip())
        if not fields:
            fields = _parse_markdown_table(body.json_sample.strip())

    if fields:
        return {
            "fields": fields,
            "indexes": indexes,
            "source": "rule_infer",
        }

    # 无样例或解析失败，走 LLM
    try:
        prompt = _build_llm_schema_prompt(body)
        result = _call_llm_for_schema(prompt)
        fields = result.get("fields", [])
        indexes = result.get("indexes", [])
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"AI 生成失败: {e}"}

    return {"fields": fields, "indexes": indexes, "source": "llm"}


@router.post("/ai-infer-from-json")
async def ai_infer_from_json(body: AIInferFromJsonRequest):
    """从 JSON 数据样例或 Markdown 表格推断字段结构。"""
    if not body.json_sample.strip():
        return {"error": "请提供 JSON 数据样例或表格文本"}

    sample = body.json_sample.strip()

    # 1. 尝试 JSON 解析
    fields = _infer_json_fields(sample)
    if fields:
        return {"fields": fields, "indexes": [], "source": "json_infer"}

    # 2. 尝试 Markdown/ASCII 表格解析
    fields = _parse_markdown_table(sample)
    if fields:
        return {"fields": fields, "indexes": [], "source": "table_infer"}

    return {"error": "无法从输入内容中推断字段结构。请提供 JSON 数据样例或字段定义表格。"}


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
