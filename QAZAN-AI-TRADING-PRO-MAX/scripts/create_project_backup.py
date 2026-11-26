#!/usr/bin/env python3
"""Create a clean, full ZIP backup of QAZAN-AI-TRADING-PRO-MAX without build bloat or secrets."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUPS_DIR = PROJECT_ROOT / "backups"
ARCHIVE_NAME = "QAZAN-AI-TRADING-PRO-MAX-v1.0.0-open-source.zip"
ARCHIVE_PATH = BACKUPS_DIR / ARCHIVE_NAME
TMP_ARCHIVE_PATH = BACKUPS_DIR / f".{ARCHIVE_NAME}.tmp"

EXCLUDED_DIR_NAMES = {
    "node_modules",
    ".git",
    "dist",
    ".backups",
    "backups",
    ".gradle",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "data",
    "logs",
}

EXCLUDED_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".DS_Store",
    "database.db",
    "local.properties",
}

EXCLUDED_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".db",
    ".db-wal",
    ".db-shm",
    ".sqlite",
    ".sqlite3",
    ".keystore",
    ".jks",
    ".log",
    ".apk",
    ".aab",
)


def should_skip_dir(rel_parts: tuple[str, ...]) -> bool:
    for part in rel_parts:
        if part in EXCLUDED_DIR_NAMES:
            return True
    return False


def should_skip_file(path: Path) -> bool:
    if path.name in EXCLUDED_FILE_NAMES:
        return True
    lower = path.name.lower()
    return lower.endswith(EXCLUDED_SUFFIXES)


def build_zip_backup() -> dict[str, object]:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    files_added = 0

    with zipfile.ZipFile(TMP_ARCHIVE_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            root_path = Path(root)
            rel_root = root_path.relative_to(PROJECT_ROOT)

            # Prune excluded directories in-place before descending
            dirs[:] = sorted(
                d for d in dirs if not should_skip_dir(rel_root.parts + (d,))
            )

            for fname in sorted(files):
                fpath = root_path / fname
                if not fpath.is_file() or should_skip_file(fpath):
                    continue
                rel_file = fpath.relative_to(PROJECT_ROOT)
                arcname = f"QAZAN-AI-TRADING-PRO-MAX/{rel_file.as_posix()}"
                zf.write(fpath, arcname=arcname)
                files_added += 1

    TMP_ARCHIVE_PATH.replace(ARCHIVE_PATH)
    data_bytes = ARCHIVE_PATH.read_bytes()
    sha256 = hashlib.sha256(data_bytes).hexdigest()

    return {
        "filename": ARCHIVE_NAME,
        "path": str(ARCHIVE_PATH.relative_to(PROJECT_ROOT)),
        "files_count": files_added,
        "size_bytes": len(data_bytes),
        "sha256": sha256,
    }


if __name__ == "__main__":
    summary = build_zip_backup()
    print(json.dumps(summary, ensure_ascii=False))
