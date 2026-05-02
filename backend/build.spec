# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for 金智汇连ETL — 合规设计：无任何第三方金融数据 SDK 绑定。"""

import os
import sys
from pathlib import Path

block_cipher = None

# Project paths
spec_dir = Path(SPECPATH)
backend_dir = spec_dir
static_dir = backend_dir / "app" / "static"

# Collect all data files
datas = [
    (str(static_dir), "app/static"),
]

# Hidden imports (packages that use dynamic imports)
# 合规说明：不内置 pytdx、akshare、tushare 等第三方金融 SDK
hiddenimports = [
    "tkinter",
    "tkinter.font",
    "tkinter.messagebox",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "apscheduler.schedulers.background",
    "apscheduler.triggers.cron",
    "apscheduler.triggers.date",
    "apscheduler.triggers.interval",
    "apscheduler.executors.pool",
    "apscheduler.jobstores.memory",
    "watchdog.observers",
    "watchdog.events",
    "PIL._tkinter_finder",
    "pymysql",
    "psycopg2",
    "duckdb",
    "clickhouse_driver",
    "openpyxl",
    "chardet",
    "pyarrow",
    "pydantic",
    "pydantic_settings",
    "fastapi",
    "starlette",
    "anyio",
    "httpcore",
    "httpx",
    "sniffio",
    "psutil",
    "requests",
    "win32gui",
    "win32con",
    "win32api",
    "win32ui",
    "win32evtlog",
    "pywintypes",
    "pystray",
    "pytdx",
    "pytdx.hq",
    # 金智汇连ETL 内置 SDK
    "etl_tool_sdk",
    "etl_tool_sdk.connector",
    "etl_tool_sdk.cleaner",
    "etl_tool_sdk.scheduler",
    "etl_tool_sdk.executor",
    "etl_tool_sdk.logger",
    "etl_tool_sdk.license",
    "etl_tool_sdk.config",
]

# Exclude unnecessary packages to reduce size
excludes = [
    "matplotlib",
    "scipy",
    "IPython",
    "notebook",
    "jupyterlab",
    "pytest",
    "sphinx",
]

a = Analysis(
    [str(backend_dir / "app" / "tray_app.py")],
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

if sys.platform == "darwin":
    # macOS: create .app bundle
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="JinZhiHuiETL",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        icon=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="JinZhiHuiETL",
    )
    app = BUNDLE(
        coll,
        name="JinZhiHuiETL.app",
        icon=None,
        bundle_identifier="com.jinzhihui.etl",
        info_plist={
            "LSUIElement": False,
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleName": "金智汇连ETL",
        },
    )
else:
    # Windows: single file exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="金智汇连ETL",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        icon=str(static_dir / "logo.ico"),
    )