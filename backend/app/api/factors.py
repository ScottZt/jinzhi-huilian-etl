"""因子库查询 API — 查询 DuckDB 中的因子数据。

支持：
- 列出已注册因子
- 查询单因子数据
- 批量查询多因子（宽表 JOIN）
- 因子统计信息
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import duckdb
import os

router = APIRouter(tags=["factors"])

# 默认因子库路径
DEFAULT_FACTOR_DB = "D:/data/factor_data.duckdb"


def _connect(db_path: Optional[str] = None, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """连接 DuckDB 因子库。"""
    path = db_path or DEFAULT_FACTOR_DB
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"因子库不存在: {path}")
    return duckdb.connect(path, read_only=read_only)


@router.get("/registry")
def list_factors(
    factor_type: Optional[str] = Query(None, description="因子类型筛选（L0/L1/L2/L3）"),
    db_path: Optional[str] = Query(None, description="因子库路径"),
):
    """列出所有已注册因子。"""
    conn = _connect(db_path)
    try:
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        # 检查是否有 factor_registry 表
        if "factor_registry" not in table_names:
            conn.close()
            return {"success": True, "factors": [], "message": "尚未注册任何因子"}

        sql = "SELECT factor_id, factor_name, factor_type, compute_type, params_json, source_column FROM factor_registry"
        if factor_type:
            sql += f" WHERE factor_type = '{factor_type}'"
        sql += " ORDER BY factor_id"

        rows = conn.execute(sql).fetchall()
        conn.close()

        factors = []
        for r in rows:
            factors.append({
                "factor_id": r[0],
                "factor_name": r[1],
                "factor_type": r[2],
                "compute_type": r[3],
                "params_json": r[4],
                "source_column": r[5],
            })

        return {"success": True, "factors": factors, "total": len(factors)}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/query")
def query_factor(
    factor_id: str = Query(..., description="因子ID，如 ma_5"),
    codes: Optional[str] = Query(None, description="股票代码（逗号分隔），如 000001,600000"),
    start_date: Optional[str] = Query(None, description="开始日期，如 2024-01-01"),
    end_date: Optional[str] = Query(None, description="结束日期，如 2024-12-31"),
    limit: int = Query(1000, ge=1, le=100000, description="返回条数限制"),
    db_path: Optional[str] = Query(None, description="因子库路径"),
):
    """查询单个因子的数据。"""
    table_name = f"factor_{factor_id}"

    conn = _connect(db_path)
    try:
        # 检查表是否存在
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        if table_name not in table_names:
            conn.close()
            raise HTTPException(status_code=404, detail=f"因子表 {table_name} 不存在")

        # 构建查询
        where_clauses = []
        if codes:
            code_list = ",".join([f"'{c.strip()}'" for c in codes.split(",")])
            where_clauses.append(f"code IN ({code_list})")
        if start_date:
            where_clauses.append(f"dt >= '{start_date}'")
        if end_date:
            where_clauses.append(f"dt <= '{end_date}'")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        sql = f"""
            SELECT code, dt, factor_value
            FROM {table_name}
            WHERE {where_sql}
            ORDER BY code, dt
            LIMIT {limit}
        """

        rows = conn.execute(sql).fetchall()
        conn.close()

        data = [
            {"code": r[0], "dt": str(r[1]), "factor_value": float(r[2]) if r[2] is not None else None}
            for r in rows
        ]

        return {
            "success": True,
            "factor_id": factor_id,
            "total": len(data),
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/query/multi")
def query_multi_factors(
    factor_ids: str = Query(..., description="因子ID列表（逗号分隔），如 ma_5,ma_20,rsi_14"),
    codes: str = Query(..., description="股票代码（逗号分隔）"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    limit: int = Query(1000, ge=1, le=100000, description="返回条数限制"),
    db_path: Optional[str] = Query(None, description="因子库路径"),
):
    """批量查询多因子，返回宽表格式（每行包含所有因子值）。"""
    ids = [fid.strip() for fid in factor_ids.split(",") if fid.strip()]
    code_list = [c.strip() for c in codes.split(",") if c.strip()]

    if not ids:
        raise HTTPException(status_code=400, detail="factor_ids 不能为空")
    if not code_list:
        raise HTTPException(status_code=400, detail="codes 不能为空")

    conn = _connect(db_path)
    try:
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        # 检查所有因子表是否存在
        missing = []
        for fid in ids:
            tname = f"factor_{fid}"
            if tname not in table_names:
                missing.append(fid)
        if missing:
            conn.close()
            raise HTTPException(status_code=404, detail=f"因子表不存在: {', '.join(missing)}")

        # 构建 JOIN 查询
        code_in = ",".join([f"'{c}'" for c in code_list])
        base_table = f"factor_{ids[0]}"

        select_cols = [f"t0.code", f"t0.dt"]
        joins = []
        for i, fid in enumerate(ids):
            tname = f"factor_{fid}"
            alias = f"t{i}"
            select_cols.append(f"{alias}.factor_value AS {fid}")
            if i > 0:
                joins.append(f"INNER JOIN {tname} {alias} ON t0.code = {alias}.code AND t0.dt = {alias}.dt")

        where_clauses = [f"t0.code IN ({code_in})"]
        if start_date:
            where_clauses.append(f"t0.dt >= '{start_date}'")
        if end_date:
            where_clauses.append(f"t0.dt <= '{end_date}'")

        sql = f"""
            SELECT {', '.join(select_cols)}
            FROM {base_table} t0
            {' '.join(joins)}
            WHERE {' AND '.join(where_clauses)}
            ORDER BY t0.code, t0.dt
            LIMIT {limit}
        """

        rows = conn.execute(sql).fetchall()
        conn.close()

        data = []
        for r in rows:
            row = {"code": r[0], "dt": str(r[1])}
            for i, fid in enumerate(ids):
                row[fid] = float(r[i + 2]) if r[i + 2] is not None else None
            data.append(row)

        return {
            "success": True,
            "factor_ids": ids,
            "total": len(data),
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/stats")
def get_stats(
    db_path: Optional[str] = Query(None, description="因子库路径"),
):
    """获取因子库统计信息。"""
    conn = _connect(db_path)
    try:
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        factor_tables = [t for t in table_names if t.startswith("factor_")]

        stats = []
        for tname in factor_tables:
            try:
                row = conn.execute(f"""
                    SELECT
                        COUNT(*) as total_records,
                        COUNT(DISTINCT code) as total_codes,
                        MIN(dt) as earliest_date,
                        MAX(dt) as latest_date
                    FROM {tname}
                """).fetchone()
                stats.append({
                    "table": tname,
                    "factor_id": tname.replace("factor_", ""),
                    "total_records": row[0],
                    "total_codes": row[1],
                    "earliest_date": str(row[2]) if row[2] else None,
                    "latest_date": str(row[3]) if row[3] else None,
                })
            except Exception:
                continue

        conn.close()
        return {
            "success": True,
            "total_factors": len(factor_tables),
            "total_records": sum(s["total_records"] for s in stats),
            "factors": stats,
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/codes")
def list_factor_codes(
    factor_id: str = Query(..., description="因子ID"),
    db_path: Optional[str] = Query(None, description="因子库路径"),
):
    """获取某个因子包含的所有股票代码。"""
    table_name = f"factor_{factor_id}"

    conn = _connect(db_path)
    try:
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        if table_name not in table_names:
            conn.close()
            raise HTTPException(status_code=404, detail=f"因子表 {table_name} 不存在")

        rows = conn.execute(f"""
            SELECT DISTINCT code, MIN(dt) as start_date, MAX(dt) as end_date, COUNT(*) as cnt
            FROM {table_name}
            GROUP BY code
            ORDER BY code
        """).fetchall()

        conn.close()

        codes = [
            {
                "code": r[0],
                "start_date": str(r[1]),
                "end_date": str(r[2]),
                "count": r[3],
            }
            for r in rows
        ]

        return {"success": True, "codes": codes, "total": len(codes)}
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.delete("/delete")
def delete_factor(
    factor_id: str = Query(..., description="因子ID"),
    db_path: Optional[str] = Query(None, description="因子库路径"),
):
    """删除指定因子（同时删除数据表和注册信息）。"""
    import re
    table_name = f"factor_{factor_id}"

    # 校验因子ID格式
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', factor_id):
        raise HTTPException(status_code=400, detail=f"因子ID格式不合法: {factor_id}")

    conn = _connect(db_path, read_only=False)
    try:
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        deleted_table = False
        deleted_registry = False

        # 删除因子数据表
        if table_name in table_names:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            deleted_table = True

        # 删除注册信息
        if "factor_registry" in table_names:
            conn.execute(f"DELETE FROM factor_registry WHERE factor_id = '{factor_id}'")
            deleted_registry = True

        conn.close()

        if not deleted_table and not deleted_registry:
            raise HTTPException(status_code=404, detail=f"因子 {factor_id} 不存在")

        return {
            "success": True,
            "factor_id": factor_id,
            "deleted_table": deleted_table,
            "deleted_registry": deleted_registry,
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
