import logging
import time
import hashlib
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from app.persistence import sqlite_repo

logger = logging.getLogger(__name__)


class FileImportHandler(FileSystemEventHandler):
    """Watchdog handler that triggers import when new files arrive."""

    def __init__(self, config: Dict[str, Any], callback: Callable[[str], None]):
        self.config = config
        self.callback = callback
        self.pattern = config.get("pattern", "*.csv")
        self.processed_files: Dict[str, str] = {}
        self.lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_new_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        self._handle_new_file(event.src_path)

    def _handle_new_file(self, file_path: str):
        path = Path(file_path)
        if not path.match(self.pattern):
            return

        file_md5 = self._compute_md5(file_path)
        with self.lock:
            if file_md5 in self.processed_files.values():
                logger.info(f"File already processed: {file_path}")
                return
            self.processed_files[file_path] = file_md5

        logger.info(f"New file detected: {file_path}, triggering import")
        try:
            self.callback(file_path)
        except Exception as e:
            logger.error(f"Import failed for {file_path}: {e}")

    def _compute_md5(self, file_path: str) -> str:
        md5 = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception:
            return ""

    def load_processed_files(self):
        """Load processed file records from DB."""
        try:
            for imp in sqlite_repo.list_bulk_imports():
                if imp.get("status") == "completed":
                    self.processed_files[imp.get("file_path", "")] = imp.get("file_md5", "")
        except Exception as e:
            logger.warning(f"Failed to load processed files: {e}")


class FileWatcher:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._observers: Dict[str, Observer] = {}
            cls._instance._handlers: Dict[str, FileImportHandler] = {}
        return cls._instance

    def start_watcher(self, connection_id: str, callback: Optional[Callable[[str], None]] = None):
        conn = sqlite_repo.get_connection(connection_id)
        if not conn or conn["type"] != "folder_watch":
            raise ValueError(f"Connection {connection_id} is not a folder_watch type")

        if connection_id in self._observers:
            return f"Watcher for {connection_id} is already running"

        dir_path = conn["config"].get("dir_path")
        pattern = conn["config"].get("pattern", "*.csv")
        polling_sec = conn["config"].get("polling_sec", 30)

        if not dir_path or not Path(dir_path).exists():
            raise ValueError(f"Directory does not exist: {dir_path}")

        if callback is None:
            callback = self._default_import_callback

        handler = FileImportHandler(conn["config"], callback)
        handler.load_processed_files()

        observer = Observer()
        observer.schedule(handler, dir_path, recursive=True)
        observer.start()

        self._observers[connection_id] = observer
        self._handlers[connection_id] = handler

        logger.info(f"Started file watcher on {dir_path} (pattern: {pattern}, polling: {polling_sec}s)")
        return f"File watcher started on {dir_path}"

    def stop_watcher(self, connection_id: str) -> str:
        observer = self._observers.pop(connection_id, None)
        if observer:
            observer.stop()
            observer.join(timeout=5)
            self._handlers.pop(connection_id, None)
            return f"Watcher for {connection_id} stopped"
        return f"No active watcher for {connection_id}"

    def list_watchers(self) -> List[Dict[str, Any]]:
        result = []
        for conn_id, observer in self._observers.items():
            handler = self._handlers.get(conn_id)
            result.append({
                "connection_id": conn_id,
                "running": observer.is_alive(),
                "pattern": handler.config.get("pattern") if handler else "N/A",
                "processed_count": len(handler.processed_files) if handler else 0,
            })
        return result

    def stop_all(self):
        for conn_id in list(self._observers.keys()):
            self.stop_watcher(conn_id)

    def _default_import_callback(self, file_path: str):
        """Automatically create a bulk import record for the new file."""
        from app.core.bulk_import_engine import get_engine
        import uuid

        db_conn = self._find_default_db_connection()
        if not db_conn:
            logger.warning("No default DB connection found, skipping auto-import")
            return

        md5 = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5.update(chunk)
        except Exception:
            pass

        import_id = str(uuid.uuid4())
        record = {
            "id": import_id,
            "source_connection_id": "auto-file-watch",
            "target_connection_id": db_conn["id"],
            "target_table": Path(file_path).stem,
            "file_path": file_path,
            "file_md5": md5.hexdigest(),
            "config_json": {
                "field_mappings": [],
                "import_mode": "incremental",
                "batch_size": 5000,
                "parallel_threads": 1,
                "enable_checkpoint": True,
            },
            "total_rows": 0,
            "imported_rows": 0,
            "last_imported_index": 0,
            "status": "pending",
            "error_at_row": None,
            "error_message": None,
            "started_at": None,
            "completed_at": None,
        }
        sqlite_repo.save_bulk_import(record)
        logger.info(f"Auto-import created for {file_path} (id: {import_id})")

        try:
            engine = get_engine()
            engine.start_import(import_id)
        except Exception as e:
            logger.error(f"Auto-import execution failed: {e}")

    def _find_default_db_connection(self) -> Optional[Dict]:
        connections = sqlite_repo.list_connections()
        db_types = {"mysql", "postgresql", "duckdb", "clickhouse"}
        for conn in connections:
            if conn["type"] in db_types:
                return conn
        return None


_watcher = FileWatcher()


def get_file_watcher() -> FileWatcher:
    return _watcher
