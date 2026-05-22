#!/usr/bin/env bash
# QuantSync ETL - Unix/macOS startup script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")/backend"
cd "$BACKEND_DIR"

# Check for venv
if [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
    echo "Using venv..."
else
    PYTHON="python3"
    echo "Using system Python..."
fi

# Check and install optional dependencies
echo "Checking dependencies..."
"$PYTHON" -c "
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
echo ""

# Start application
"$PYTHON" -m app.tray_app
