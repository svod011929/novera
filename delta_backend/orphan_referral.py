from __future__ import annotations

import time
from typing import Any

from delta_backend.repository import DeltaRepository, RepositoryError

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
                user_id,
                str(referrer_id),
                changed_by,
                require_null_referrer=True,
                reason="orphan_rebind",
            )
        except RepositoryError as exc:
            errors.append({"user_id": user_id, "reason": str(exc)})
            continue
        if result.get("changed"):
            changed.append(entry)
        else:
            skipped.append(
                {
                    "user_id": user_id,
                    "reason": str(result.get("reason") or "unchanged"),
                }
            )

    return {
        "dry_run": dry_run,
        "would_change": would_change,
        "changed": changed,
        "skipped": skipped,
        "errors": errors,
    }
