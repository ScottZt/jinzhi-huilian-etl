"""
后复权处理工作流 - 工程化版本

通过 REST API 注册：
  - Workflow "后复权处理"：从 quantifydata.duckdb 读未复权 K 线，
    同时计算前复权/后复权，写入 quantifydata_adj.duckdb
  - Pipeline  "后复权数据流"：封装上述工作流，支持定时调度

每种频率产出 3 张表：
  - dat_xxx_raw  : 未复权（字段名: open, high, low, close）
  - dat_xxx_qfq  : 前复权（字段名: open_qfq, high_qfq, low_qfq, close_qfq）
  - dat_xxx_hfq  : 后复权（字段名: open_hfq, high_hfq, low_hfq, close_hfq）

复权因子来自 baostock（直接返回 fore + back 两个因子）。

分阶段实施（--stage 1~7），避免一次性处理 33 亿行 1min 数据导致长时间阻塞。

用法：
  cd backend
  python examples/hfq_full_setup.py              # 默认阶段 1（只跑 dat_day）
  python examples/hfq_full_setup.py --stage 2    # 扩展到 dat_day + dat_60mins
  python examples/hfq_full_setup.py --stage 7    # 全部 7 张表
  python examples/hfq_full_setup.py --dry-run    # 只打印工作流 JSON，不注册
"""

import argparse
import httpx
import json
import sys
import textwrap

# ============================================================================
# 配置
# ============================================================================

BASE = "http://127.0.0.1:8080"
SOURCE_DB = "C:/duckdb/quantifydata.duckdb"
TARGET_DB = "C:/duckdb/quantifydata_adj.duckdb"

STAGES = {
    1: ["dat_day"],
    2: ["dat_day", "dat_60mins"],
    3: ["dat_day", "dat_60mins", "dat_30mins"],
    4: ["dat_day", "dat_60mins", "dat_30mins", "dat_15mins"],
    5: ["dat_day", "dat_60mins", "dat_30mins", "dat_15mins", "dat_10mins"],
    6: ["dat_day", "dat_60mins", "dat_30mins", "dat_15mins", "dat_10mins", "dat_5mins"],
    7: ["dat_day", "dat_60mins", "dat_30mins", "dat_15mins", "dat_10mins", "dat_5mins", "dat_1mins"],
}

BATCH_SIZE = 500_000


# ============================================================================
# custom_python 代码模板
# ============================================================================

