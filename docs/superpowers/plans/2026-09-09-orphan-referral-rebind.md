# Orphan Referral Report + Safe Rebind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a read-only orphan-referrer report plus a confirm-gated batch rebind (`NULL → ref` only) with evidence rules A+B for leader `967903658`.

**Architecture:** Testable library in `delta_backend/orphan_referral.py` builds report rows from SQLite (`users` + `web_login_tokens`) and applies binds only via existing `DeltaRepository.admin_set_user_referrer`. Thin CLI `scripts/orphan_referral_rebind.py` exposes `report` | `dry-run` | `apply`. No HTTP / Mini App UI.

**Tech Stack:** Python 3.12 / aiosqlite via `DeltaRepository` / argparse / pytest / CSV+JSON files

**Spec:** `docs/superpowers/specs/2026-09-09-orphan-referral-rebind-design.md`

## Global Constraints

- Apply only when target `referrer_id IS NULL` at transaction time; never overwrite.
- `--from-suggested` only rows with `evidence == "token_ref"` AND `suggested_ok`.
- No-evidence / conflict rows require `--from-file` explicit map (focus B).
- Historical `referral_rewards` / `referral_accruals` are never rewritten (reuse `admin_set_user_referrer`).
- No end-user “new partner” notifications on bulk rebind.
- Default focus leader id: `967903658` (overridable via `--focus-referrer`).
- No new admin HTTP routes in this plan.
- Commits only when the owner explicitly asks (project git rule); plan commit steps are optional checkpoints.

## File map

| File | Role |
|------|------|
| `delta_backend/orphan_referral.py` | Parse `ref_*`, build report rows, dry-run/apply map |
| `scripts/orphan_referral_rebind.py` | CLI entrypoint |
| `tests/test_orphan_referral_rebind.py` | Unit + repo integration tests |
| `_cursor_output/ORPHAN_REFERRAL_REBIND.md` | VPS runbook after script works |

---

### Task 1: Report builder (evidence + suggested_ok)

**Files:**
- Create: `delta_backend/orphan_referral.py`
- Test: `tests/test_orphan_referral_rebind.py`

**Interfaces:**
- Produces:
  - `FOCUS_REFERRER_DEFAULT = 967903658`
  - `def parse_ref_start_param(start_param: str | None) -> int | None`
  - `def classify_ref_evidence(ref_ids: list[int]) -> tuple[str, int | None]`  
    → `("none", None)` | `("token_ref", id)` | `("conflict", None)`
  - `async def build_orphan_report(repo: DeltaRepository, *, focus_referrer_id: int = FOCUS_REFERRER_DEFAULT) -> dict`  
    → `{"rows": list[dict], "summary": dict}`  
    Row keys: `user_id`, `username`, `first_name`, `created_at`, `deposit_count`, `has_deposits`, `evidence`, `suggested_referrer_id`, `suggested_ok`, `focus_967903658` (bool name kept for focus id **value** equality to `focus_referrer_id` — implement as `focus_leader`: bool in code, CSV column `focus_leader`; also include `focus_referrer_id` in summary. Spec column `focus_967903658` → emit CSV header `focus_leader` plus summary key `focus_referrer_id` to avoid lying when flag overrides.)
  - Actually match spec CSV: column `focus_leader` (bool) meaning “suggested_referrer_id == focus_referrer_id”. Spec name `focus_967903658` is the default case; use `focus_leader` in code/CSV.
  - `apply_eligible` = evidence == `token_ref` and suggested_ok and referrer still null (always true for orphan query).

- [ ] **Step 1: Write failing tests**

Create `tests/test_orphan_referral_rebind.py`:

