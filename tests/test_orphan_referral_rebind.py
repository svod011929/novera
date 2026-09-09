import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from delta_backend.api_settings import MiniAppSettings
from delta_backend.orphan_referral import (
    apply_rebind_map,
    build_orphan_report,
    classify_ref_evidence,
    parse_ref_start_param,
    suggested_apply_map,
)
from delta_backend.repository import DeltaRepository
from scripts import orphan_referral_rebind as rebind_cli


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


async def test_apply_null_guard_survives_concurrent_bind(tmp_path, monkeypatch) -> None:
    repo = DeltaRepository(tmp_path / "o5-race.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(300, "other", "Other", "ru")
        await repo.ensure_user(200, "child", "Child", "ru")
        original_set_referrer = repo.admin_set_user_referrer

        async def bind_between_check_and_update(
            user_id: int,
            identifier: str | None,
            changed_by: int,
            **kwargs,
        ) -> dict[str, object]:
            await original_set_referrer(user_id, "300", changed_by)
            return await original_set_referrer(
                user_id,
                identifier,
                changed_by,
                **kwargs,
            )

        monkeypatch.setattr(
            repo,
            "admin_set_user_referrer",
            bind_between_check_and_update,
        )
        result = await apply_rebind_map(
            repo, {200: 100}, changed_by=100, dry_run=False
        )

        connection = repo._connection()
        async with repo._lock:
            row = await (
                await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = 200"
                )
            ).fetchone()
        assert int(row["referrer_id"]) == 300
        assert not result["changed"]
        assert any(s["reason"] == "already_bound" for s in result["skipped"])
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
            audit = await (
                await connection.execute(
                    "SELECT details FROM audit_events "
                    "WHERE event_type = 'user_referrer_changed' "
                    "ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()
        assert int(row["referrer_id"]) == 100
        assert adj["old_referrer_id"] is None
        assert int(adj["new_referrer_id"]) == 100
        assert int(adj["changed_by"]) == 100
        assert "reason=orphan_rebind" in str(audit["details"])
    finally:
        await repo.close()


@pytest.mark.parametrize(
    "payload",
    [
        '{"200": true}',
        '{"200": 100.5}',
        '{"200.0": 100}',
    ],
)
def test_load_map_rejects_non_integer_ids(tmp_path, payload: str) -> None:
    map_path = tmp_path / "map.json"
    map_path.write_text(payload, encoding="utf-8")

    with pytest.raises(SystemExit, match="integers"):
        rebind_cli._load_map(map_path)


async def test_cli_report_writes_files(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db = tmp_path / "cli.sqlite3"
    out = tmp_path / "out"
    repo = DeltaRepository(db, MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(200, "orphan", "Orphan", "ru")
    finally:
        await repo.close()
    subprocess.check_call(
        [
            sys.executable,
            str(repo_root / "scripts" / "orphan_referral_rebind.py"),
            "--db",
            str(db),
            "--out-dir",
            str(out),
            "report",
        ],
        cwd=repo_root,
    )
    assert (out / "orphan_referral_report.csv").exists()
    assert (out / "orphan_referral_report.json").exists()


async def test_cli_report_does_not_call_repository_connect(
    tmp_path, monkeypatch
) -> None:
    db = tmp_path / "read-only.sqlite3"
    out = tmp_path / "out"
    repo = DeltaRepository(db, MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(200, "orphan", "Orphan", "ru")
    finally:
        await repo.close()

    async def fail_if_called(_repo) -> None:
        raise AssertionError("DeltaRepository.connect() must not be used for report")

    monkeypatch.setattr(DeltaRepository, "connect", fail_if_called)
    args = argparse.Namespace(
        db=str(db),
        focus_referrer=100,
        out_dir=str(out),
    )

    assert await rebind_cli.cmd_report(args) == 0


async def test_cli_dry_run_does_not_call_repository_connect(
    tmp_path, monkeypatch
) -> None:
    db = tmp_path / "dry-run-read-only.sqlite3"
    map_path = tmp_path / "map.json"
    repo = DeltaRepository(db, MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        await repo.ensure_user(200, "orphan", "Orphan", "ru")
    finally:
        await repo.close()
    map_path.write_text(json.dumps({"200": 100}), encoding="utf-8")

    async def fail_if_called(_repo) -> None:
        raise AssertionError("DeltaRepository.connect() must not be used for dry-run")

    monkeypatch.setattr(DeltaRepository, "connect", fail_if_called)
    args = argparse.Namespace(
        db=str(db),
        from_file=str(map_path),
        from_suggested=False,
        focus_referrer=100,
        changed_by=100,
    )

    assert await rebind_cli.cmd_dry_run(args) == 0


def test_cli_report_missing_database_does_not_create_file(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db = tmp_path / "missing.sqlite3"
    out = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "orphan_referral_rebind.py"),
            "--db",
            str(db),
            "--out-dir",
            str(out),
            "report",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "database file does not exist" in result.stderr
    assert not db.exists()


def test_cli_apply_missing_database_does_not_create_file(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db = tmp_path / "missing-apply.sqlite3"
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"200": 100}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "orphan_referral_rebind.py"),
            "--db",
            str(db),
            "apply",
            "--from-file",
            str(map_path),
            "--changed-by",
            "100",
            "--confirm",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "database file does not exist" in result.stderr
    assert not db.exists()


def test_cli_apply_without_confirm_exits_two(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db = tmp_path / "missing-unconfirmed.sqlite3"
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"200": 100}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "orphan_referral_rebind.py"),
            "--db",
            str(db),
            "apply",
            "--from-file",
            str(map_path),
            "--changed-by",
            "100",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "refusing apply without --confirm" in result.stderr
    assert not db.exists()


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
