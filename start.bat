@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"

set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=
set no_proxy=*
set NO_PROXY=*

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
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    venv\Scripts\python.exe -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org
    venv\Scripts\pip.exe install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
    if errorlevel 1 (
        echo [ERROR] Failed to install backend dependencies.
        pause
        exit /b 1
    )
)

echo [3/3] Starting server on http://127.0.0.1:8080 ...
start "" http://127.0.0.1:8080
cd /d "%BACKEND%"
call venv\Scripts\python.exe -u run_server.py
if errorlevel 1 (
    echo [ERROR] Server failed. Check console logs above.
    pause
    exit /b 1
)

endlocal
