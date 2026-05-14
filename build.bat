@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
REM QuantSync ETL one-click build - double-click this file.
REM Prerequisites: Python 3.10+ and Node.js 18+ installed.
REM Output: frontend/dist/ (NSIS installer + portable exe)

cd /d "%~dp0"

echo.
echo ========================================
echo   QuantSync ETL Build
echo ========================================
echo.

REM Check Python
echo [1/5] Checking Python...
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

REM Check Node.js
echo [2/5] Checking Node.js...
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node.js 18+ and add to PATH.
    pause
    exit /b 1
)

REM Install backend dependencies
echo [3/5] Installing backend dependencies...
cd /d "%~dp0backend"
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Backend dependency installation failed.
    pause
    exit /b 1
)

REM Package backend with PyInstaller using venv
echo [4/5] Packaging backend service...
REM Use venv pyinstaller to ensure correct package versions
call venv\Scripts\activate.bat
pyinstaller build.spec --distpath dist --noconfirm
if errorlevel 1 (
    echo [ERROR] Backend packaging failed.
    pause
    exit /b 1
)
if not exist "dist\backend-server\backend-server.exe" (
    echo [ERROR] Backend exe not generated. Check build.spec output.
    pause
    exit /b 1
)

REM Install frontend deps and package Electron app
echo [5/5] Packaging Electron app...
cd /d "%~dp0frontend"
if not exist "node_modules" (
    call npm install --registry=https://registry.npmmirror.com --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000
)
REM Skip code signing (GitHub download blocked in China), use npmmirror for electron-builder binaries.
set "CSC_IDENTITY_AUTO_DISCOVERY=false"
set "ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/"
call npm run build:win
if errorlevel 1 (
    echo [ERROR] Electron packaging failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Build complete! Output: frontend/dist/
echo ========================================
echo.

endlocal
pause