```python
from delta_backend.api_settings import MiniAppSettings
from delta_backend.orphan_referral import (
    classify_ref_evidence,
    parse_ref_start_param,
    build_orphan_report,
)
from delta_backend.repository import DeltaRepository


def test_parse_ref_start_param() -> None:
    assert parse_ref_start_param("ref_967903658") == 967903658
    assert parse_ref_start_param("ref_") is None
    assert parse_ref_start_param("promo_x") is None
    assert parse_ref_start_param(None) is None


def test_classify_ref_evidence() -> None:
    assert classify_ref_evidence([]) == ("none", None)
    assert classify_ref_evidence([10, 10]) == ("token_ref", 10)
    assert classify_ref_evidence([10, 20]) == ("conflict", None)


async def test_build_orphan_report_token_evidence(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "o.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(200, "orphan", "Orphan", "ru")
        # Simulate leftover login token with ref
        connection = repo._connection()
        async with repo._lock:
            await connection.execute(
                """
                INSERT INTO web_login_tokens(
                    token_hash, telegram_id, username, first_name, language,
                    start_param, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("hash1", 200, "orphan", "Orphan", "ru", "ref_100", 9999999999, 1),
            )
            await connection.commit()
        report = await build_orphan_report(repo, focus_referrer_id=100)
        rows = {r["user_id"]: r for r in report["rows"]}
        assert 200 in rows
        assert rows[200]["evidence"] == "token_ref"
        assert rows[200]["suggested_referrer_id"] == 100
        assert rows[200]["suggested_ok"] is True
        assert rows[200]["apply_eligible"] is True
        assert rows[200]["focus_leader"] is True
        assert report["summary"]["orphans"] >= 1
        assert report["summary"]["apply_eligible"] >= 1
    finally:
        await repo.close()


async def test_build_orphan_report_conflict_not_eligible(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "o2.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(10, "a", "A", "ru")
        await repo.ensure_user(11, "b", "B", "ru")
        await repo.ensure_user(200, "orphan", "Orphan", "ru")
        connection = repo._connection()
        async with repo._lock:
            await connection.execute(
                """
                INSERT INTO web_login_tokens(
                    token_hash, telegram_id, username, first_name, language,
                    start_param, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "h1", 200, "orphan", "Orphan", "ru", "ref_10", 9999999999, 1,
                    "h2", 200, "orphan", "Orphan", "ru", "ref_11", 9999999999, 2,
                ),
            )
            await connection.commit()
        report = await build_orphan_report(repo, focus_referrer_id=10)
        row = next(r for r in report["rows"] if r["user_id"] == 200)
        assert row["evidence"] == "conflict"
        assert row["apply_eligible"] is False
    finally:
        await repo.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orphan_referral_rebind.py::test_parse_ref_start_param tests/test_orphan_referral_rebind.py::test_classify_ref_evidence tests/test_orphan_referral_rebind.py::test_build_orphan_report_token_evidence -v`  
Expected: FAIL (module/import not found)

- [ ] **Step 3: Implement `delta_backend/orphan_referral.py` (report only)**

