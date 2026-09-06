from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKEN_LITERAL_RE = re.compile(r"\b[0-9]{6,16}:[A-Za-z0-9_-]{30,}\b")


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_bootstrap_stub_is_one_file_fail_closed_installer() -> None:
    stub = _text("deploy/NOVERA_BOOTSTRAP_INSTALLER.stub.sh")
    assert stub.count("\n__NOVERA_BOOTSTRAP_PAYLOAD__\n") == 1
    assert stub.index("exit 0") < stub.index("\n__NOVERA_BOOTSTRAP_PAYLOAD__\n")
    assert "read -r -s" in stub
    assert "Existing NOVERA/GFORT state detected" in stub
    assert "CHAIN_ENABLED=false" in stub
    assert "DEPOSITS_ENABLED=false" in stub
    assert "INVESTMENTS_ENABLED=false" in stub
    assert "PAYOUTS_ENABLED=false" in stub
    assert "REFERRAL_ENABLED=false" in stub
    assert "RUNTIME_CONFIG_KEY_FILE=/run/secrets/runtime_config_key" in stub
    assert TOKEN_LITERAL_RE.search(stub) is None


def test_bootstrap_compose_mounts_only_bootstrap_secrets() -> None:
    compose = _text("compose.vps.yml")
    assert "runtime_config_key" in compose
    assert "bot_token" in compose
    assert "bsc_rpc_url:" not in compose
    assert "bsc_wss_url:" not in compose
    assert "seed_phrase:" not in compose


def test_backup_and_restore_include_encrypted_generation() -> None:
    backup = _text("deploy/backup.sh")
    restore = _text("deploy/restore-backup.sh")
    assert "runtime_secrets/active.enc" in backup
    assert "runtime-config.enc" in backup
    assert "sha256sum" in backup
    assert "NOVERA_CONFIRM_RESTORE" in restore
    assert "PRAGMA integrity_check" in restore
    assert "Restore failed; returning to the pre-restore state" in restore


def test_builder_includes_dockerignore_and_round_trip_checks() -> None:
    builder = _text("scripts/build_bootstrap_installer.ps1")
    assert '"Dockerfile", ".dockerignore", "compose.vps.yml"' in builder
    assert "PAYLOAD_SHA256.txt" in builder
    assert "FromBase64String" in builder
    assert "runtime_config_key.txt" in builder
    assert "Token-shaped literal found outside test fixtures" in builder


def test_safe_update_is_staged_with_rollback_and_frontend_mode() -> None:
    update = _text("deploy/safe-update.sh")
    assert "--mode" in update
    assert "frontend" in update
    assert "rolling back" in update.lower() or "Rolling back" in update
    assert "deploy/backup.sh" in update
    assert "GFORT_FRONTEND_DIR" in update
    assert "wait_ready" in update
    check = _text("deploy/post-update-check.sh")
    assert "/health" in check
    assert "/ready" in check
    wrapper = _text("scripts/safe_update_remote.ps1")
    assert "safe-update.sh" in wrapper
    rehearsal = _text("deploy/backup-rehearsal.sh")
    assert "PRAGMA integrity_check" in rehearsal
    assert "REHEARSAL_OK" in rehearsal