CUSTOM_PYTHON_TEMPLATE = textwrap.dedent(r'''
# ========== 配置（由 setup 脚本注入） ==========
SOURCE_DB = {source_db!r}
TARGET_DB = {target_db!r}
TABLES = {tables_repr}
BATCH_SIZE = {batch_size}

# ========== 主逻辑 ==========

def process(df):
    """
    custom_python 节点入口。
    接管全部 I/O：自连 DuckDB，逐表逐 code 处理，直接写入目标库。
    返回 1 行状态 DataFrame（不传大数据）。
    """
    import duckdb
    import pandas as pd
    import numpy as np
    import baostock as bs
    import gc
    from datetime import datetime

    print(f"[START] 后复权处理 - {{datetime.now().isoformat()}}")
    print(f"[CONFIG] 源库: {{SOURCE_DB}}")
    print(f"[CONFIG] 目标库: {{TARGET_DB}}")
    print(f"[CONFIG] 表: {{TABLES}}")

    # ========== 工具函数 ==========

    def normalize_code(c):
        """统一为 '000001.SZ' 大写格式"""
        c = str(c).strip().upper()
        if '.' in c:
            return c
        if len(c) == 6 and c.isdigit():
            market = 'SH' if c.startswith(('6', '9')) else 'SZ'
            return f"{{c}}.{{market}}"
        return c

    def to_baostock_code(c):
        """'000001.SZ' -> 'sz.000001' 或 '000001' -> 'sz.000001'"""
        c = str(c).strip().upper()
        if '.' in c:
            code, market = c.split('.')
            return f"{{market.lower()}}.{{code}}"
        c = c.zfill(6)
        return ('sh.' + c) if c.startswith(('6', '9')) else ('sz.' + c)

    def to_bare_code(c):
        """'000001.SZ' -> '000001'"""
        c = str(c).strip()
        if '.' in c:
            return c.split('.')[0]
        return c.zfill(6)

    # ========== 1) 收集所有 code ==========

    src_ro = duckdb.connect(SOURCE_DB, read_only=True)
    all_codes = set()
    for tbl in TABLES:
        try:
            rows = src_ro.execute(f"SELECT DISTINCT code FROM {{tbl}}").fetchall()
            all_codes.update(normalize_code(r[0]) for r in rows)
        except Exception as e:
            print(f"[WARN] 表 {{tbl}} 查询失败：{{e}}")
    src_ro.close()
    all_codes = sorted(all_codes)
    print(f"[INFO] 共 {{len(all_codes)}} 只标的待处理")

    # ========== 2) 拉取 baostock 复权因子 ==========

    print("[INFO] 连接 baostock 拉取复权因子...")
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f"baostock 登录失败: {{lg.error_msg}}")

    # 确定日期范围（跨所有表取最宽范围）
    src_ro = duckdb.connect(SOURCE_DB, read_only=True)
    global_min_date = '2010-01-01'
    global_max_date = '2030-12-31'
    for tbl in TABLES:
        try:
            row = src_ro.execute(f"""
                SELECT MIN(trade_time)::DATE as min_d, MAX(trade_time)::DATE as max_d
                FROM {{tbl}}
            """).fetchone()
            if row[0]:
                d = str(row[0])
                if d > global_min_date:
                    global_min_date = d
            if row[1]:
                d = str(row[1])
                if d < global_max_date:
                    global_max_date = d
        except Exception:
            pass
    src_ro.close()

    # 对每只股票拉取复权因子
    factor_cache = {{}}  # {{bare_code: DataFrame[dt, fore, back]}}
    total = len(all_codes)
    for i, code in enumerate(all_codes, 1):
        bare = to_bare_code(code)
        try:
            rs = bs.query_adjust_factor(
                code=to_baostock_code(code),
                start_date=global_min_date,
                end_date=global_max_date,
            )
            rows = []
            while rs.next():
                r = rs.get_row_data()
                # r[1]=dividOperateDate, r[2]=foreAdjustFactor, r[3]=backAdjustFactor
                if r[2] and r[2] != '' and r[3] and r[3] != '':
                    rows.append({{'dt': r[1], 'fore': float(r[2]), 'back': float(r[3])}})
            if rows:
                fdf = pd.DataFrame(rows)
                fdf['dt'] = pd.to_datetime(fdf['dt'])
                factor_cache[bare] = fdf
        except Exception as e:
            print(f"[WARN] {{code}} 因子拉取失败：{{e}}")
        if i % 100 == 0 or i == total:
            print(f"[INFO] baostock 拉取进度：{{i}} / {{total}}")
    bs.logout()
    print(f"[INFO] baostock 加载复权因子：{{len(factor_cache)}} / {{total}} 只标的")

    # ========== 3) 逐表逐 code 处理，写入目标库 ==========

    tgt = duckdb.connect(TARGET_DB)
    summary = []

    for tbl in TABLES:
        tbl_raw = tbl + '_raw'
        tbl_qfq = tbl + '_qfq'
        tbl_hfq = tbl + '_hfq'
        print(f"\n[PROCESS] {{tbl}} -> {{tbl_raw}} / {{tbl_qfq}} / {{tbl_hfq}}")

        # 建目标表
        tgt.execute(f"""
            CREATE TABLE IF NOT EXISTS {{tbl_raw}} (
                code VARCHAR, trade_time TIMESTAMPTZ,
                open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
                vol BIGINT, amount DOUBLE
            )
        """)
        tgt.execute(f"""
            CREATE TABLE IF NOT EXISTS {{tbl_qfq}} (
                code VARCHAR, trade_time TIMESTAMPTZ,
                open_qfq DOUBLE, high_qfq DOUBLE, low_qfq DOUBLE, close_qfq DOUBLE,
                vol BIGINT, amount DOUBLE
            )
        """)
        tgt.execute(f"""
            CREATE TABLE IF NOT EXISTS {{tbl_hfq}} (
                code VARCHAR, trade_time TIMESTAMPTZ,
                open_hfq DOUBLE, high_hfq DOUBLE, low_hfq DOUBLE, close_hfq DOUBLE,
                vol BIGINT, amount DOUBLE
            )
        """)

        # 全量重算：清空目标表
        tgt.execute(f"DELETE FROM {{tbl_raw}}")
        tgt.execute(f"DELETE FROM {{tbl_qfq}}")
        tgt.execute(f"DELETE FROM {{tbl_hfq}}")

        src = duckdb.connect(SOURCE_DB, read_only=True)
        total_raw = 0
        total_qfq = 0
        total_hfq = 0
        code_ok = 0
        code_fail = 0

        for i, code in enumerate(all_codes, 1):
            try:
                chunk = src.execute(f"""
                    SELECT code, trade_time, open, high, low, close, vol, amount
                    FROM {{tbl}}
                    WHERE code = ?
                    ORDER BY trade_time
                """, [code]).fetchdf()
            except Exception as e:
                print(f"[WARN] {{code}} 读取失败：{{e}}")
                code_fail += 1
                continue

            if chunk.empty:
                continue

            # 类型转换（分钟级表字段可能全是 VARCHAR）
            for c in ['open', 'high', 'low', 'close', 'amount']:
                if chunk[c].dtype == object:
                    chunk[c] = pd.to_numeric(chunk[c], errors='coerce')
            if chunk['vol'].dtype == object:
                chunk['vol'] = pd.to_numeric(chunk['vol'], errors='coerce').astype('Int64')

            bare = to_bare_code(code)
            fdf = factor_cache.get(bare)

            if fdf is not None and not fdf.empty:
                # 把因子广播到分钟级：提取日期作为合并键
                chunk['_date'] = (
                    pd.to_datetime(chunk['trade_time'], utc=True)
                    .dt.tz_convert('Asia/Shanghai')
                    .dt.tz_localize(None)
                    .dt.normalize()
                )
                fdf_sorted = fdf.sort_values('dt')

                chunk = chunk.sort_values('_date')
                chunk = pd.merge_asof(
                    chunk,
                    fdf_sorted[['dt', 'fore', 'back']],
                    left_on='_date',
                    right_on='dt',
                    direction='backward',
                )
                # 填充 NaN（早于第一个因子日期的行用第一个因子值）
                first_fore = fdf_sorted['fore'].iloc[0]
                first_back = fdf_sorted['back'].iloc[0]
                chunk['fore'] = chunk['fore'].fillna(first_fore)
                chunk['back'] = chunk['back'].fillna(first_back)
                chunk = chunk.drop(columns=['_date', 'dt'])
            else:
                chunk['fore'] = 1.0
                chunk['back'] = 1.0

            # 计算前复权价
            for c in ['open', 'high', 'low', 'close']:
                chunk[c + '_qfq'] = (chunk[c] * chunk['fore']).round(3)

            # 计算后复权价
            for c in ['open', 'high', 'low', 'close']:
                chunk[c + '_hfq'] = (chunk[c] * chunk['back']).round(3)

            # 写入未复权表
            try:
                tgt.execute(f"""
                    INSERT INTO {{tbl_raw}}
                    SELECT code, trade_time, open, high, low, close,
                           vol::BIGINT as vol, amount
                    FROM chunk
                """)
                total_raw += len(chunk)
            except Exception as e:
                print(f"[WARN] {{code}} 未复权写入失败：{{e}}")

            # 写入前复权表
            try:
                tgt.execute(f"""
                    INSERT INTO {{tbl_qfq}}
                    SELECT code, trade_time, open_qfq, high_qfq, low_qfq, close_qfq,
                           vol::BIGINT as vol, amount
                    FROM chunk
                """)
                total_qfq += len(chunk)
            except Exception as e:
                print(f"[WARN] {{code}} 前复权写入失败：{{e}}")

            # 写入后复权表
            try:
                tgt.execute(f"""
                    INSERT INTO {{tbl_hfq}}
                    SELECT code, trade_time, open_hfq, high_hfq, low_hfq, close_hfq,
                           vol::BIGINT as vol, amount
                    FROM chunk
                """)
                total_hfq += len(chunk)
                code_ok += 1
            except Exception as e:
                print(f"[WARN] {{code}} 后复权写入失败：{{e}}")
                code_fail += 1

            # 进度反馈
            if i % 200 == 0 or i == len(all_codes):
                print(f"  [PROGRESS] {{i}}/{{len(all_codes)}} 只标的, raw={{total_raw}} / qfq={{total_qfq}} / hfq={{total_hfq}} 行")

            del chunk
            if i % 100 == 0:
                gc.collect()

        src.close()
        summary.append(
            f"{{tbl}}: raw={{total_raw}} / qfq={{total_qfq}} / hfq={{total_hfq}} 行 ({{code_ok}} ok / {{code_fail}} fail)"
        )
        print(f"[DONE] {{summary[-1]}}")

    tgt.close()

    # 4) 返回 1 行状态
    result = pd.DataFrame([{{
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'tables_processed': len(TABLES),
        'detail': ' | '.join(summary),
    }}])
    print(f"\n[FINISH] {{datetime.now().isoformat()}}")
    for s in summary:
        print(f"  {{s}}")
    return result
''').strip()