```python
from __future__ import annotations

import time
from typing import Any

from delta_backend.repository import DeltaRepository

FOCUS_REFERRER_DEFAULT = 967903658


def parse_ref_start_param(start_param: str | None) -> int | None:
    if not start_param or not start_param.startswith("ref_"):
        return None
    raw = start_param.removeprefix("ref_")
    if not raw.isdigit():
        return None
    return int(raw)


def classify_ref_evidence(ref_ids: list[int]) -> tuple[str, int | None]:
    unique = sorted(set(ref_ids))
    if not unique:
        return ("none", None)
    if len(unique) == 1:
        return ("token_ref", unique[0])
    return ("conflict", None)


async def _referrer_would_be_ok(
    repo: DeltaRepository, user_id: int, referrer_id: int
) -> bool:
    if referrer_id == user_id:
        return False
    connection = repo._connection()
    async with repo._lock:
        cursor = await connection.execute(
            "SELECT telegram_id, referrer_id FROM users WHERE telegram_id = ?",
            (referrer_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return False
        seen: set[int] = set()
        ancestor_id: int | None = referrer_id
        for _ in range(1000):
            if ancestor_id is None:
                return True
            if ancestor_id == user_id:
                return False
            if ancestor_id in seen:
                return False
            seen.add(ancestor_id)
            cursor = await connection.execute(
                "SELECT referrer_id FROM users WHERE telegram_id = ?",
                (ancestor_id,),
            )
            ancestor = await cursor.fetchone()
            if ancestor is None or ancestor["referrer_id"] is None:
                ancestor_id = None
            else:
                ancestor_id = int(ancestor["referrer_id"])
        return False


async def build_orphan_report(
    repo: DeltaRepository,
    *,
    focus_referrer_id: int = FOCUS_REFERRER_DEFAULT,
) -> dict[str, Any]:
    connection = repo._connection()
    async with repo._lock:
        orphans = await (
            await connection.execute(
                """
                SELECT u.telegram_id AS user_id, u.username, u.first_name, u.created_at,
                       (SELECT COUNT(*) FROM deposits d WHERE d.user_id = u.telegram_id) AS deposit_count
                FROM users u
                WHERE u.referrer_id IS NULL
                ORDER BY u.created_at DESC, u.telegram_id DESC
                """
            )
        ).fetchall()
        tokens = await (
            await connection.execute(
                """
                SELECT telegram_id, start_param
                FROM web_login_tokens
                WHERE start_param IS NOT NULL AND start_param LIKE 'ref_%'
                """
            )
        ).fetchall()

    refs_by_user: dict[int, list[int]] = {}
    for tok in tokens:
        ref = parse_ref_start_param(tok["start_param"])
        if ref is None:
            continue
        refs_by_user.setdefault(int(tok["telegram_id"]), []).append(ref)

    rows: list[dict[str, Any]] = []
    for o in orphans:
        user_id = int(o["user_id"])
        evidence, suggested = classify_ref_evidence(refs_by_user.get(user_id, []))
        suggested_ok = False
        if suggested is not None:
            suggested_ok = await _referrer_would_be_ok(repo, user_id, suggested)
        deposit_count = int(o["deposit_count"] or 0)
        apply_eligible = evidence == "token_ref" and suggested_ok
        focus_leader = suggested is not None and suggested == focus_referrer_id
        rows.append(
            {
                "user_id": user_id,
                "username": o["username"] or "",
                "first_name": o["first_name"] or "",
                "created_at": int(o["created_at"] or 0),
                "deposit_count": deposit_count,
                "has_deposits": deposit_count > 0,
                "evidence": evidence,
                "suggested_referrer_id": suggested,
                "suggested_ok": suggested_ok,
                "focus_leader": focus_leader,
                "apply_eligible": apply_eligible,
            }
        )

    summary = {
        "orphans": len(rows),
        "token_ref": sum(1 for r in rows if r["evidence"] == "token_ref"),
        "conflict": sum(1 for r in rows if r["evidence"] == "conflict"),
        "none": sum(1 for r in rows if r["evidence"] == "none"),
        "suggested_ok": sum(1 for r in rows if r["suggested_ok"]),
        "apply_eligible": sum(1 for r in rows if r["apply_eligible"]),
        "focus_leader": sum(1 for r in rows if r["focus_leader"]),
        "focus_referrer_id": focus_referrer_id,
        "generated_at": int(time.time()),
    }
    return {"rows": rows, "summary": summary}
```

Fix SQLite multi-row INSERT in conflict test if needed (two separate executes). Adjust test Step 1 INSERT to two statements if the multi-VALUES form is awkward.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_orphan_referral_rebind.py -v -k "parse or classify or build_orphan"`  
Expected: PASS

- [ ] **Step 5: Commit (only if owner asked)**

```bash
git add delta_backend/orphan_referral.py tests/test_orphan_referral_rebind.py
git commit -m "feat: orphan referral report builder with token evidence"
```

---

### Task 2: Dry-run + apply via `admin_set_user_referrer`

**Files:**
- Modify: `delta_backend/orphan_referral.py`
- Test: `tests/test_orphan_referral_rebind.py`

**Interfaces:**
- Consumes: `DeltaRepository.admin_set_user_referrer(user_id, identifier, changed_by)`
- Produces:
  - `def suggested_apply_map(report: dict) -> dict[int, int]`  
    → `{user_id: referrer_id}` for `apply_eligible` rows only
  - `async def apply_rebind_map(repo, mapping: dict[int, int], *, changed_by: int, dry_run: bool) -> dict`  
    → `{"would_change"|"changed": [...], "skipped": [...], "errors": [...]}`  
    Skip if user missing, referrer already set, or `admin_set_user_referrer` raises / returns `changed: False` unexpectedly.  
    On dry_run: do not call mutating path — re-check NULL + `_referrer_would_be_ok` only.  
    On apply: call `admin_set_user_referrer(user_id, str(referrer_id), changed_by)` only if still NULL.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_orphan_referral_rebind.py`:

```python
from delta_backend.orphan_referral import apply_rebind_map, suggested_apply_map


async def test_suggested_map_excludes_none_evidence(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "o3.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(200, "orphan", "Orphan", "ru")
        report = await build_orphan_report(repo, focus_referrer_id=100)
        assert suggested_apply_map(report) == {}
    finally:
        await repo.close()


async def test_apply_dry_run_no_write(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "o4.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(200, "orphan", "Orphan", "ru")
        result = await apply_rebind_map(
            repo, {200: 100}, changed_by=100, dry_run=True
        )
        assert result["would_change"]
        connection = repo._connection()
        async with repo._lock:
            row = await (
                await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = 200"
                )
            ).fetchone()
        assert row["referrer_id"] is None
    finally:
        await repo.close()


async def test_apply_only_null_referrer(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "o5.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(300, "other", "Other", "ru")
        await repo.ensure_user(200, "child", "Child", "ru", referrer_id=300)
        result = await apply_rebind_map(
            repo, {200: 100}, changed_by=100, dry_run=False
        )
        assert any(s["reason"] == "already_bound" for s in result["skipped"])
        connection = repo._connection()
        async with repo._lock:
            row = await (
                await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = 200"
                )
            ).fetchone()
        assert int(row["referrer_id"]) == 300
    finally:
        await repo.close()


async def test_apply_binds_null_and_audits(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "o6.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(200, "orphan", "Orphan", "ru")
        result = await apply_rebind_map(
            repo, {200: 100}, changed_by=100, dry_run=False
        )
        assert any(c["user_id"] == 200 for c in result["changed"])
        connection = repo._connection()
        async with repo._lock:
            row = await (
                await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = 200"
                )
            ).fetchone()
            adj = await (
                await connection.execute(
                    "SELECT old_referrer_id, new_referrer_id, changed_by "
                    "FROM referrer_adjustments WHERE user_id = 200"
                )
            ).fetchone()
        assert int(row["referrer_id"]) == 100
        assert adj["old_referrer_id"] is None
        assert int(adj["new_referrer_id"]) == 100
        assert int(adj["changed_by"]) == 100
    finally:
        await repo.close()


async def test_apply_rejects_cycle(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "o7.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(200, "mid", "Mid", "ru", referrer_id=100)
        # 100's referrer cleared? keep 100 orphan of tree root; try bind 100 under 200
        result = await apply_rebind_map(
            repo, {100: 200}, changed_by=100, dry_run=False
        )
        assert result["errors"] or result["skipped"]
        connection = repo._connection()
        async with repo._lock:
            row = await (
                await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = 100"
                )
            ).fetchone()
        assert row["referrer_id"] is None
    finally:
        await repo.close()
```

- [ ] **Step 2: Run new tests — expect FAIL**

Run: `python -m pytest tests/test_orphan_referral_rebind.py -v -k "apply or suggested"`  
Expected: FAIL (functions missing)

- [ ] **Step 3: Implement apply helpers**

Append to `delta_backend/orphan_referral.py`:

