import logging
import sqlite3
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import get_settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_CONFIGURED = False
_CONFIG_LOCK = threading.Lock()


class SQLiteLogHandler(logging.Handler):
    """Persists WARNING+ logs into SQLite system_logs without recursive loops."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(level=logging.WARNING)
        self.db_path = db_path
        self._local = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._local, "emitting", False):
            return
        self._local.emitting = True
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path), timeout=3.0)
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS system_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        level TEXT NOT NULL,
                        logger_name TEXT NOT NULL,
                        message TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'backend',
                        request_id TEXT
                    )
                    """
                )
                request_id = getattr(record, "request_id", None)
                created_at = datetime.now(timezone.utc).isoformat()
                message = self.format(record)
                conn.execute(
                    """
                    INSERT INTO system_logs (created_at, level, logger_name, message, source, request_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (created_at, record.levelname, record.name, message, "backend", request_id),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            # Never raise from a logging handler
            pass
        finally:
            self._local.emitting = False


def setup_logging(db_path: Path | None = None, log_file_path: Path | None = None) -> None:
    global _CONFIGURED
    with _CONFIG_LOCK:
        if _CONFIGURED:
            return
        settings = get_settings()
        target_log_file = log_file_path or settings.resolved_log_path
        target_db_path = db_path or settings.resolved_db_path

        target_log_file.parent.mkdir(parents=True, exist_ok=True)
        target_db_path.parent.mkdir(parents=True, exist_ok=True)

        root_logger = logging.getLogger()
        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        root_logger.setLevel(level)

        formatter = logging.Formatter(_LOG_FORMAT)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        file_handler = RotatingFileHandler(
            filename=str(target_log_file),
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        sqlite_handler = SQLiteLogHandler(db_path=target_db_path)
        sqlite_handler.setFormatter(logging.Formatter("%(message)s"))

        root_logger.handlers.clear()
        root_logger.addHandler(stream_handler)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(sqlite_handler)

        _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
