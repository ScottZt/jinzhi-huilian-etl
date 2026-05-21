from typing import Dict, List
from app.models.schema import TableSchema, FieldDefinition, FieldType

class SchemaManager:

    TYPE_MAPPING = {
        "mysql": {
            FieldType.VARCHAR: lambda f: f"VARCHAR({f.length or 255})",
            FieldType.CHAR: lambda f: f"CHAR({f.length or 10})",
            FieldType.DECIMAL: lambda f: f"DECIMAL({f.precision or 10},{f.scale or 2})",
            FieldType.FLOAT: lambda f: "FLOAT",
            FieldType.DOUBLE: lambda f: "DOUBLE",
            FieldType.INT: lambda f: "INT",
            FieldType.BIGINT: lambda f: "BIGINT",
            FieldType.DATETIME: lambda f: "DATETIME",
            FieldType.DATE: lambda f: "DATE",
            FieldType.TEXT: lambda f: "TEXT",
            FieldType.JSON: lambda f: "JSON",
        },
        "postgresql": {
            FieldType.VARCHAR: lambda f: f"VARCHAR({f.length or 255})",
            FieldType.CHAR: lambda f: f"CHAR({f.length or 10})",
            FieldType.DECIMAL: lambda f: f"NUMERIC({f.precision or 10},{f.scale or 2})",
            FieldType.FLOAT: lambda f: "REAL",
            FieldType.DOUBLE: lambda f: "DOUBLE PRECISION",
            FieldType.INT: lambda f: "INTEGER",
            FieldType.BIGINT: lambda f: "BIGINT",
            FieldType.DATETIME: lambda f: "TIMESTAMP",
            FieldType.DATE: lambda f: "DATE",
            FieldType.TEXT: lambda f: "TEXT",
            FieldType.JSON: lambda f: "JSONB",
        },
        "duckdb": {
            FieldType.VARCHAR: lambda f: f"VARCHAR({f.length or 255})" if f.length else "VARCHAR",
            FieldType.CHAR: lambda f: f"CHAR({f.length or 10})",
            FieldType.DECIMAL: lambda f: f"DECIMAL({f.precision or 10},{f.scale or 2})",
            FieldType.FLOAT: lambda f: "FLOAT",
            FieldType.DOUBLE: lambda f: "DOUBLE",
            FieldType.INT: lambda f: "INTEGER",
            FieldType.BIGINT: lambda f: "BIGINT",
            FieldType.DATETIME: lambda f: "TIMESTAMP",
            FieldType.DATE: lambda f: "DATE",
            FieldType.TEXT: lambda f: "VARCHAR",
            FieldType.JSON: lambda f: "JSON",
        },
        "clickhouse": {
            FieldType.VARCHAR: lambda f: f"String",
            FieldType.CHAR: lambda f: f"FixedString({f.length or 10})",
            FieldType.DECIMAL: lambda f: f"Decimal({f.precision or 10},{f.scale or 2})",
            FieldType.FLOAT: lambda f: "Float32",
            FieldType.DOUBLE: lambda f: "Float64",
            FieldType.INT: lambda f: "Int32",
            FieldType.BIGINT: lambda f: "Int64",
            FieldType.DATETIME: lambda f: "DateTime",
            FieldType.DATE: lambda f: "Date",
            FieldType.TEXT: lambda f: "String",
            FieldType.JSON: lambda f: "String",
        }
    }

    def generate_ddl(self, schema: TableSchema) -> str:
        db_type = schema.database_type.lower()
        if db_type not in self.TYPE_MAPPING:
            raise ValueError(f"Unsupported database type: {db_type}")

        type_map = self.TYPE_MAPPING[db_type]
        field_defs = []
        primary_keys = []

        for field in schema.fields:
            field_type = type_map[field.type](field)
            null_constraint = "" if field.nullable else " NOT NULL"
            field_def = f"  {field.name} {field_type}{null_constraint}"
            field_defs.append(field_def)

            if field.primary_key:
                primary_keys.append(field.name)

        if primary_keys:
            field_defs.append(f"  PRIMARY KEY ({', '.join(primary_keys)})")

        ddl = f"CREATE TABLE {schema.table_name} (\n"
        ddl += ",\n".join(field_defs)
        ddl += "\n);"

        # Add column comments (database-specific syntax)
        for field in schema.fields:
            if field.description:
                if db_type == "mysql":
                    ddl += f"\nALTER TABLE {schema.table_name} MODIFY COLUMN {field.name} {type_map[field.type](field)} COMMENT '{field.description}';"
                elif db_type == "postgresql":
                    ddl += f"\nCOMMENT ON COLUMN {schema.table_name}.{field.name} IS '{field.description}';"
                elif db_type == "duckdb":
                    ddl += f"\nCOMMENT ON COLUMN {schema.table_name}.{field.name} IS '{field.description}';"
                elif db_type == "clickhouse":
                    ddl += f"\nALTER TABLE {schema.table_name} COMMENT COLUMN {field.name} '{field.description}';"

        for index in schema.indexes:
            index_type = "UNIQUE INDEX" if index.unique else "INDEX"
            ddl += f"\n\nCREATE {index_type} {index.name} ON {schema.table_name} ({', '.join(index.fields)});"

        return ddl

    def validate_schema(self, schema: TableSchema) -> List[str]:
        errors = []

        if not schema.table_name:
            errors.append("Table name is required")

        if not schema.fields:
            errors.append("At least one field is required")

        field_names = set()
        for field in schema.fields:
            if field.name in field_names:
                errors.append(f"Duplicate field name: {field.name}")
            field_names.add(field.name)

            if field.type in [FieldType.VARCHAR, FieldType.CHAR] and not field.length:
                errors.append(f"Field {field.name}: length is required for {field.type}")

            if field.type == FieldType.DECIMAL:
                if not field.precision:
                    errors.append(f"Field {field.name}: precision is required for DECIMAL")
                if not field.scale:
                    errors.append(f"Field {field.name}: scale is required for DECIMAL")

        return errors
