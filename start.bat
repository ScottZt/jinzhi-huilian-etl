@echo off
setlocal
title JinZhiHuiLian-ETL :8080

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"

set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=
set no_proxy=*
set NO_PROXY=*

echo [0/3] Detecting stale venv - path-moved guard...
if exist "%BACKEND%\venv\Scripts\python.exe" (
    "%BACKEND%\venv\Scripts\python.exe" -c "" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Existing venv is broken [project path likely moved]. Recreating...
        rmdir /s /q "%BACKEND%\venv"
    ) else (
        echo [OK] Existing venv is healthy.
    )
)

echo [1/3] Checking Python...
if not exist "%BACKEND%\venv\Scripts\python.exe" (
    echo [INFO] Creating backend virtual environment...
    python -m venv "%BACKEND%\venv"
    if errorlevel 1 (
        echo [ERROR] Failed to create backend venv.
        pause
        exit /b 1
    )
)

echo [2/3] Checking dependencies...
cd /d "%BACKEND%"
venv\Scripts\python.exe -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 goto :install_deps

REM Check if requirements.txt changed since last install
venv\Scripts\python.exe -c "import hashlib,os; cur=hashlib.md5(open('requirements.txt','rb').read()).hexdigest(); old=open('venv/.req_hash').read().strip() if os.path.exists('venv/.req_hash') else ''; exit(0 if cur==old else 1)" >nul 2>&1
if errorlevel 1 goto :sync_deps
goto :deps_ok

:install_deps
echo [INFO] Installing dependencies (first run)...
venv\Scripts\python.exe -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
venv\Scripts\pip.exe install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if errorlevel 1 (
    echo [ERROR] Failed to install backend dependencies.
    pause
    exit /b 1
)
venv\Scripts\python.exe -c "import hashlib; print(hashlib.md5(open('requirements.txt','rb').read()).hexdigest())" > venv\.req_hash
goto :deps_ok

:sync_deps
echo [INFO] requirements.txt changed, syncing dependencies...
venv\Scripts\pip.exe install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if errorlevel 1 (
    echo [WARN] Failed to sync some dependencies, continuing...
) else (
    venv\Scripts\python.exe -c "import hashlib; print(hashlib.md5(open('requirements.txt','rb').read()).hexdigest())" > venv\.req_hash
    echo [OK] Dependencies synced.
)

:deps_ok

echo [3/3] Starting server on http://127.0.0.1:8080 ...
echo       Waiting for backend to become ready, browser will open automatically...

rem Launch health-check script in background: polls backend until ready, then opens browser.
rem Uses a separate ps1 file to avoid bat inline PowerShell quote/escape issues.
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\wait_for_backend.ps1"

cd /d "%BACKEND%"
call venv\Scripts\python.exe -u run_server.py
if errorlevel 1 (
    echo [ERROR] Server failed. Check console logs above.
    pause
    exit /b 1
)

endlocal
