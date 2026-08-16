"""
后复权处理工作流 - 初始化脚本

通过 REST API 注册：
  - Workflow "后复权处理"：从 quantifydata.duckdb 读未复权 K 线，计算后复权，写入 quantifydata_hfq.duckdb
  - Pipeline  "后复权数据流"：封装上述工作流，支持定时调度

分阶段实施（--stage 1~7），避免一次性处理 33 亿行 1min 数据导致长时间阻塞。

用法：
  cd backend
  python examples/hfq_processing_setup.py              # 默认阶段 1（只跑 dat_day）
  python examples/hfq_processing_setup.py --stage 2    # 扩展到 dat_day + dat_60mins
  python examples/hfq_processing_setup.py --stage 7    # 全部 7 张表
  python examples/hfq_processing_setup.py --dry-run    # 只打印工作流 JSON，不注册
"""

import argparse
import httpx
import json
import sys
import textwrap

# ============================================================================
# 配置
# ============================================================================

# ETL 工具后端地址
BASE = "http://127.0.0.1:8080"

# 源库和目标库路径（Windows 反斜杠在 JSON 里需要转义，用正斜杠更安全）
SOURCE_DB = "C:/duckdb/quantifydata.duckdb"
TARGET_DB = "C:/duckdb/quantifydata_hfq.duckdb"

# 复权因子 Excel（可选，不存在则走 baostock 回落）
ADJ_FACTOR_EXCEL = "D:/data/adj_factor.xlsx"

# 7 个阶段，按数据量从小到大扩展
STAGES = {
    1: ["dat_day"],
    2: ["dat_day", "dat_60mins"],
    3: ["dat_day", "dat_60mins", "dat_30mins"],
    4: ["dat_day", "dat_60mins", "dat_30mins", "dat_15mins"],
    5: ["dat_day", "dat_60mins", "dat_30mins", "dat_15mins", "dat_10mins"],
    6: ["dat_day", "dat_60mins", "dat_30mins", "dat_15mins", "dat_10mins", "dat_5mins"],
    7: ["dat_day", "dat_60mins", "dat_30mins", "dat_15mins", "dat_10mins", "dat_5mins", "dat_1mins"],
}

# 单只标的的单批处理大小（分钟级数据单 code 最多 ~200 万行，一次吃下）
BATCH_SIZE = 500_000


# ============================================================================
# custom_python 代码模板
# ============================================================================
# 注意：custom_python 节点签名是 process(df)，params 不会传给 process。
# 所有配置硬编码在 code 字符串顶部常量里。
# 使用 {tables_repr} 占位符由 setup 脚本根据 stage 动态填充。

