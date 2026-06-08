from fastapi import APIRouter
from typing import List, Dict, Any
from pydantic import BaseModel

from app.core.transform_engine import get_transform_engine, TransformEngine
from app.core.secure_exec import validate_code_ast

router = APIRouter()
transform_engine = get_transform_engine()


class TransformRule(BaseModel):
    type: str
    source_field: str = None
    target_field: str = None
    expression: str = None
    func_name: str = None
    func_args: List[Any] = []


class FieldMapping(BaseModel):
    source_field: str
    target_field: str = None
    transform_expression: str = None
    transform_type: str = None
    transform_func: str = None
    transform_args: List[Any] = []


class CustomFuncRegister(BaseModel):
    name: str
    code: str


@router.get("/builtins")
async def list_builtin_funcs():
    return transform_engine.list_builtin_funcs()


@router.post("/preview")
async def preview_transform(data: Dict[str, Any]):
    """
    Preview a transformation on sample data.
    data: { "columns": [...], "rows": [...], "rules": [...] }
    """
    import pandas as pd
    try:
        df = pd.DataFrame(data.get("rows", []))
        for i, col in enumerate(data.get("columns", [])):
            if col not in df.columns:
                df[col] = None

        rules = data.get("rules", [])
        df_result = transform_engine.transform(df, rules)
        return {
            "columns": df_result.columns.tolist(),
            "preview": df_result.head(20).to_dict(orient="records"),
            "shape": list(df_result.shape),
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/validate-expression")
async def validate_expression(data: Dict[str, Any]):
    expr = data.get("expression", "")
    expr_type = data.get("type", "python")
    sample_data = data.get("sample_data")
    import pandas as pd
    df_sample = pd.DataFrame(sample_data) if sample_data else None
    valid, msg = transform_engine.validate_expression(expr, expr_type, df_sample)
    return {"valid": valid, "message": msg}


@router.post("/custom-funcs")
async def register_custom_func(body: CustomFuncRegister):
    """Register a custom Python transformation function from source code."""
    # AST-level security validation before registration
    ok, err = validate_code_ast(body.code)
    if not ok:
        return {"success": False, "error": f"Code rejected: {err}"}
    try:
        local_ns = {}
        exec(body.code, {"__builtins__": {}}, local_ns)
        func = local_ns.get(body.name)
        if not func:
            return {"success": False, "error": f"Function '{body.name}' not found in code"}
        transform_engine.register_custom_func(body.name, func)
        return {"success": True, "message": f"Function '{body.name}' registered"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/custom-funcs/{name}")
async def unregister_custom_func(name: str):
    transform_engine.unregister_custom_func(name)
    return {"message": f"Function '{name}' unregistered"}


@router.get("/custom-funcs")
async def list_custom_funcs():
    return list(transform_engine._custom_funcs.keys())
