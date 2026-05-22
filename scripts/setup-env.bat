@echo off
REM QuantSync ETL - Windows venv setup script
REM Creates isolated virtual environment and installs dependencies

cd /d "%~dp0\..\backend"

echo === QuantSync ETL Environment Setup ===
echo.

REM Check Python version
python --version 2>NUL
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10-3.12 from python.org
    pause
    exit /b 1
)

REM Check Python version compatibility
for /f "tokens=2 delims= " %%v in ('python --version 2^>^NUL') do set PYVER=%%v
echo Found Python %PYVER%

REM Create venv if not exists
if not exist "venv" (
    echo.
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv
        pause
        exit /b 1
    )
)

REM Activate venv and install
echo.
echo Installing dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
if exist requirements.txt (
    pip install -r requirements.txt
)
REM Install optional data source packages
pip install python-binance yfinance akshare tushare mootdx
pip freeze > requirements.lock.txt

echo.
echo === Setup complete ===
echo Run 'scripts\run.bat' to start QuantSync ETL
pause
