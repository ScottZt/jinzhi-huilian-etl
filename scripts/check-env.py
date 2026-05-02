"""Environment check script for QuantSync ETL.

Validates Python version, available packages, port availability, and disk permissions.
"""
import sys
import os
import socket
import platform
import importlib
from pathlib import Path


def check_python_version() -> tuple[bool, str]:
    """Python 3.10+ required, 3.13 has known PyInstaller issues."""
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        return False, f"Python {major}.{minor} found, need 3.10+. Install Python 3.10-3.12."
    if major == 3 and minor >= 13:
        return True, f"Python {major}.{minor} found (PyInstaller may have compatibility issues, consider 3.12)"
    return True, f"Python {major}.{minor} OK"


def check_package(name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(name)
        return True, f"{name} OK"
    except ImportError:
        return False, f"{name} NOT installed"


def check_port(port: int = 8080) -> tuple[bool, str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True, f"Port {port} available"
        except OSError:
            return False, f"Port {port} in use"


def check_disk_writable() -> tuple[bool, str]:
    data_dir = _get_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True, f"Data dir {data_dir} writable"
    except Exception as e:
        return False, f"Data dir {data_dir} not writable: {e}"


def _get_data_dir() -> Path:
    if os.environ.get("QUANTSYNC_DATA_DIR"):
        return Path(os.environ["QUANTSYNC_DATA_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "QuantSyncETL"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "QuantSyncETL"
    else:
        return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "QuantSyncETL"


REQUIRED_PACKAGES = [
    "fastapi", "uvicorn", "pydantic", "pandas", "numpy",
    "sqlalchemy", "pymysql", "psycopg2", "duckdb",
    "openpyxl", "apscheduler", "watchdog", "chardet", "pyarrow",
    "pystray", "PIL", "psutil",
]

OPTIONAL_PACKAGES = [
    "clickhouse_driver",
    "pyinstaller",
]


def main():
    print("=" * 60)
    print("QuantSync ETL - Environment Check")
    print("=" * 60)
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print()

    errors = []

    # Python version
    ok, msg = check_python_version()
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {msg}")
    if not ok:
        errors.append(msg)

    # Required packages
    print("\n--- Required Packages ---")
    for pkg in REQUIRED_PACKAGES:
        ok, msg = check_package(pkg)
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {msg}")
        if not ok:
            errors.append(msg)

    # Optional packages
    print("\n--- Optional Packages ---")
    for pkg in OPTIONAL_PACKAGES:
        ok, msg = check_package(pkg)
        status = "OK" if ok else "WARN"
        print(f"  [{status}] {msg}")

    # Port
    print("\n--- Network ---")
    ok, msg = check_port(8080)
    status = "OK" if ok else "WARN"
    print(f"  [{status}] {msg}")

    # Disk
    print("\n--- Storage ---")
    ok, msg = check_disk_writable()
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {msg}")
    if not ok:
        errors.append(msg)

    print()
    if errors:
        print("=" * 60)
        print("ERRORS FOUND:")
        for e in errors:
            print(f"  - {e}")
        print("=" * 60)
        return 1
    else:
        print("All checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
