import time

import pytest

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.models import TransferEvent
from delta_backend.repository import DeltaRepository, RepositoryError

WALLET_ONE = "0x0000000000000000000000000000000000000001"
WALLET_TWO = "0x0000000000000000000000000000000000000002"


async def _pay_exact(repo, exact, log_index):
    return await repo.apply_transfer(
        TransferEvent(
            chain_id=97,
            tx_hash=f"0x{log_index:064x}",
            log_index=log_index,
            block_number=100 + log_index,
            from_address=WALLET_TWO,
            to_address=WALLET_ONE,
            amount_atomic=exact * 10**12,
            amount_minor=exact,
        )
    )


async def _pay(repo, user_id, amount, log_index, promo_code=None):
    inv = await repo.create_invoice(user_id, usdt_to_minor(amount), promo_code=promo_code)
    result = await _pay_exact(repo, int(inv["exact_minor"]), log_index)
    assert result["matched"] is True
    return int(result["deposit_id"]), inv


async def _fetch_one(repo, sql, params=()):
    connection = repo._connection()
    async with repo._lock:
        cursor = await connection.execute(sql, params)
        row = await cursor.fetchone()
    return dict(row) if row else None


async def _make_percent_promo(repo, code, owner, *, bonus_bps=1000, max_redemptions=50):
    return await repo.admin_create_promo_code(
        code=code,
        bonus_type="percent",
        bonus_bps=bonus_bps,
        bonus_fixed_minor=0,
        max_redemptions=max_redemptions,
        min_deposit_minor=0,
        valid_from=None,
        valid_until=None,
        enabled=True,
        created_by=owner,
    )


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


