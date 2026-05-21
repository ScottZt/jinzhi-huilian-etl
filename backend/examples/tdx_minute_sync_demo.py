"""
金智汇联 ETL — 通达信分钟 K 线同步到 DuckDB 演示脚本

通过后端 REST API 演示完整 ETL 流程：
  数据源创建 → 连接管理 → 表结构 → 同步任务 → 验证结果

支持两种数据源模式：
  - tdx:    通达信本地数据文件（.1min/.01/.lc1 等）
  - mootdx: 通过 mootdx 库在线连接通达信行情服务器

用法：
  cd backend
  python examples/tdx_minute_sync_demo.py
  python examples/tdx_minute_sync_demo.py --mode mootdx
  python examples/tdx_minute_sync_demo.py --mode tdx --data-dir "D:/tdx/vipdoc" --codes 000001,600000
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

# 确保 Windows 控制台使用 UTF-8，避免 emoji/中文乱码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def sanitize(msg: str) -> str:
    """清理可能导致控制台编码错误的字符（如 ⚠️ emoji）。"""
    return msg.replace("⚠", "!").replace("️", "").replace("\U0001f6a9", "!")

# ============================================================================
# 可配置参数（也可通过 CLI 参数覆盖）
# ============================================================================
DEFAULT_MODE = "tdx"
DEFAULT_DATA_DIR = ""  # TDX 模式必填，如 r"D:\tdx\vipdoc"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8080"
DEFAULT_CODES = ["000001", "600000"]
DEFAULT_LOOKBACK = 60
DEFAULT_TARGET_TABLE = "stock_minute_kline"
# DuckDB 文件路径 — 在通达信 exe 同级目录创建
DUCKDB_DIR = r"D:\04.量化\测试&演示\duckdb"
DUCKDB_PATH = os.path.join(DUCKDB_DIR, "demo_data.db")


def print_step(n: int, msg: str):
    print(f"\n{'='*60}")
    print(f"  步骤 {n}: {msg}")
    print(f"{'='*60}")


def print_ok(msg: str):
    print(f"  [OK] {msg}")


def print_err(msg: str):
    print(f"  [ERROR] {sanitize(str(msg))}")


def print_warn(msg: str):
    print(f"  [WARN] {sanitize(str(msg))}")


def print_info(msg: str):
    print(f"  [INFO] {sanitize(str(msg))}")


# ============================================================================
# API 客户端
# ============================================================================
class DemoClient:
    """封装后端 REST API 调用的便捷客户端。"""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base, timeout=120.0)

    def get(self, path: str, **kw) -> dict:
        r = self.client.get(path, **kw)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, **kw) -> dict:
        r = self.client.post(path, **kw)
        r.raise_for_status()
        return r.json()

    def put(self, path: str, **kw) -> dict:
        r = self.client.put(path, **kw)
        r.raise_for_status()
        return r.json()

    def delete(self, path: str) -> dict:
        r = self.client.delete(path)
        r.raise_for_status()
        return r.json()

    def cleanup(self):
        self.client.close()


# ============================================================================
# 各步骤实现
# ============================================================================

def check_backend(client: DemoClient) -> bool:
    """步骤 1: 检查后端服务是否可用。"""
    print_step(1, "检查后端服务状态")
    try:
        data = client.get("/health")
        print_ok(f"后端服务可用: {data}")
        return True
    except Exception as e:
        print_err(f"无法连接后端 ({client.base}): {e}")
        print_info("请确保后端服务已启动，例如: python backend/app/main.py")
        return False


def create_kline_source(client: DemoClient, mode: str, data_dir: str) -> Optional[dict]:
    """步骤 2+3: 创建 K 线数据源并测试连接。"""
    print_step(2, "创建 K 线数据源")

    if mode == "tdx":
        if not data_dir or not Path(data_dir).is_dir():
            print_err(f"TDX 数据目录不存在: {data_dir}")
            print_info("请通过 --data-dir 指定通达信数据目录（如 D:/tdx/vipdoc）")
            return None

        body = {
            "name": "TDX 本地分钟数据",
            "type": "tdx",
            "config": {
                "data_dir": data_dir,
                "interval": "1min",
            },
        }
        result = client.post("/api/kline-sources/", json=body)
        print_ok(f"数据源已创建: id={result['id']}, name={result['name']}")

        # 测试连接
        print_info("正在测试连接...")
        test = client.post(f"/api/kline-sources/{result['id']}/test")
        print_info(test.get("message", ""))
        if not test.get("success"):
            print_warn("连接测试未通过，但继续尝试...")

        # 列出可用代码
        codes_resp = client.get(f"/api/kline-sources/{result['id']}/codes")
        codes = codes_resp.get("codes", [])
        print_ok(f"可用股票代码数: {codes_resp.get('count', 0)}")
        if codes:
            sample = codes[:5]
            print_info(f"示例: {[c.get('name', c.get('code')) for c in sample]}")

    elif mode == "mootdx":
        # 先解锁私有功能
        password = os.environ.get("JZHL_MOOTDX_PASSWORD", "")
        if not password:
            print_err("Mootdx 模式需要设置环境变量 JZHL_MOOTDX_PASSWORD")
            print_info("在命令行中设置: set JZHL_MOOTDX_PASSWORD=你的密码")
            return None

        print_info("正在解锁 Mootdx 私有功能...")
        unlock = client.post("/api/kline-sources/private/unlock", json={"password": password})
        if not unlock.get("success"):
            print_err(f"解锁失败: {unlock}")
            return None
        token = unlock["token"]
        print_ok("私有功能已解锁")

        headers = {"X-Private-Feature-Token": token}
        body = {
            "name": "Mootdx 在线分钟数据",
            "type": "mootdx",
            "config": {
                "interval": "1min",
                "use_bestip": "false",
                "timeout": 10,
                "preview_codes": "000001",
            },
        }
        result = client.post("/api/kline-sources/", json=body, headers=headers)
        print_ok(f"数据源已创建: id={result['id']}, name={result['name']}")

        # 测试连接
        print_info("正在测试连接（拉取分钟线探测）...")
        test = client.post(f"/api/kline-sources/{result['id']}/test", headers=headers)
        print_info(test.get("message", ""))
        if not test.get("success"):
            print_warn("连接测试未通过，但继续尝试...")

    else:
        print_err(f"未知模式: {mode}")
        return None

    return result


def create_duckdb_connection(client: DemoClient) -> Optional[dict]:
    """步骤 4+5: 创建 DuckDB 目标连接并测试。"""
    print_step(3, "创建 DuckDB 目标连接")

    body = {
        "name": "DuckDB Demo 目标库",
        "type": "duckdb",
        "config": {
            "db_path": DUCKDB_PATH,
        },
    }
    result = client.post("/api/connections/", json=body)
    print_ok(f"目标连接已创建: id={result['id']}, db_path={DUCKDB_PATH}")

    # 测试连接
    print_info("正在测试连接...")
    test = client.post(f"/api/connections/{result['id']}/test")
    print_info(test.get("message", ""))
    if not test.get("success"):
        print_err(f"连接测试失败: {test.get('message', '')}")
        return None

    return result


def create_target_table(target_table: str) -> bool:
    """步骤 6: 创建 DuckDB 目标表。"""
    print_step(4, f"创建目标表 [{target_table}]")

    try:
        import duckdb
    except ImportError:
        print_err("未安装 duckdb，请先: pip install duckdb")
        return False

    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=False)
        # 先 DROP 已存在的表，确保演示干净
        conn.execute(f"DROP TABLE IF EXISTS {target_table}")
        conn.execute(f"""
            CREATE TABLE {target_table} (
                stock_code VARCHAR,
                trade_time TIMESTAMP,
                open_price DOUBLE,
                high_price DOUBLE,
                low_price DOUBLE,
                close_price DOUBLE,
                volume BIGINT,
                amount DOUBLE
            )
        """)
        conn.close()
        print_ok(f"目标表已创建: {DUCKDB_PATH}::{target_table}")
        print_info("表结构:")
        print_info("  stock_code  VARCHAR  - 股票代码")
        print_info("  trade_time  TIMESTAMP - 交易时间")
        print_info("  open_price  DOUBLE   - 开盘价")
        print_info("  high_price  DOUBLE   - 最高价")
        print_info("  low_price   DOUBLE   - 最低价")
        print_info("  close_price DOUBLE   - 收盘价")
        print_info("  volume      BIGINT   - 成交量")
        print_info("  amount      DOUBLE   - 成交额")
        return True
    except Exception as e:
        print_err(f"创建表失败: {e}")
        return False


def create_sync_task(
    client: DemoClient,
    source_id: str,
    target_conn_id: str,
    target_table: str,
    mode: str,
    codes: list,
    lookback: int,
) -> Optional[dict]:
    """步骤 7: 创建同步任务。"""
    print_step(5, "创建同步任务")

    # 根据模式构建不同的字段映射
    if mode == "tdx":
        # TDX 输出列: code, datetime, open, high, low, close, volume, amount
        field_mappings = [
            {"source_field": "code",     "target_field": "stock_code",  "transform": "direct"},
            {"source_field": "datetime", "target_field": "trade_time",  "transform": "direct"},
            {"source_field": "open",     "target_field": "open_price",  "transform": "direct"},
            {"source_field": "high",     "target_field": "high_price",  "transform": "direct"},
            {"source_field": "low",      "target_field": "low_price",   "transform": "direct"},
            {"source_field": "close",    "target_field": "close_price", "transform": "direct"},
            {"source_field": "volume",   "target_field": "volume",      "transform": "direct"},
            {"source_field": "amount",   "target_field": "amount",      "transform": "direct"},
        ]
    else:
        # Mootdx 输出列: code, dt, open, high, low, close, vol, amount
        field_mappings = [
            {"source_field": "code",  "target_field": "stock_code",  "transform": "direct"},
            {"source_field": "dt",    "target_field": "trade_time",  "transform": "direct"},
            {"source_field": "open",  "target_field": "open_price",  "transform": "direct"},
            {"source_field": "high",  "target_field": "high_price",  "transform": "direct"},
            {"source_field": "low",   "target_field": "low_price",   "transform": "direct"},
            {"source_field": "close", "target_field": "close_price", "transform": "direct"},
            {"source_field": "vol",   "target_field": "volume",      "transform": "direct"},
            {"source_field": "amount","target_field": "amount",      "transform": "direct"},
        ]

    body = {
        "name": f"{'TDX' if mode == 'tdx' else 'Mootdx'} 分钟K线 → DuckDB",
        "source_connection_id": source_id,
        "target_connection_id": target_conn_id,
        "target_table": target_table,
        "config_json": {
            "codes": codes,
            "interval": "1min",
            "time_mode": "lookback",
            "lookback_days": lookback,
            "session_only": False,  # 关闭交易时段过滤，避免 dt/datetime 列名差异
            "batch_size": 5000,
            "on_duplicate": "ignore",
            "field_mappings": field_mappings,
        },
    }

    result = client.post("/api/kline-sync-tasks/", json=body)
    print_ok(f"同步任务已创建: id={result['id']}, name={result['name']}")
    print_info(f"  股票代码: {codes}")
    print_info(f"  周期: 1min")
    print_info(f"  回看: {lookback} 天")
    print_info(f"  字段映射: {len(field_mappings)} 个")
    return result


def run_sync_task(client: DemoClient, task_id: str, timeout: int = 120) -> Optional[dict]:
    """步骤 8: 执行同步任务并轮询等待完成。"""
    print_step(6, "执行同步任务")

    # 触发执行
    result = client.post(f"/api/kline-sync-tasks/{task_id}/run")
    print_ok(f"任务已加入后台队列: {result.get('message', '')}")

    # 轮询执行记录
    print_info(f"正在轮询执行状态（超时 {timeout}s）...")
    start = time.time()
    poll_interval = 2

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        sys.stdout.write(f"  已等待 {elapsed}s...\r")
        sys.stdout.flush()

        try:
            records = client.get(f"/api/kline-sync-tasks/{task_id}/records", params={"limit": 1})
            if records:
                rec = records[0]
                status = rec.get("status", "")
                if status in ("success", "failed"):
                    print()  # 换行
                    if status == "success":
                        print_ok(f"同步完成!")
                        print_info(f"  读取行数: {rec.get('rows_read', 0)}")
                        print_info(f"  写入行数: {rec.get('rows_written', 0)}")
                        print_info(f"  跳过行数: {rec.get('rows_skipped', 0)}")
                        print_info(f"  耗时: {rec.get('duration', 0):.2f}s")
                        return rec
                    else:
                        print_err(f"同步失败: {rec.get('error_message', '未知错误')}")
                        return rec
        except Exception:
            pass

        time.sleep(poll_interval)

    print()
    print_warn(f"超时 ({timeout}s)，任务可能仍在执行中")
    return None


def verify_results(target_table: str) -> bool:
    """步骤 9: 验证 DuckDB 中的同步结果。"""
    print_step(7, "验证同步结果")

    try:
        import duckdb
    except ImportError:
        print_err("未安装 duckdb")
        return False

    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)

        # 总行数
        row_count = conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0]
        print_ok(f"总行数: {row_count}")

        if row_count == 0:
            print_warn("表中无数据，请检查数据源配置和日期范围")
            conn.close()
            return False

        # 涉及股票
        stocks = conn.execute(f"SELECT DISTINCT stock_code FROM {target_table} ORDER BY stock_code").fetchall()
        stock_list = [r[0] for r in stocks]
        print_ok(f"涉及股票: {', '.join(stock_list)}")

        # 时间范围
        time_range = conn.execute(
            f"SELECT MIN(trade_time) as start_t, MAX(trade_time) as end_t FROM {target_table}"
        ).fetchone()
        print_ok(f"时间范围: {time_range[0]} ~ {time_range[1]}")

        # 各股票行数
        per_stock = conn.execute(
            f"SELECT stock_code, COUNT(*) as cnt FROM {target_table} GROUP BY stock_code ORDER BY stock_code"
        ).fetchall()
        print_info("各股票行数:")
        for code, cnt in per_stock:
            print_info(f"  {code}: {cnt:,} 条")

        # 样本数据
        sample = conn.execute(
            f"SELECT * FROM {target_table} ORDER BY trade_time DESC LIMIT 5"
        ).fetchdf()
        print_info("最新 5 条数据:")
        print(f"\n{sample.to_string(index=False)}\n")

        conn.close()
        return True
    except Exception as e:
        print_err(f"验证失败: {e}")
        return False


# ============================================================================
# 主流程
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="通达信分钟 K 线 → DuckDB 同步演示")
    parser.add_argument("--mode", choices=["tdx", "mootdx"], default=DEFAULT_MODE,
                        help="数据源模式 (默认: tdx)")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                        help="通达信本地数据目录路径 (TDX 模式必填)")
    parser.add_argument("--codes", default=None,
                        help="股票代码，逗号分隔 (默认: 000001,600000)")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK,
                        help=f"回看天数 (默认: {DEFAULT_LOOKBACK})")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL,
                        help=f"后端 API 地址 (默认: {DEFAULT_BACKEND_URL})")
    parser.add_argument("--table", default=DEFAULT_TARGET_TABLE,
                        help=f"目标表名 (默认: {DEFAULT_TARGET_TABLE})")
    parser.add_argument("--keep", action="store_true", default=False,
                        help="保留演示资源（不删除数据源、连接、任务）")
    args = parser.parse_args()

    # 解析股票代码
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] if args.codes else DEFAULT_CODES

    # 打印配置
    print("=" * 60)
    print("  金智汇联 ETL — 通达信分钟 K 线同步演示")
    print("=" * 60)
    print_info(f"  模式: {args.mode}")
    print_info(f"  后端: {args.backend_url}")
    print_info(f"  股票代码: {codes}")
    print_info(f"  回看天数: {args.lookback}")
    print_info(f"  目标表: {args.table}")
    print_info(f"  DuckDB: {DUCKDB_PATH}")
    if args.mode == "tdx":
        print_info(f"  TDX 数据目录: {args.data_dir or '(未指定)'}")

    # 步骤 1: 检查后端
    client = DemoClient(args.backend_url)
    try:
        if not check_backend(client):
            print_err("后端不可用，退出")
            return

        # 步骤 2+3: 创建数据源
        source = create_kline_source(client, args.mode, args.data_dir)
        if not source:
            print_err("数据源创建失败，退出")
            return

        # 步骤 4+5: 创建目标连接
        target_conn = create_duckdb_connection(client)
        if not target_conn:
            print_err("目标连接创建失败，退出")
            return

        # 步骤 6: 创建目标表
        if not create_target_table(args.table):
            print_err("目标表创建失败，退出")
            return

        # 步骤 7: 创建同步任务
        task = create_sync_task(
            client, source["id"], target_conn["id"],
            args.table, args.mode, codes, args.lookback,
        )
        if not task:
            print_err("同步任务创建失败，退出")
            return

        # 步骤 8: 执行同步
        record = run_sync_task(client, task["id"])

        # 步骤 9: 验证结果
        verify_results(args.table)

        # 清理残留资源（默认保留，加 --keep 参数可保留资源供前端查看）
        print(f"\n{'='*60}")
        if args.keep:
            print_info("保留演示资源（--keep），可在前端页面查看")
            print_info(f"  数据源: {source['id']}")
            print_info(f"  连接: {target_conn['id']}")
            print_info(f"  任务: {task['id']}")
        else:
            print_info("清理演示资源...")
            try:
                client.delete(f"/api/kline-sync-tasks/{task['id']}")
                print_ok(f"已删除同步任务: {task['id']}")
            except Exception:
                pass
            try:
                client.delete(f"/api/kline-sources/{source['id']}")
                print_ok(f"已删除数据源: {source['id']}")
            except Exception:
                pass
            try:
                client.delete(f"/api/connections/{target_conn['id']}")
                print_ok(f"已删除连接: {target_conn['id']}")
            except Exception:
                pass

    except httpx.ConnectError:
        print_err(f"无法连接后端 {args.backend_url}，请确认后端已启动")
    except httpx.HTTPStatusError as e:
        print_err(f"API 错误 {e.response.status_code}: {e.response.text}")
    except Exception as e:
        print_err(f"异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.cleanup()

    print(f"\n{'='*60}")
    print("  演示完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