```python
from delta_backend.repository import RepositoryError


def suggested_apply_map(report: dict[str, Any]) -> dict[int, int]:
    out: dict[int, int] = {}
    for row in report.get("rows") or []:
        if row.get("apply_eligible") and row.get("suggested_referrer_id") is not None:
            out[int(row["user_id"])] = int(row["suggested_referrer_id"])
    return out


async def apply_rebind_map(
    repo: DeltaRepository,
    mapping: dict[int, int],
    *,
    changed_by: int,
    dry_run: bool,
) -> dict[str, Any]:
    would_change: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for user_id, referrer_id in sorted(mapping.items()):
        user_id = int(user_id)
        referrer_id = int(referrer_id)
        connection = repo._connection()
        async with repo._lock:
            cursor = await connection.execute(
                "SELECT referrer_id FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            target = await cursor.fetchone()
        if target is None:
            skipped.append({"user_id": user_id, "reason": "user_not_found"})
            continue
        if target["referrer_id"] is not None:
            skipped.append({"user_id": user_id, "reason": "already_bound"})
            continue
        ok = await _referrer_would_be_ok(repo, user_id, referrer_id)
        if not ok:
            errors.append({"user_id": user_id, "reason": "invalid_referrer_or_cycle"})
            continue
        entry = {"user_id": user_id, "referrer_id": referrer_id}
        if dry_run:
            would_change.append(entry)
            continue
        try:
            result = await repo.admin_set_user_referrer(
                user_id, str(referrer_id), changed_by
            )
        except RepositoryError as exc:
            errors.append({"user_id": user_id, "reason": str(exc)})
            continue
        if result.get("changed"):
            changed.append(entry)
        else:
            skipped.append({"user_id": user_id, "reason": "unchanged"})

    return {
        "dry_run": dry_run,
        "would_change": would_change,
        "changed": changed,
        "skipped": skipped,
        "errors": errors,
    }
```

- [ ] **Step 4: Run full orphan tests**

Run: `python -m pytest tests/test_orphan_referral_rebind.py -v`  
Expected: all PASS

- [ ] **Step 5: Commit (only if owner asked)**

```bash
git add delta_backend/orphan_referral.py tests/test_orphan_referral_rebind.py
git commit -m "feat: safe orphan referral rebind dry-run and apply"
```

---

### Task 3: CLI `scripts/orphan_referral_rebind.py`

**Files:**
- Create: `scripts/orphan_referral_rebind.py`
- Create: `_cursor_output/ORPHAN_REFERRAL_REBIND.md`
- Test: smoke via `python scripts/orphan_referral_rebind.py --help` (no DB)

**Interfaces:**
- Consumes: `build_orphan_report`, `suggested_apply_map`, `apply_rebind_map`, `MiniAppSettings`, `DeltaRepository`
- CLI:
  - `--db PATH` (required)
  - `--focus-referrer INT` default `967903658`
  - `--changed-by INT` required for dry-run/apply (admin telegram id)
  - `--out-dir PATH` default `_cursor_output`
  - subcommands:
    - `report` → write `orphan_referral_report.json` + `.csv`, print summary
    - `dry-run --from-suggested` | `dry-run --from-file map.json`
    - `apply --confirm --from-suggested` | `apply --confirm --from-file map.json`  
      Without `--confirm`, apply must exit 2 with message.

JSON map file format: `{"200": 100, "201": 100}` (string or int keys OK).

- [ ] **Step 1: Implement CLI**

```python
#!/usr/bin/env python3
"""Orphan referral report + confirm-gated rebind (ops)."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

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
    return {int(k): int(v) for k, v in raw.items()}


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
    repo = DeltaRepository(db, MiniAppSettings(_env_file=None))
    await repo.connect()
    return repo


async def cmd_report(args: argparse.Namespace) -> int:
    repo = await _open_repo(Path(args.db))
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
    repo = await _open_repo(Path(args.db))
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
```

- [ ] **Step 2: Help smoke**

Run: `python scripts/orphan_referral_rebind.py --help`  
Expected: usage with `report` / `dry-run` / `apply`

- [ ] **Step 3: Write runbook `_cursor_output/ORPHAN_REFERRAL_REBIND.md`**

