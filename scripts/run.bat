@echo off
REM QuantSync ETL - Windows startup script

cd /d "%~dp0\..\backend"

REM Check for venv
if exist "venv\Scripts\python.exe" (
    echo Using venv...
    venv\Scripts\python.exe -m app.tray_app
) else (
    echo Using system Python...
    python -m app.tray_app
)
pause
