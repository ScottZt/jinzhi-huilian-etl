@echo off
setlocal
REM One-click launcher for QuantSync ETL (Windows).
REM Steps:
REM 1) Verify Python and Node.js are available.
REM 2) Create backend virtual environment on first run.
REM 3) Install backend/frontend dependencies if needed.
REM 4) Start Electron app in development mode.

REM Always run from project root, no matter where script is started.
cd /d "%~dp0"

echo [1/6] Checking Python...
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10-3.12 and add it to PATH.
    pause
    exit /b 1
)

echo [2/6] Checking Node.js...
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 18+ and add it to PATH.
    pause
    exit /b 1
)

echo [3/6] Preparing backend virtual environment...
if not exist "backend\venv\Scripts\python.exe" (
    REM First run: create isolated venv for backend.
    cd /d "%~dp0backend"
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create backend venv.
        pause
        exit /b 1
    )
    cd /d "%~dp0"
)

echo [4/6] Installing backend dependencies...
cd /d "%~dp0backend"
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install backend dependencies.
    pause
    exit /b 1
)

echo [5/6] Installing frontend dependencies...
cd /d "%~dp0frontend"
REM Use mirror + retry strategy to reduce Electron download network failures.
set "ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/"
REM Use project-local Electron cache to avoid permission issues on AppData.
set "ELECTRON_CACHE=%~dp0frontend\.electron-cache"
if not exist "%ELECTRON_CACHE%" mkdir "%ELECTRON_CACHE%"
if not exist "node_modules\.bin\electron.cmd" (
    REM Install/reinstall frontend packages when electron binary is missing.
    call npm install --registry=https://registry.npmmirror.com --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000
    if errorlevel 1 (
        echo [ERROR] Failed to install frontend dependencies.
        pause
        exit /b 1
    )
)

echo [6/6] Starting QuantSync ETL...
REM npm run dev starts Electron and auto-starts backend.
call npm run dev
if errorlevel 1 (
    echo [ERROR] Startup failed. Check console logs above.
    pause
    exit /b 1
)

endlocal
