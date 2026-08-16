"""复权因子查询 API — 查询 DuckDB 中的复权因子数据。"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import duckdb
import os

router = APIRouter(tags=["adj-factors"])

# 默认的 DuckDB 路径
DEFAULT_DB_PATH = "D:/data/stock_adj.duckdb"


@router.get("/")
def list_adj_factors(
    code: Optional[str] = Query(None, description="股票代码，如 000001"),
    limit: int = Query(100, ge=1, le=10000, description="返回条数限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db_path: Optional[str] = Query(None, description="DuckDB 文件路径"),
):
    """查询复权因子数据。

    返回字段：code（股票代码）, dt（日期）, fore（前复权因子）, back（后复权因子）
    """
    path = db_path or DEFAULT_DB_PATH

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"数据库文件不存在: {path}")

    try:
        conn = duckdb.connect(path, read_only=True)

        # 检查表是否存在
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        if "adj_factor" not in table_names:
            conn.close()
            raise HTTPException(
                status_code=404,
                detail="adj_factor 表不存在，请先执行示例12工作流生成复权因子数据"
            )

        # 构建查询
        if code:
            sql = f"""
                SELECT code, dt, fore, back
                FROM adj_factor
                WHERE code = '{code}'
                ORDER BY dt DESC
                LIMIT {limit} OFFSET {offset}
            """
        else:
            sql = f"""
                SELECT code, dt, fore, back
                FROM adj_factor
                ORDER BY code, dt DESC
                LIMIT {limit} OFFSET {offset}
            """

        result = conn.execute(sql).fetchall()
        conn.close()

        # 转换为字典列表
        data = [
            {
                "code": row[0],
                "dt": str(row[1]),
                "fore": float(row[2]) if row[2] is not None else None,
                "back": float(row[3]) if row[3] is not None else None,
            }
            for row in result
        ]

        return {
            "success": True,
            "total": len(data),
            "data": data,
            "db_path": path,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/codes")
def list_codes(db_path: Optional[str] = Query(None, description="DuckDB 文件路径")):
    """获取所有有复权因子数据的股票代码列表。"""
    path = db_path or DEFAULT_DB_PATH

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"数据库文件不存在: {path}")

    try:
        conn = duckdb.connect(path, read_only=True)

        # 检查表是否存在
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        if "adj_factor" not in table_names:
            conn.close()
            return {"success": True, "codes": []}

        result = conn.execute("""
            SELECT DISTINCT code, MIN(dt) as start_date, MAX(dt) as end_date, COUNT(*) as cnt
            FROM adj_factor
            GROUP BY code
            ORDER BY code
        """).fetchall()

        conn.close()

        codes = [
            {
                "code": row[0],
                "start_date": str(row[1]),
                "end_date": str(row[2]),
                "count": row[3],
            }
            for row in result
        ]

        return {"success": True, "codes": codes}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/stats")
def get_stats(db_path: Optional[str] = Query(None, description="DuckDB 文件路径")):
    """获取复权因子数据的统计信息。"""
    path = db_path or DEFAULT_DB_PATH

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"数据库文件不存在: {path}")

    try:
        conn = duckdb.connect(path, read_only=True)

        # 检查表是否存在
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        if "adj_factor" not in table_names:
            conn.close()
            return {
                "success": True,
                "total_records": 0,
                "total_codes": 0,
                "message": "adj_factor 表不存在",
            }

        result = conn.execute("""
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT code) as total_codes,
                MIN(dt) as earliest_date,
                MAX(dt) as latest_date
            FROM adj_factor
        """).fetchone()

        conn.close()

        return {
            "success": True,
            "total_records": result[0],
            "total_codes": result[1],
            "earliest_date": str(result[2]) if result[2] else None,
            "latest_date": str(result[3]) if result[3] else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