# ============================================================================
# 工作流 / Pipeline 构建
# ============================================================================

def build_workflow_json(tables):
    code_str = CUSTOM_PYTHON_TEMPLATE.format(
        source_db=SOURCE_DB,
        target_db=TARGET_DB,
        tables_repr=tables,
        batch_size=BATCH_SIZE,
    )
    return {
        "nodes": [
            {
                "id": "n1",
                "name": "后复权计算（含前复权+未复权）",
                "type": "custom_python",
                "parameters": {"code": code_str},
            }
        ],
        "connections": {},
    }


def build_pipeline_payload(workflow_id):
    return {
        "name": "后复权数据流",
        "description": "定时把未复权 K 线处理为前复权+后复权+未复权三套数据，写入 quantifydata_adj.duckdb。",
        "enabled": False,
        "cron_expression": "0 18 * * *",
        "sources": [],
        "workflow": {"id": workflow_id},
        "target": None,
        "field_mappings": [],
        "batch_size": BATCH_SIZE,
        "on_duplicate": "replace",
    }


# ============================================================================
# API 调用
# ============================================================================

def check_server():
    try:
        r = httpx.get(f"{BASE}/api/workflows/", timeout=3)
        return r.status_code == 200
    except Exception as e:
        print(f"[ERROR] 无法连接后端服务 {BASE}: {e}")
        print("[HINT] 请先启动后端: cd backend && python run_server.py")
        return False