Include:
- Stop/start not required for read-only `report`
- Typical live DB path on VPS (discover from `/opt/gfort` env or `safe_update` docs — look up actual path while writing; if unknown, document `find` / `systemctl` / `.env` steps)
- Example:

```bash
cd /opt/gfort
python scripts/orphan_referral_rebind.py --db /path/to/app.sqlite3 report
python scripts/orphan_referral_rebind.py --db ... --changed-by <ADMIN_TG_ID> dry-run --from-suggested
# Focus B manual map:
# echo '{"123": 967903658}' > /tmp/rebind.json
python scripts/orphan_referral_rebind.py --db ... --changed-by <ADMIN_TG_ID> dry-run --from-file /tmp/rebind.json
python scripts/orphan_referral_rebind.py --db ... --changed-by <ADMIN_TG_ID> apply --confirm --from-file /tmp/rebind.json
```

- Spot-check team for `967903658` after apply.
- Reminder: deploy first-touch fix separately so new orphans stop.

- [ ] **Step 4: End-to-end local CLI on tmp DB**

Create a tiny fixture DB in pytest or one-off shell: ensure users + token, run `report`, assert CSV exists. Prefer a pytest that shells out **or** calls `_write_report` — keep one test:

```python
async def test_cli_report_writes_files(tmp_path) -> None:
    db = tmp_path / "cli.sqlite3"
    repo = DeltaRepository(db, MiniAppSettings(_env_file=None))
    await repo.connect()
    await repo.ensure_user(100, "leader", "Leader", "ru")
    await repo.ensure_user(200, "orphan", "Orphan", "ru")
    await repo.close()
    out = tmp_path / "out"
    from scripts import orphan_referral_rebind as cli  # may need importlib
```

If `scripts` is not a package, test via `subprocess`:

```python
import subprocess, sys
subprocess.check_call(
    [sys.executable, "scripts/orphan_referral_rebind.py", "--db", str(db), "--out-dir", str(out), "report"],
    cwd=repo_root,
)
assert (out / "orphan_referral_report.csv").exists()
```

- [ ] **Step 5: Full pytest file green**

Run: `python -m pytest tests/test_orphan_referral_rebind.py -v`  
Expected: PASS

- [ ] **Step 6: Commit (only if owner asked)**

```bash
git add scripts/orphan_referral_rebind.py tests/test_orphan_referral_rebind.py _cursor_output/ORPHAN_REFERRAL_REBIND.md
git commit -m "feat: orphan referral rebind CLI and runbook"
```

---

### Task 4: Live VPS report (ops, no apply yet)

**Files:** none in repo (outputs under `_cursor_output/` copied locally if desired)

- [ ] **Step 1:** After code is on the machine that can read the live DB (deploy branch **or** scp script + library), run `report` only.
- [ ] **Step 2:** Paste/summarize summary counts to owner: orphans, token_ref, apply_eligible, focus_leader.
- [ ] **Step 3:** Do **not** run `apply` until owner confirms the CSV / explicit JSON map.

---

## Spec coverage self-check

| Spec item | Task |
|-----------|------|
| Read-only report CSV/JSON + summary | T1, T3 |
| Evidence from `web_login_tokens` only | T1 |
| conflict / none excluded from suggested | T1, T2 |
| Focus leader flag + B via `--from-file` | T1, T3 |
| dry-run / apply --confirm | T2, T3 |
| Reuse `admin_set_user_referrer` + audit | T2 |
| No reward rewrite / no partner spam | T2 (by reuse + no notify calls) |
| No HTTP UI | — (omitted) |
| VPS workflow | T3 runbook, T4 |
| Tests listed in success criteria | T1–T3 |

## Placeholder scan

None intentional. Live DB path resolved when writing the runbook from VPS/`deploy` docs.

## Type consistency

- `build_orphan_report` → `dict` with `rows` / `summary`
- `suggested_apply_map(report) -> dict[int, int]`
- `apply_rebind_map(..., dry_run: bool) -> dict` with `would_change` / `changed` / `skipped` / `errors`
- CSV column `focus_leader` (spec’s `focus_967903658` generalized)
