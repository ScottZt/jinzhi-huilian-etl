"""Application configuration — centralized constants."""
import os
import socket
from pathlib import Path
from typing import Optional

# ---- Port configuration ----
DEFAULT_PORT = int(os.environ.get("JINZHIHUILIAN_PORT", os.environ.get("JINZHIHUI_PORT", "8080")))
PORT_RANGE = (DEFAULT_PORT, DEFAULT_PORT + 19)  # 8080-8099 by default


def find_free_port(start: Optional[int] = None, end: Optional[int] = None) -> int:
    """Find the first available port in the configured range."""
    if start is None:
        start = DEFAULT_PORT
    if end is None:
        end = DEFAULT_PORT + 19
    for p in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    raise RuntimeError(f"No free port in range [{start}-{end}]")


# ---- Resource path ----

def resource_path(relative: str, *, app_subdir: bool = True) -> str:
    """
    Get absolute path to resource, works for dev and PyInstaller.

    Args:
        relative: Relative path from the app root.
        app_subdir: If True (dev), prepend 'app/' to the relative path.
                    PyInstaller uses a flat structure, so this is auto-detected.
    """
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller: resources are at the bundle root
        base = Path(sys._MEIPASS)
        candidate = base / relative
        if app_subdir:
            alt = base / "app" / relative
            if alt.exists():
                candidate = alt
        return str(candidate)
    else:
        # Dev: resources are relative to this module's parent (app/)
        base = Path(__file__).parent
        return str(base / relative)
