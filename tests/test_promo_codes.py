import pytest

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.repository import DeltaRepository, RepositoryError


async def test_admin_create_and_list_promo_codes(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        created = await repo.admin_create_promo_code(
            code=" welcome10 ",
            bonus_type="percent",
            bonus_bps=1000,
            bonus_fixed_minor=0,
            max_redemptions=100,
            min_deposit_minor=0,
            valid_from=None,
            valid_until=None,
            enabled=True,
            created_by=1,
        )
        assert created["code"] == "WELCOME10"
        assert created["bonus_type"] == "percent"
        assert int(created["bonus_bps"]) == 1000
        rows = await repo.admin_list_promo_codes()
        assert any(r["code"] == "WELCOME10" for r in rows)
        with pytest.raises(RepositoryError):
            await repo.admin_create_promo_code(
                code="welcome10",
                bonus_type="percent",
                bonus_bps=500,
                bonus_fixed_minor=0,
                max_redemptions=10,
                min_deposit_minor=0,
                valid_from=None,
                valid_until=None,
                enabled=True,
                created_by=1,
            )
    finally:
        await repo.close()


async def test_admin_update_promo_code_and_get_by_code(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        created = await repo.admin_create_promo_code(
            code="SUMMER",
            bonus_type="fixed",
            bonus_bps=0,
            bonus_fixed_minor=usdt_to_minor("5"),
            max_redemptions=10,
            min_deposit_minor=0,
            valid_from=None,
            valid_until=None,
            enabled=True,
            created_by=1,
        )
        updated = await repo.admin_update_promo_code(int(created["id"]), enabled=False)
        assert updated["enabled"] is False

        fetched = await repo.get_promo_by_code(" summer ")
        assert fetched is not None
        assert fetched["code"] == "SUMMER"
        assert fetched["enabled"] is False

        assert await repo.get_promo_by_code("NOPE") is None

        with pytest.raises(RepositoryError):
            await repo.admin_update_promo_code(999999, enabled=True)
    finally:
        await repo.close()


async def test_admin_create_promo_code_validation(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")

        with pytest.raises(RepositoryError):
            await repo.admin_create_promo_code(
                code="   ",
                bonus_type="percent",
                bonus_bps=1000,
                bonus_fixed_minor=0,
                max_redemptions=10,
                min_deposit_minor=0,
                valid_from=None,
                valid_until=None,
                enabled=True,
                created_by=1,
            )

        with pytest.raises(RepositoryError):
            await repo.admin_create_promo_code(
                code="x" * 33,
                bonus_type="percent",
                bonus_bps=1000,
                bonus_fixed_minor=0,
                max_redemptions=10,
                min_deposit_minor=0,
                valid_from=None,
                valid_until=None,
                enabled=True,
                created_by=1,
            )

        with pytest.raises(RepositoryError):
            await repo.admin_create_promo_code(
                code="BADTYPE",
                bonus_type="mystery",
                bonus_bps=1000,
                bonus_fixed_minor=0,
                max_redemptions=10,
                min_deposit_minor=0,
                valid_from=None,
                valid_until=None,
                enabled=True,
                created_by=1,
            )

        with pytest.raises(RepositoryError):
            await repo.admin_create_promo_code(
                code="ZEROPERCENT",
                bonus_type="percent",
                bonus_bps=0,
                bonus_fixed_minor=0,
                max_redemptions=10,
                min_deposit_minor=0,
                valid_from=None,
                valid_until=None,
                enabled=True,
                created_by=1,
            )

        with pytest.raises(RepositoryError):
            await repo.admin_create_promo_code(
                code="ZEROFIXED",
                bonus_type="fixed",
                bonus_bps=0,
                bonus_fixed_minor=0,
                max_redemptions=10,
                min_deposit_minor=0,
                valid_from=None,
                valid_until=None,
                enabled=True,
                created_by=1,
            )

        with pytest.raises(RepositoryError):
            await repo.admin_create_promo_code(
                code="MIXED",
                bonus_type="percent",
                bonus_bps=1000,
                bonus_fixed_minor=usdt_to_minor("5"),
                max_redemptions=10,
                min_deposit_minor=0,
                valid_from=None,
                valid_until=None,
                enabled=True,
                created_by=1,
            )
    finally:
        await repo.close()


async def test_compute_promo_bonus_minor() -> None:
    from delta_backend.repository import compute_promo_bonus_minor

    assert compute_promo_bonus_minor(
        {"bonus_type": "percent", "bonus_bps": 1000}, usdt_to_minor("100")
    ) == usdt_to_minor("10")
    assert compute_promo_bonus_minor(
        {"bonus_type": "fixed", "bonus_fixed_minor": usdt_to_minor("5")}, usdt_to_minor("100")
    ) == usdt_to_minor("5")
    with pytest.raises(RepositoryError):
        compute_promo_bonus_minor({"bonus_type": "unknown"}, usdt_to_minor("100"))
