#!/usr/bin/env bash
# Build script for macOS PyInstaller

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"

echo "=== QuantSync ETL Build (macOS) ==="
echo "Project: $PROJECT_DIR"

# Check Python3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found. Please install Python 3.10-3.12"
    exit 1
fi

echo "Python: $(python3 --version)"

cd "$BACKEND_DIR"

# Install dependencies
echo ""
echo "=== Installing dependencies ==="
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "No venv found, using system Python"
fi

pip install -r requirements.txt
pip install pyinstaller

# Build with PyInstaller
echo ""
echo "=== Building with PyInstaller ==="
pyinstaller --clean --noconfirm build.spec

echo ""
echo "=== Build complete ==="
ls -la "$BACKEND_DIR/dist/" 2>/dev/null || true