CUSTOM_PYTHON_TEMPLATE = textwrap.dedent(r'''
# ========== 配置（由 setup 脚本注入） ==========
SOURCE_DB = {source_db!r}
TARGET_DB = {target_db!r}
TABLES = {tables_repr}
ADJ_FACTOR_EXCEL = {adj_excel!r}
BATCH_SIZE = {batch_size}

# ========== 工具函数 ==========

def normalize_code(c):
    """统一为 '000001.SZ' 大写格式"""
    import re
    c = str(c).strip().upper()
    if '.' in c:
        return c
    if len(c) == 6 and c.isdigit():
        market = 'SH' if c.startswith(('6', '9')) else 'SZ'
        return f"{{c}}.{{market}}"
    return c


def to_baostock_code(c):
    """'000001.SZ' -> 'sz.000001'"""
    code, market = c.split('.')
    return f"{{market.lower()}}.{{code}}"


def load_adj_factors_from_excel(adj_excel, all_codes):
    """从 Excel 加载复权因子。返回 {{code: DataFrame[dt, back_factor]}}"""
    import pandas as pd, os
    if not adj_excel or not os.path.exists(adj_excel):
        return None
    try:
        adj = pd.read_excel(adj_excel, sheet_name='复权因子', parse_dates=['dt'])
    except Exception as e:
        print(f"[WARN] 读取 Excel 失败，回落到 baostock: {{e}}")
        return None
    adj['code'] = adj['code'].apply(normalize_code)
    cache = {{}}
    for code in all_codes:
        sub = adj[adj['code'] == code].sort_values('dt').copy()
        if not sub.empty:
            sub = sub.rename(columns={{'factor': 'back_factor'}})
            cache[code] = sub[['dt', 'back_factor']]
    print(f"[INFO] Excel 加载复权因子：{{len(cache)}} / {{len(all_codes)}} 只标的")
    return cache


def load_adj_factors_from_baostock(all_codes):
    """从 baostock 拉取后复权因子。返回 {{code: DataFrame[dt, back_factor]}}"""
    import pandas as pd
    import baostock as bs
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f"baostock 登录失败: {{lg.error_msg}}")
    cache = {{}}
    total = len(all_codes)
    for i, code in enumerate(all_codes, 1):
        try:
            rs = bs.query_adjust_factor(
                code=to_baostock_code(code),
                start_date='2000-01-01',
                end_date='2030-12-31',
            )
            rows = []
            while rs.next():
                r = rs.get_row_data()
                # r[1]=dividOperateDate, r[3]=backAdjustFactor
                if r[3] and r[3] != '':
                    rows.append({{'dt': r[1], 'back_factor': float(r[3])}})
            if rows:
                df = pd.DataFrame(rows)
                df['dt'] = pd.to_datetime(df['dt'])
                cache[code] = df
            if i % 100 == 0 or i == total:
                print(f"[INFO] baostock 拉取进度：{{i}} / {{total}}")
        except Exception as e:
            print(f"[WARN] {{code}} 因子拉取失败：{{e}}")
    bs.logout()
    print(f"[INFO] baostock 加载复权因子：{{len(cache)}} / {{total}} 只标的")
    return cache


def load_adj_factors(all_codes):
    """优先 Excel，不存在则回落 baostock"""
    cache = load_adj_factors_from_excel(ADJ_FACTOR_EXCEL, all_codes)
    if cache is not None:
        return cache
    print("[INFO] Excel 不可用，启用 baostock 拉取（可能需要 10-30 分钟）...")
    return load_adj_factors_from_baostock(all_codes)


def merge_factor(chunk, factor_df):
    """
    把日频复权因子广播到分钟级 chunk。
    chunk.trade_time 是带时区的 timestamp。
    同一天所有分钟 K 线共享同一个因子。
    """
    import pandas as pd
    if factor_df is None or factor_df.empty:
        chunk = chunk.copy()
        chunk['back_factor'] = 1.0
        return chunk

    # 统一转 naive datetime64[ns]（避免 DuckDB us/pandas ns 精度差异，以及时区差异）
    # 然后取天数作为合并键
    chunk_dt_ns = (
        pd.to_datetime(chunk['trade_time'], utc=True)
        .dt.tz_convert('Asia/Shanghai')
        .dt.tz_localize(None)
        .astype('datetime64[ns]')
    )
    chunk_days = chunk_dt_ns.dt.floor('D').astype('int64') // (24 * 3600 * 10**9)
    chunk_days = pd.Series(chunk_days.values, index=chunk.index)

    fdf = factor_df.copy()
    factor_dt_ns = pd.to_datetime(fdf['dt']).dt.tz_localize(None).astype('datetime64[ns]')
    fdf['day_key'] = factor_dt_ns.dt.floor('D').astype('int64') // (24 * 3600 * 10**9)
    fdf = fdf.sort_values('day_key')

    # merge_asof 需要双方按 on 列排序
    tmp = pd.DataFrame({{'day_key': chunk_days}}).reset_index(drop=False).rename(columns={{'index': 'orig_idx'}})
    tmp = tmp.sort_values('day_key')

    merged = pd.merge_asof(
        tmp[['day_key', 'orig_idx']],
        fdf[['day_key', 'back_factor']],
        on='day_key',
        direction='backward',
    )
    merged['back_factor'] = merged['back_factor'].ffill().bfill().fillna(1.0)
    # 写回原索引顺序
    merged = merged.sort_values('orig_idx')

    chunk = chunk.copy()
    chunk['back_factor'] = merged['back_factor'].values
    return chunk


# ========== 主逻辑 ==========

def process(df):
    """
    custom_python 节点入口。
    接管全部 I/O：自连 DuckDB，逐表逐 code 处理，直接写入目标库。
    返回 1 行状态 DataFrame（不传大数据）。
    """
    import duckdb
    import pandas as pd
    import gc
    from datetime import datetime

    print(f"[START] 后复权处理 - {{datetime.now().isoformat()}}")
    print(f"[CONFIG] 源库: {{SOURCE_DB}}")
    print(f"[CONFIG] 目标库: {{TARGET_DB}}")
    print(f"[CONFIG] 表: {{TABLES}}")

    # 1) 收集所有 code（跨所有待处理表）
    src_ro = duckdb.connect(SOURCE_DB, read_only=True)
    all_codes = set()
    for tbl in TABLES:
        try:
            rows = src_ro.execute(f"SELECT DISTINCT code FROM {{tbl}}").fetchall()
            all_codes.update(r[0] for r in rows)
        except Exception as e:
            print(f"[WARN] 表 {{tbl}} 查询失败：{{e}}")
    src_ro.close()
    all_codes = sorted(all_codes)
    print(f"[INFO] 共 {{len(all_codes)}} 只标的待处理")

    # 2) 加载复权因子
    factor_cache = load_adj_factors(all_codes)

    # 3) 打开目标库，逐表处理
    tgt = duckdb.connect(TARGET_DB)
    summary = []

    for tbl in TABLES:
        tgt_table = tbl + '_hfq'
        print(f"\n[PROCESS] {{tbl}} -> {{tgt_table}}")

        # 建目标表
        tgt.execute(f"""
            CREATE TABLE IF NOT EXISTS {{tgt_table}} (
                code VARCHAR,
                trade_time TIMESTAMPTZ,
                open_hfq DOUBLE,
                high_hfq DOUBLE,
                low_hfq DOUBLE,
                close_hfq DOUBLE,
                vol BIGINT,
                amount DOUBLE
            )
        """)
        # 全量重算模式：清空目标表
        tgt.execute(f"DELETE FROM {{tgt_table}}")

        src = duckdb.connect(SOURCE_DB, read_only=True)
        total_rows = 0
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

            # 类型转换（dat_1mins 字段全是 VARCHAR）
            for c in ['open', 'high', 'low', 'close', 'amount']:
                if chunk[c].dtype == object:
                    chunk[c] = pd.to_numeric(chunk[c], errors='coerce')
            if chunk['vol'].dtype == object:
                chunk['vol'] = pd.to_numeric(chunk['vol'], errors='coerce').astype('Int64')

            # 合并复权因子
            chunk = merge_factor(chunk, factor_cache.get(code))

            # 计算后复权价
            for c in ['open', 'high', 'low', 'close']:
                chunk[c + '_hfq'] = (chunk[c] * chunk['back_factor']).round(3)

            # 写入目标表（用 DuckDB 的 DataFrame 直查语法）
            try:
                tgt.execute(f"""
                    INSERT INTO {{tgt_table}}
                    SELECT code, trade_time, open_hfq, high_hfq, low_hfq, close_hfq,
                           vol::BIGINT as vol, amount
                    FROM chunk
                """)
                total_rows += len(chunk)
                code_ok += 1
            except Exception as e:
                print(f"[WARN] {{code}} 写入失败：{{e}}")
                code_fail += 1

            # 进度反馈
            if i % 200 == 0 or i == len(all_codes):
                print(f"  [PROGRESS] {{i}}/{{len(all_codes)}} 只标的, 已写入 {{total_rows}} 行")

            # 显式释放内存
            del chunk
            if i % 100 == 0:
                gc.collect()

        src.close()
        summary.append(f"{{tbl}}->{{tgt_table}}: {{total_rows}} 行 ({{code_ok}} ok / {{code_fail}} fail)")
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
    """构建工作流 JSON（单 custom_python 节点）"""
    code_str = CUSTOM_PYTHON_TEMPLATE.format(
        source_db=SOURCE_DB,
        target_db=TARGET_DB,
        tables_repr=tables,
        adj_excel=ADJ_FACTOR_EXCEL,
        batch_size=BATCH_SIZE,
    )
    return {
        "nodes": [
            {
                "id": "n1",
                "name": "后复权计算",
                "type": "custom_python",
                "parameters": {
                    "code": code_str,
                },
            }
        ],
        "connections": {},
    }


def build_pipeline_payload(workflow_id):
    """构建 Pipeline JSON（仅做调度封装，不传数据）"""
    return {
        "name": "后复权数据流",
        "description": "定时把未复权 K 线处理为后复权 K 线。工作流内部接管全部 I/O，Pipeline 仅负责调度触发。",
        "enabled": False,  # 默认关闭，用户手动启用
        "cron_expression": "0 18 * * *",  # 每天 18:00 跑一次（收盘后）
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
    """检查后端服务是否在线"""
    try:
        r = httpx.get(f"{BASE}/api/workflows/", timeout=3)
        return r.status_code == 200
    except Exception as e:
        print(f"[ERROR] 无法连接后端服务 {BASE}: {e}")
        print("[HINT] 请先启动后端: cd backend && python run_server.py")
        return False


def find_existing_workflow(name):
    """查找同名工作流，存在则返回 id（用于更新而非新建）"""
    r = httpx.get(f"{BASE}/api/workflows/")
    if r.status_code != 200:
        return None
    for w in r.json():
        if w.get("name") == name:
            return w.get("id")
    return None


def find_existing_pipeline(name):
    """查找同名 Pipeline"""
    r = httpx.get(f"{BASE}/api/pipelines/")
    if r.status_code != 200:
        return None
    for p in r.json():
        if p.get("name") == name:
            return p.get("id")
    return None


def register_workflow(name, description, workflow_json):
    """注册或更新工作流，返回 workflow_id"""
    existing_id = find_existing_workflow(name)
    payload = {
        "name": name,
        "description": description,
        "workflow_json": workflow_json,
    }
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
    """注册或更新 Pipeline，返回 pipeline_id"""
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


def trigger_workflow(wf_id):
    """触发工作流预览执行（用于验证是否可跑通）"""
    print(f"\n[ACTION] 触发工作流预览执行 id={wf_id}")
    r = httpx.post(f"{BASE}/api/workflows/{wf_id}/preview", timeout=60)
    if r.status_code == 200:
        print(f"[OK] 预览执行已触发")
        return r.json()
    print(f"[WARN] 预览触发失败 ({r.status_code}): {r.text[:300]}")
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
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只打印工作流 JSON 概要，不注册",
    )
    parser.add_argument(
        "--trigger", action="store_true",
        help="注册后立即触发一次预览执行（验证可跑通）",
    )
    args = parser.parse_args()

    tables = STAGES[args.stage]
    print("=" * 70)
    print("  后复权处理工作流 - 初始化")
    print("=" * 70)
    print(f"  阶段: {args.stage} / 共 {len(STAGES)} 阶段")
    print(f"  待处理表: {tables}")
    print(f"  源库: {SOURCE_DB}")
    print(f"  目标库: {TARGET_DB}")
    print(f"  复权因子 Excel: {ADJ_FACTOR_EXCEL}")
    print("=" * 70)

    # 构建工作流 JSON
    wf_json = build_workflow_json(tables)
    print(f"\n[INFO] 工作流节点数: {len(wf_json['nodes'])}")
    print(f"[INFO] custom_python 代码长度: {len(wf_json['nodes'][0]['parameters']['code'])} 字符")

    if args.dry_run:
        print("\n[DRY-RUN] 工作流 JSON 概要:")
        # 代码太长，只打印前 500 字符
        preview = dict(wf_json)
        preview["nodes"] = [
            {**n, "parameters": {"code": n["parameters"]["code"][:500] + "..."}}
            for n in wf_json["nodes"]
        ]
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    # 检查后端服务
    if not check_server():
        sys.exit(1)

    # 注册工作流
    wf_id = register_workflow(
        name="后复权处理",
        description=f"从 {SOURCE_DB} 读取未复权 K 线，计算后复权价，写入 {TARGET_DB}。阶段 {args.stage}: {tables}",
        workflow_json=wf_json,
    )
    if not wf_id:
        sys.exit(1)

    # 注册 Pipeline
    pl_payload = build_pipeline_payload(wf_id)
    pl_id = register_pipeline(pl_payload)
    if not pl_id:
        print("[WARN] Pipeline 注册失败，工作流仍可独立使用")

    # 打印后续操作指引
    print("\n" + "=" * 70)
    print("  ✅ 初始化完成")
    print("=" * 70)
    print(f"  工作流 ID: {wf_id}")
    if pl_id:
        print(f"  Pipeline ID: {pl_id}")
    print(f"""
后续操作：
  1. 打开 ETL 工具前端，找到工作流 "后复权处理"
  2. 手动执行一次，观察输出状态
  3. 在 DuckDB 中验证数据：
     cd C:\\duckdb
     python -c "import duckdb; c=duckdb.connect('quantifydata_hfq.duckdb'); print(c.execute('SELECT tbl, COUNT(*) FROM (SELECT \\'dat_day_hfq\\' as tbl, * FROM dat_day_hfq)').fetchdf())"
  4. 与通达信后复权价格抽样比对（详见 docs/example_workflows.md 示例 14）
  5. 确认准确性后，升级到下一阶段：
     python examples/hfq_processing_setup.py --stage {min(args.stage + 1, 7)}
""")

    # 可选：立即触发预览
    if args.trigger:
        trigger_workflow(wf_id)


if __name__ == "__main__":
    main()
