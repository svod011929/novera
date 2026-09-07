import argparse
import sqlite3
import time
from pathlib import Path

from .config import Settings


def backup_database(source: Path, destination: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"Database does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as target_db:
        source_db.backup(target_db)
        cursor = target_db.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an online NOVERA SQLite backup")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = Settings().database_path
    destination = args.output or Path("backups") / time.strftime(
        "delta-%Y%m%d-%H%M%S.sqlite3",
        time.gmtime(),
    )
    saved = backup_database(source, destination)
    print(saved)


if __name__ == "__main__":
    main()
