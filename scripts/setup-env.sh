#!/usr/bin/env bash
# QuantSync ETL - Unix/macOS venv setup script
# Creates isolated virtual environment and installs dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")/backend"
cd "$BACKEND_DIR"

echo "=== QuantSync ETL Environment Setup ==="
echo ""

# Check Python3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found. Install Python 3.10-3.12"
    exit 1
fi

PYVER=$(python3 --version 2>&1 | awk '{print $2}')
echo "Found Python $PYVER"

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv and install
echo ""
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi
# Install optional data source packages
pip install python-binance yfinance akshare tushare mootdx
pip freeze > requirements.lock.txt

echo ""
echo "=== Setup complete ==="
echo "Run 'scripts/run.sh' to start QuantSync ETL"
