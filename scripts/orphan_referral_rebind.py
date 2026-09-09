#!/usr/bin/env python3
"""Orphan referral report + confirm-gated rebind (ops)."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

import aiosqlite

# Allow running from repo root without install
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from delta_backend.api_settings import MiniAppSettings
from delta_backend.orphan_referral import (
    FOCUS_REFERRER_DEFAULT,
    apply_rebind_map,
    build_orphan_report,
    suggested_apply_map,
)
from delta_backend.repository import DeltaRepository


def _load_map(path: Path) -> dict[int, int]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("map file must be a JSON object {user_id: referrer_id}")
    mapping: dict[int, int] = {}
    for raw_user_id, referrer_id in raw.items():
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError):
            raise SystemExit(
                "map user IDs must be integer strings and referrer IDs must be integers"
            ) from None
        if isinstance(referrer_id, bool) or not isinstance(referrer_id, int):
            raise SystemExit(
                "map user IDs must be integer strings and referrer IDs must be integers"
            )
        mapping[user_id] = referrer_id
    return mapping


def _write_report(out_dir: Path, report: dict) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "orphan_referral_report.json"
    csv_path = out_dir / "orphan_referral_report.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "user_id", "username", "first_name", "created_at", "deposit_count",
        "has_deposits", "evidence", "suggested_referrer_id", "suggested_ok",
        "focus_leader", "apply_eligible",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow({k: row.get(k) for k in fields})
    return json_path, csv_path


async def _open_repo(db: Path) -> DeltaRepository:
    db = _require_existing_db(db)
    repo = DeltaRepository(db, MiniAppSettings(_env_file=None))
    await repo.connect()
    return repo


def _require_existing_db(db: Path) -> Path:
    db = db.expanduser()
    if not db.is_file():
        raise SystemExit(f"database file does not exist: {db}")
    return db.resolve()


async def _open_repo_read_only(db: Path) -> DeltaRepository:
    db = _require_existing_db(db)
    repo = DeltaRepository(db, MiniAppSettings(_env_file=None))
    connection = await aiosqlite.connect(f"{db.as_uri()}?mode=ro", uri=True)
    try:
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA query_only = ON")
    except BaseException:
        await connection.close()
        raise
    repo.connection = connection
    return repo


async def cmd_report(args: argparse.Namespace) -> int:
    repo = await _open_repo_read_only(Path(args.db))
    try:
        report = await build_orphan_report(
            repo, focus_referrer_id=int(args.focus_referrer)
        )
        json_path, csv_path = _write_report(Path(args.out_dir), report)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        print(f"wrote {json_path}")
        print(f"wrote {csv_path}")
        return 0
    finally:
        await repo.close()


async def _resolve_mapping(args: argparse.Namespace, repo: DeltaRepository) -> dict[int, int]:
    if args.from_file:
        return _load_map(Path(args.from_file))
    if args.from_suggested:
        report = await build_orphan_report(
            repo, focus_referrer_id=int(args.focus_referrer)
        )
        return suggested_apply_map(report)
    raise SystemExit("need --from-suggested or --from-file")


async def cmd_dry_run(args: argparse.Namespace) -> int:
    repo = await _open_repo_read_only(Path(args.db))
    try:
        mapping = await _resolve_mapping(args, repo)
        result = await apply_rebind_map(
            repo, mapping, changed_by=int(args.changed_by), dry_run=True
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        await repo.close()


async def cmd_apply(args: argparse.Namespace) -> int:
    if not args.confirm:
        print("refusing apply without --confirm", file=sys.stderr)
        return 2
    repo = await _open_repo(Path(args.db))
    try:
        mapping = await _resolve_mapping(args, repo)
        result = await apply_rebind_map(
            repo, mapping, changed_by=int(args.changed_by), dry_run=False
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not result["errors"] else 1
    finally:
        await repo.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to live/app SQLite DB")
    parser.add_argument("--focus-referrer", type=int, default=FOCUS_REFERRER_DEFAULT)
    parser.add_argument("--out-dir", default=str(ROOT / "_cursor_output"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_report = sub.add_parser("report")
    p_report.set_defaults(func=cmd_report)

    def add_map_flags(p: argparse.ArgumentParser) -> None:
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--from-suggested", action="store_true")
        g.add_argument("--from-file", type=str)
        p.add_argument("--changed-by", type=int, required=True)

    p_dry = sub.add_parser("dry-run")
    add_map_flags(p_dry)
    p_dry.set_defaults(func=cmd_dry_run)

    p_apply = sub.add_parser("apply")
    add_map_flags(p_apply)
    p_apply.add_argument("--confirm", action="store_true")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