def find_existing_workflow(name):
    r = httpx.get(f"{BASE}/api/workflows/")
    if r.status_code != 200:
        return None
    for w in r.json():
        if w.get("name") == name:
            return w.get("id")
    return None


def find_existing_pipeline(name):
    r = httpx.get(f"{BASE}/api/pipelines/")
    if r.status_code != 200:
        return None
    for p in r.json():
        if p.get("name") == name:
            return p.get("id")
    return None


def register_workflow(name, description, workflow_json):
    existing_id = find_existing_workflow(name)
    payload = {"name": name, "description": description, "workflow_json": workflow_json}
    if existing_id:
        r = httpx.put(f"{BASE}/api/workflows/{existing_id}", json=payload, timeout=30)
        if r.status_code in (200, 201):
            print(f"[OK] 更新已有工作流: {name} (id={existing_id})")
            return existing_id
        print(f"[WARN] 更新失败 ({r.status_code})，尝试新建: {r.text[:200]}")
    r = httpx.post(f"{BASE}/api/workflows/", json=payload, timeout=30)
    if r.status_code in (200, 201):
        data = r.json()
        wf_id = data.get("id") or data.get("workflow_id")
        print(f"[OK] 创建工作流: {name} (id={wf_id})")
        return wf_id
    print(f"[ERROR] 创建工作流失败 ({r.status_code}): {r.text[:300]}")
    return None


