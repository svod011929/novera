from __future__ import annotations

import sqlite3

from delta_backend.config import Settings
from delta_backend.services.safety import SafetyMonitor


def test_scheduled_backup_includes_encrypted_runtime_generation(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    database = data / "delta.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker(value) VALUES ('ok')")
        connection.commit()

    runtime = data / "runtime_secrets"
    runtime.mkdir()
    encrypted = b'{"algorithm":"AES-256-GCM","ciphertext":"opaque"}\n'
    (runtime / "active.enc").write_bytes(encrypted)
    settings = Settings(
        _env_file=None,
        bot_token="123456:SAFETY_BACKUP_TEST_TOKEN",
        database_path=database,
    )
    monitor = object.__new__(SafetyMonitor)
    monitor.settings = settings

    backup, _digest = monitor._create_backup_sync()
    sidecar = backup.with_name(f"{backup.stem}.runtime-config.enc")
    manifest = backup.with_suffix(backup.suffix + ".sha256").read_text(encoding="ascii")
    assert sidecar.read_bytes() == encrypted
    assert backup.name in manifest
    assert sidecar.name in manifest
