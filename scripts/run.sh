#!/usr/bin/env bash
# QuantSync ETL - Unix/macOS startup script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")/backend"
cd "$BACKEND_DIR"

# Check for venv
if [ -f "venv/bin/python" ]; then
    echo "Using venv..."
    venv/bin/python -m app.tray_app
else
    echo "Using system Python..."
    python3 -m app.tray_app
fi
