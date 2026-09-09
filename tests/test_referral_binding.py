from delta_backend.api_settings import MiniAppSettings
from delta_backend.repository import DeltaRepository


async def test_ensure_user_binds_referrer_on_first_touch(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "ref.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(100, "leader", "Leader", "ru")
        # Existing user created without referrer (e.g. /stats before Mini App).
        await repo.ensure_user(200, "newbie", "Newbie", "ru", referrer_id=None)
        await repo.ensure_user(200, "newbie", "Newbie", "ru", referrer_id=100)

        connection = repo._connection()
        async with repo._lock:
            row = await (
                await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = 200"
                )
            ).fetchone()
        assert int(row["referrer_id"]) == 100

        # Second referrer must not overwrite first-touch.
        await repo.ensure_user(300, "other", "Other", "ru")
        await repo.ensure_user(200, "newbie", "Newbie", "ru", referrer_id=300)
        async with repo._lock:
            row = await (
                await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = 200"
                )
            ).fetchone()
        assert int(row["referrer_id"]) == 100
    finally:
        await repo.close()


async def test_ensure_user_new_with_referrer(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "ref2.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(10, "leader", "Leader", "ru")
        await repo.ensure_user(20, "partner", "Partner", "ru", referrer_id=10)
        connection = repo._connection()
        async with repo._lock:
            row = await (
                await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = 20"
                )
            ).fetchone()
            count = await (
                await connection.execute(
                    "SELECT COUNT(*) AS n FROM users WHERE referrer_id = 10"
                )
            ).fetchone()
        assert int(row["referrer_id"]) == 10
        assert int(count["n"]) == 1
    finally:
        await repo.close()


async def test_ensure_user_ignores_missing_referrer(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "ref3.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(20, "partner", "Partner", "ru", referrer_id=999999)
        connection = repo._connection()
        async with repo._lock:
            row = await (
                await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = 20"
                )
            ).fetchone()
        assert row["referrer_id"] is None
    finally:
        await repo.close()