def register_pipeline(payload):
    name = payload["name"]
    existing_id = find_existing_pipeline(name)
    if existing_id:
        r = httpx.put(f"{BASE}/api/pipelines/{existing_id}", json=payload, timeout=30)
        if r.status_code in (200, 201):
            print(f"[OK] 更新已有 Pipeline: {name} (id={existing_id})")
            return existing_id
        print(f"[WARN] 更新失败 ({r.status_code})，尝试新建: {r.text[:200]}")
    r = httpx.post(f"{BASE}/api/pipelines/", json=payload, timeout=30)
    if r.status_code in (200, 201):
        data = r.json()
        pl_id = data.get("id") or data.get("pipeline_id")
        print(f"[OK] 创建 Pipeline: {name} (id={pl_id})")
        return pl_id
    print(f"[ERROR] 创建 Pipeline 失败 ({r.status_code}): {r.text[:300]}")
    return None


# ============================================================================
# 主流程
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="后复权处理工作流初始化")
    parser.add_argument(
        "--stage", type=int, choices=sorted(STAGES.keys()), default=1,
        help="实施阶段：1=只跑 dat_day，7=全部 7 张表。默认 1",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印工作流 JSON 概要，不注册")
    args = parser.parse_args()

    tables = STAGES[args.stage]
    print("=" * 70)
    print("  后复权处理工作流 - 初始化")
    print("=" * 70)
    print(f"  阶段: {args.stage} / 共 {len(STAGES)} 阶段")
    print(f"  待处理表: {tables}")
    print(f"  源库: {SOURCE_DB}")
    print(f"  目标库: {TARGET_DB}")
    print(f"  复权因子: baostock (fore + back)")
    print(f"  输出: 每种频率 3 张表 (_raw / _qfq / _hfq)")
    print("=" * 70)

    wf_json = build_workflow_json(tables)
    print(f"\n[INFO] 工作流节点数: {len(wf_json['nodes'])}")
    print(f"[INFO] custom_python 代码长度: {len(wf_json['nodes'][0]['parameters']['code'])} 字符")

    if args.dry_run:
        print("\n[DRY-RUN] 工作流 JSON 概要:")
        preview = dict(wf_json)
        preview["nodes"] = [
            {**n, "parameters": {"code": n["parameters"]["code"][:500] + "..."}}
            for n in wf_json["nodes"]
        ]
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    if not check_server():
        sys.exit(1)

    wf_id = register_workflow(
        name="后复权处理",
        description=f"从 {SOURCE_DB} 读取未复权 K 线，通过 baostock 获取复权因子，同时计算前复权/后复权/未复权，写入 {TARGET_DB}。阶段 {args.stage}: {tables}",
        workflow_json=wf_json,
    )
    if not wf_id:
        sys.exit(1)

    pl_payload = build_pipeline_payload(wf_id)
    pl_id = register_pipeline(pl_payload)
    if not pl_id:
        print("[WARN] Pipeline 注册失败，工作流仍可独立使用")

    print("\n" + "=" * 70)
    print("  初始化完成")
    print("=" * 70)
    print(f"  工作流 ID: {wf_id}")
    if pl_id:
        print(f"  Pipeline ID: {pl_id}")
    print(f"""
后续操作：
  1. 打开 ETL 工具前端，找到工作流 "后复权处理"
  2. 手动执行一次，观察输出状态
  3. 在 DuckDB 中验证数据：
     duckdb C:\\duckdb\\quantifydata_adj.duckdb
     > SHOW TABLES;
     > SELECT COUNT(*) FROM dat_day_raw;
     > SELECT COUNT(*) FROM dat_day_qfq;
     > SELECT COUNT(*) FROM dat_day_hfq;
     > SELECT * FROM dat_day_hfq WHERE code='000001.SZ' ORDER BY trade_time DESC LIMIT 5;
  4. 与通达信后复权/前复权价格抽样比对
  5. 确认准确性后，升级到下一阶段：
     python examples/hfq_full_setup.py --stage {min(args.stage + 1, 7)}
""")


if __name__ == "__main__":
    main()