async def test_promo_boosts_principal_once_per_user(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(10, "u", "U", "ru")
        await repo.set_wallet(10, WALLET_ONE)
        await repo.admin_create_promo_code(
            code="PLUS10",
            bonus_type="percent",
            bonus_bps=1000,
            bonus_fixed_minor=0,
            max_redemptions=50,
            min_deposit_minor=0,
            valid_from=None,
            valid_until=None,
            enabled=True,
            created_by=10,
        )
        deposit_id, inv = await _pay(repo, 10, "100", 1, promo_code="PLUS10")
        bonus = usdt_to_minor("10")
        connection = repo._connection()
        async with repo._lock:
            cur = await connection.execute(
                "SELECT principal_minor, bonus_minor FROM deposits WHERE id = ?",
                (deposit_id,),
            )
            row = dict(await cur.fetchone())
        assert int(row["bonus_minor"]) == bonus
        assert int(row["principal_minor"]) == int(inv["exact_minor"]) + bonus

        await repo.ensure_user(11, "u2", "U2", "ru")
        await repo.set_wallet(11, WALLET_TWO)
        # same user cannot redeem again
        with pytest.raises(RepositoryError):
            await repo.create_invoice(10, usdt_to_minor("50"), promo_code="PLUS10")
    finally:
        await repo.close()


async def test_expired_invoice_does_not_consume_promo(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(20, "u", "U", "ru")
        await repo.set_wallet(20, WALLET_ONE)
        await repo.admin_create_promo_code(
            code="ONCE",
            bonus_type="fixed",
            bonus_bps=0,
            bonus_fixed_minor=usdt_to_minor("5"),
            max_redemptions=1,
            min_deposit_minor=0,
            valid_from=None,
            valid_until=None,
            enabled=True,
            created_by=20,
        )
        inv = await repo.create_invoice(20, usdt_to_minor("100"), promo_code="ONCE")
        async with repo.transaction() as connection:
            await connection.execute(
                "UPDATE deposit_invoices SET status='expired', expires_at=? WHERE id=?",
                (int(time.time()) - 10, inv["invoice_id"]),
            )
        # promo still available for new invoice
        inv2 = await repo.create_invoice(20, usdt_to_minor("100"), promo_code="ONCE")
        assert inv2["invoice_id"] != inv["invoice_id"]
    finally:
        await repo.close()


async def test_disabled_promo_still_opens_deposit_without_bonus(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(30, "u", "U", "ru")
        await repo.set_wallet(30, WALLET_ONE)
        promo = await _make_percent_promo(repo, "OFFLATER", 30)

        inv = await repo.create_invoice(30, usdt_to_minor("100"), promo_code="OFFLATER")
        exact = int(inv["exact_minor"])
        await repo.admin_update_promo_code(int(promo["id"]), enabled=False)

        result = await _pay_exact(repo, exact, 5)
        assert result["matched"] is True
        assert int(result["bonus_minor"]) == 0
        assert result["promo_code_id"] is None
        assert result["promo_skipped_reason"] == "promo_disabled"

        deposit = await _fetch_one(
            repo,
            "SELECT principal_minor, bonus_minor, promo_code_id FROM deposits WHERE id = ?",
            (int(result["deposit_id"]),),
        )
        assert int(deposit["principal_minor"]) == exact
        assert int(deposit["bonus_minor"]) == 0
        assert deposit["promo_code_id"] is None

        # the on-chain payment must survive: chain_deposits row matched, invoice paid
        chain = await _fetch_one(
            repo,
            "SELECT invoice_id, matched FROM chain_deposits WHERE amount_minor = ?",
            (exact,),
        )
        assert chain is not None
        assert int(chain["invoice_id"]) == int(inv["invoice_id"])
        assert int(chain["matched"]) == 1
        invoice_row = await _fetch_one(
            repo,
            "SELECT status FROM deposit_invoices WHERE id = ?",
            (int(inv["invoice_id"]),),
        )
        assert invoice_row["status"] == "paid"

        audit = await _fetch_one(
            repo,
            "SELECT details FROM audit_events WHERE event_type = 'promo_redeem_skipped'",
        )
        assert audit is not None
        assert "reason=promo_disabled" in audit["details"]
        assert f"promo={int(promo['id'])}" in audit["details"]

        assert int((await repo.get_promo_by_code("OFFLATER"))["redemption_count"]) == 0
        assert (
            await _fetch_one(repo, "SELECT 1 AS v FROM promo_redemptions LIMIT 1")
        ) is None
    finally:
        await repo.close()


async def test_second_pending_invoice_opens_without_bonus(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(40, "u", "U", "ru")
        await repo.set_wallet(40, WALLET_ONE)
        promo = await _make_percent_promo(repo, "TWICE", 40)

        first_invoice = await repo.create_invoice(40, usdt_to_minor("100"), promo_code="TWICE")
        second_invoice = await repo.create_invoice(40, usdt_to_minor("100"), promo_code="TWICE")
        bonus = usdt_to_minor("10")

        first = await _pay_exact(repo, int(first_invoice["exact_minor"]), 11)
        assert first["matched"] is True
        assert int(first["bonus_minor"]) == bonus
        assert first["promo_skipped_reason"] is None
        assert int(first["promo_code_id"]) == int(promo["id"])

        second = await _pay_exact(repo, int(second_invoice["exact_minor"]), 12)
        assert second["matched"] is True
        assert int(second["bonus_minor"]) == 0
        assert second["promo_code_id"] is None
        assert second["promo_skipped_reason"] == "promo_already_redeemed"

        second_deposit = await _fetch_one(
            repo,
            "SELECT principal_minor, bonus_minor FROM deposits WHERE id = ?",
            (int(second["deposit_id"]),),
        )
        assert int(second_deposit["principal_minor"]) == int(second_invoice["exact_minor"])
        assert int(second_deposit["bonus_minor"]) == 0

        assert int((await repo.get_promo_by_code("TWICE"))["redemption_count"]) == 1
        redemptions = await _fetch_one(
            repo, "SELECT COUNT(*) AS value FROM promo_redemptions"
        )
        assert int(redemptions["value"]) == 1
    finally:
        await repo.close()


async def test_idempotent_invoice_reuse_survives_promo_disable(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(50, "u", "U", "ru")
        await repo.set_wallet(50, WALLET_ONE)
        promo = await _make_percent_promo(repo, "REUSE", 50)

        inv = await repo.create_invoice(
            50, usdt_to_minor("100"), idempotency_key="key-1", promo_code="REUSE"
        )
        await repo.admin_update_promo_code(int(promo["id"]), enabled=False)

        again = await repo.create_invoice(
            50, usdt_to_minor("100"), idempotency_key="key-1", promo_code="REUSE"
        )
        assert again["reused"] is True
        assert int(again["invoice_id"]) == int(inv["invoice_id"])
        assert int(again["exact_minor"]) == int(inv["exact_minor"])
        assert int(again["promo_code_id"]) == int(promo["id"])
        assert int(again["bonus_minor"]) == usdt_to_minor("10")

        # a fresh invoice for the disabled promo is still rejected
        with pytest.raises(RepositoryError):
            await repo.create_invoice(50, usdt_to_minor("100"), promo_code="REUSE")
        # reuse with a mismatched promo binding is still rejected
        with pytest.raises(RepositoryError):
            await repo.create_invoice(50, usdt_to_minor("100"), idempotency_key="key-1")
    finally:
        await repo.close()
