#!/usr/bin/env bash
# Build script for Windows PyInstaller (run in Git Bash or WSL)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"

echo "=== QuantSync ETL Build (Windows) ==="
echo "Project: $PROJECT_DIR"

# Check Python
if ! command -v python &> /dev/null; then
    echo "ERROR: Python not found. Please install Python 3.10-3.12"
    exit 1
fi

echo "Python: $(python --version)"

cd "$BACKEND_DIR"

# Install dependencies
echo ""
echo "=== Installing dependencies ==="
if [ -d "venv" ]; then
    source venv/Scripts/activate
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
