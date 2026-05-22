@echo off
REM QuantSync ETL - Windows startup script

cd /d "%~dp0\..\backend"

REM Check for venv
if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
    echo Using venv...
) else (
    set PYTHON=python
    echo Using system Python...
)

REM Check and install optional dependencies
echo Checking dependencies...
%PYTHON% -c "
import importlib, subprocess, sys
missing = []
for name, pkg in [('binance', 'python-binance'), ('yfinance', 'yfinance'), ('akshare', 'akshare'), ('tushare', 'tushare'), ('mootdx', 'mootdx')]:
    try:
        importlib.import_module(name)
    except ImportError:
        missing.append(pkg)
if missing:
    print('  安装缺失依赖: ' + ', '.join(missing))
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q'] + missing, stdout=subprocess.DEVNULL)
    print('  依赖安装完成')
else:
    print('  依赖检查通过')
"

echo.

REM Start application
%PYTHON% -m app.tray_app
pause
