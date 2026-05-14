# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for backend server — 纯 API 服务，无 GUI 依赖。"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

spec_dir = Path(SPECPATH)
backend_dir = spec_dir
static_dir = backend_dir / "app" / "static"

# Collect all data files (static resources)
datas = [
    (str(static_dir), "app/static"),
]

def add_all_hidden(name):
    """Collect all submodules and data for a package."""
    try:
        submods = collect_submodules(name)
        data, binaries = collect_data_files(name, include_py_files=True)
        return submods, data
    except Exception:
        return [], []

hiddenimports = [
    # apscheduler (critical - missing from build)
    "apscheduler.schedulers.background",
    "apscheduler.schedulers.blocking",
    "apscheduler.triggers.cron",
    "apscheduler.triggers.date",
    "apscheduler.triggers.interval",
    "apscheduler.executors.pool",
    "apscheduler.executors.base",
    "apscheduler.jobstores.memory",
    "apscheduler.jobstores.base",
    "apscheduler.events",
    "apscheduler.util",
    # uvicorn
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # fastapi/starlette
    "fastapi",
    "fastapi.applications",
    "fastapi.routing",
    "fastapi.middleware.cors",
    "fastapi.staticfiles",
    "fastapi.responses",
    "fastapi.middleware",
    "starlette",
    "starlette.applications",
    "starlette.routing",
    "starlette.middleware",
    "starlette.middleware.cors",
    "starlette.staticfiles",
    "starlette.responses",
    "starlette.endpoints",
    "anyio",
    "sniffio",
    # httpx/httpcore
    "httpx",
    "httpcore",
    "httpcore._sync",
    "httpcore._sync.connection",
    "httpcore._sync.connection_pool",
    "httpcore._sync.http11",
    "httpcore._sync.http2",
    "h11",
    # database drivers
    "pymysql",
    "pymysql.connections",
    "psycopg2",
    "duckdb",
    "clickhouse_driver",
    # pandas/numpy
    "pandas",
    "numpy",
    # akshare local SDK
    "akshare",
    # pydantic
    "pydantic",
    "pydantic_settings",
    # file handling
    "openpyxl",
    "chardet",
    "pyarrow",
    # misc
    "psutil",
    "requests",
    "sqlalchemy",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "pytz",
    "tzlocal",
    # built-in SDK
    "etl_tool_sdk",
    "etl_tool_sdk.connector",
    "etl_tool_sdk.cleaner",
    "etl_tool_sdk.scheduler",
    "etl_tool_sdk.executor",
    "etl_tool_sdk.logger",
    "etl_tool_sdk.license",
    "etl_tool_sdk.config",
    # app modules (dynamic imports)
    "app.persistence.sqlite_repo",
    "app.core.license_manager",
    "app.core.task_scheduler",
    "app.core.kline_sync_engine",
    "app.core.workflow_engine",
    "app.core.transform_engine",
    "app.core.connection_manager",
    "app.core.websocket_manager",
    "app.core.bulk_import_engine",
    "app.core.parallel_engine",
    "app.core.report_generator",
    "app.core.ai_script_generator",
    "app.core.file_watcher",
    "app.core.credential_manager",
    "app.models.connection",
    "app.models.workflow",
    "app.models.pipeline",
    "app.models.schema",
    "app.models.bulk_import",
    "app.api.connections",
    "app.api.schemas",
    "app.api.tasks",
    "app.api.bulk_import",
    "app.api.monitor",
    "app.api.file_watchers",
    "app.api.transforms",
    "app.api.reports",
    "app.api.kline_sources",
    "app.api.credentials",
    "app.api.kline_sync_tasks",
    "app.api.workflows",
    "app.api.pipelines",
    "app.api.license",
    "app.api.ai_script",
    "app.api.llm",
    "app.adapters.source_adapters.tdx_adapter",
    "app.adapters.source_adapters.tushare_adapter",
    "app.adapters.source_adapters.akshare_adapter",
    "app.adapters.source_adapters.kline_base",
    "app.adapters.source_adapters.csv_adapter",
    "app.adapters.source_adapters.excel_adapter",
    "app.adapters.source_adapters.json_adapter",
    "app.adapters.source_adapters.parquet_adapter",
    "app.adapters.target_adapters.sqlite_target",
    "app.adapters.target_adapters.mysql_target",
    "app.adapters.target_adapters.postgres_target",
    "app.adapters.target_adapters.duckdb_target",
    "app.adapters.target_adapters.clickhouse_target",
    "app.adapters.target_adapters.excel_target",
    "app.adapters.target_adapters.csv_target",
    "app.nodes.resample",
    "app.nodes.indicators",
    "app.nodes.filter",
    "app.nodes.sort_group",
    "app.nodes.column_ops",
    "app.nodes.condition",
    "app.nodes.custom_python",
    # encryption
    "cryptography",
]

excludes = [
    "matplotlib", "scipy", "IPython", "notebook", "jupyterlab",
    "pytest", "sphinx", "tkinter", "pystray",
]

a = Analysis(
    [str(backend_dir / "bootstrap.py")],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="backend-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="backend-server",
)
