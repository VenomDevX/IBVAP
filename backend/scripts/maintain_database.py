"""Database integrity and recoverable backup utility.

Examples:
  python scripts/maintain_database.py check
  python scripts/maintain_database.py backup
"""

import argparse
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.db import get_database
from src.paths import output_dir


def sqlite_path() -> Path:
    url = get_database().db_url
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise SystemExit("This maintenance command currently supports SQLite only")
    return Path(url.removeprefix(prefix)).resolve()


def integrity_check() -> bool:
    source = sqlite_path()
    with sqlite3.connect(source) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    print(f"integrity_check: {result}")
    print(f"foreign_key_errors: {len(foreign_key_errors)}")
    return result == "ok" and not foreign_key_errors


def backup() -> Path:
    source = sqlite_path()
    destination_dir = output_dir() / "backups"
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = destination_dir / f"ibvap-{stamp}.db"
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    print(f"backup: {destination}")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or back up the IBVAP database")
    parser.add_argument("command", choices=("check", "backup"))
    args = parser.parse_args()
    if args.command == "check":
        return 0 if integrity_check() else 1
    destination = backup()
    with sqlite3.connect(destination) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"backup_integrity_check: {result}")
    return 0 if result == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
