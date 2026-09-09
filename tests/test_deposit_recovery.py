from __future__ import annotations

import time

import pytest

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.repository import DeltaRepository, RepositoryError


ADMIN_ID = 900
USER_ID = 100
USER_WALLET = "0x0000000000000000000000000000000000000001"
SENDER_WALLET = "0x0000000000000000000000000000000000000002"
TREASURY_WALLET = "0x0000000000000000000000000000000000000003"


async def _repo(tmp_path) -> DeltaRepository:
    repository = DeltaRepository(
        tmp_path / "deposit-recovery.sqlite3",
        MiniAppSettings(_env_file=None),
    )
    await repository.connect()
    await repository.ensure_user(ADMIN_ID, "admin", "Admin", "ru")
    return repository


async def _create_invoice(
    repository: DeltaRepository,
    *,
    user_id: int = USER_ID,
    amount: str = "100",
    promo_code: str | None = None,
) -> dict[str, object]:
    await repository.ensure_user(user_id, f"user{user_id}", "User", "ru")
    await repository.set_wallet(user_id, USER_WALLET)
    return await repository.create_invoice(
        user_id,
        usdt_to_minor(amount),
        promo_code=promo_code,
    )


def _tx_hash(log_index: int) -> str:
    return f"0x{log_index:064x}"


async def _insert_unmatched(
    repository: DeltaRepository,
    amount_minor: int,
    *,
    log_index: int,
) -> int:
    async with repository.transaction() as connection:
        cursor = await connection.execute(
            """
            INSERT INTO chain_deposits(
                chain_id, tx_hash, log_index, block_number, from_address,
                to_address, amount_atomic, amount_minor, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                97,
                _tx_hash(log_index),
                log_index,
                10_000 + log_index,
                SENDER_WALLET,
                TREASURY_WALLET,
                str(amount_minor * 10**12),
                amount_minor,
                int(time.time()),
            ),
        )
        return int(cursor.lastrowid)


async def _fetch_one(
    repository: DeltaRepository,
    sql: str,
    params: tuple[object, ...] = (),
) -> dict[str, object] | None:
    connection = repository._connection()
    async with repository._lock:
        cursor = await connection.execute(sql, params)
        row = await cursor.fetchone()
    return dict(row) if row else None


async def _make_percent_promo(
    repository: DeltaRepository,
    *,
    code: str,
    bonus_bps: int = 1000,
) -> dict[str, object]:
    return await repository.admin_create_promo_code(
        code=code,
        bonus_type="percent",
        bonus_bps=bonus_bps,
        bonus_fixed_minor=0,
        max_redemptions=10,
        min_deposit_minor=0,
        valid_from=None,
        valid_until=None,
        enabled=True,
        created_by=ADMIN_ID,
    )


async def test_admin_match_uses_on_chain_amount(tmp_path) -> None:
    repository = await _repo(tmp_path)
    try:
        invoice = await _create_invoice(repository)
        chain_amount = usdt_to_minor("100")
        assert chain_amount != int(invoice["exact_minor"])
        chain_deposit_id = await _insert_unmatched(
            repository,
            chain_amount,
            log_index=1,
        )

        result = await repository.admin_match_chain_deposit(
            chain_deposit_id,
            int(invoice["invoice_id"]),
            admin_id=ADMIN_ID,
            reason="  Customer supplied transaction receipt  ",
        )

        assert result == {
            "deposit_id": result["deposit_id"],
            "invoice_id": int(invoice["invoice_id"]),
            "chain_deposit_id": chain_deposit_id,
            "principal_minor": chain_amount,
            "bonus_minor": 0,
            "tx_hash": _tx_hash(1),
            "reused": False,
        }
        deposit = await _fetch_one(
            repository,
            "SELECT * FROM deposits WHERE id = ?",
            (int(result["deposit_id"]),),
        )
        assert deposit is not None
        assert int(deposit["principal_minor"]) == chain_amount

        chain_deposit = await _fetch_one(
            repository,
            "SELECT invoice_id, matched FROM chain_deposits WHERE id = ?",
            (chain_deposit_id,),
        )
        assert chain_deposit == {
            "invoice_id": int(invoice["invoice_id"]),
            "matched": 1,
        }
        paid_invoice = await _fetch_one(
            repository,
            "SELECT status, tx_hash, paid_at FROM deposit_invoices WHERE id = ?",
            (int(invoice["invoice_id"]),),
        )
        assert paid_invoice is not None
        assert paid_invoice["status"] == "paid"
        assert paid_invoice["tx_hash"] == _tx_hash(1)
        assert paid_invoice["paid_at"] is not None

        recovery_audit = await _fetch_one(
            repository,
            "SELECT details FROM audit_events "
            "WHERE event_type = 'deposit_recovery_matched'",
        )
        assert recovery_audit is not None
        details = str(recovery_audit["details"])
        for expected in (
            f"admin={ADMIN_ID}",
            f"chain_deposit={chain_deposit_id}",
            f"invoice={int(invoice['invoice_id'])}",
            f"tx={_tx_hash(1)}",
            f"amount_minor={chain_amount}",
            f"principal_minor={chain_amount}",
            "bonus_minor=0",
            "reason=Customer supplied transaction receipt",
        ):
            assert expected in details
        assert (
            await _fetch_one(
                repository,
                "SELECT 1 AS present FROM audit_events "
                "WHERE event_type = 'deposit_opened'",
            )
            == {"present": 1}
        )
        assert (
            await _fetch_one(
                repository,
                "SELECT event_type FROM user_notifications WHERE user_id = ?",
                (USER_ID,),
            )
            == {"event_type": "deposit_confirmed"}
        )
    finally:
        await repository.close()


async def test_admin_match_allows_expired_invoice(tmp_path) -> None:
    repository = await _repo(tmp_path)
    try:
        invoice = await _create_invoice(repository)
        invoice_id = int(invoice["invoice_id"])
        async with repository.transaction() as connection:
            await connection.execute(
                "UPDATE deposit_invoices SET expires_at = ? WHERE id = ?",
                (int(time.time()) - 1, invoice_id),
            )
        chain_deposit_id = await _insert_unmatched(
            repository,
            usdt_to_minor("99"),
            log_index=2,
        )

        result = await repository.admin_match_chain_deposit(
            chain_deposit_id,
            invoice_id,
            admin_id=ADMIN_ID,
            reason="Recover expired invoice",
        )

        assert result["invoice_id"] == invoice_id
        assert result["principal_minor"] == usdt_to_minor("99")
        paid_invoice = await _fetch_one(
            repository,
            "SELECT status FROM deposit_invoices WHERE id = ?",
            (invoice_id,),
        )
        assert paid_invoice == {"status": "paid"}
    finally:
        await repository.close()


async def test_admin_match_rejects_paid_invoice(tmp_path) -> None:
    repository = await _repo(tmp_path)
    try:
        invoice = await _create_invoice(repository)
        invoice_id = int(invoice["invoice_id"])
        async with repository.transaction() as connection:
            await connection.execute(
                "UPDATE deposit_invoices "
                "SET status = 'paid', tx_hash = ?, paid_at = ? WHERE id = ?",
                ("0xalready-paid", int(time.time()), invoice_id),
            )
        chain_deposit_id = await _insert_unmatched(
            repository,
            usdt_to_minor("100"),
            log_index=3,
        )

        with pytest.raises(RepositoryError, match="Invoice is already paid"):
            await repository.admin_match_chain_deposit(
                chain_deposit_id,
                invoice_id,
                admin_id=ADMIN_ID,
                reason="Must not double credit",
            )

        chain_deposit = await _fetch_one(
            repository,
            "SELECT matched, invoice_id FROM chain_deposits WHERE id = ?",
            (chain_deposit_id,),
        )
        assert chain_deposit == {"matched": 0, "invoice_id": None}
        assert (
            await _fetch_one(
                repository,
                "SELECT COUNT(*) AS value FROM deposits WHERE invoice_id = ?",
                (invoice_id,),
            )
            == {"value": 0}
        )
    finally:
        await repository.close()


async def test_admin_match_rejects_double(tmp_path) -> None:
    repository = await _repo(tmp_path)
    try:
        invoice = await _create_invoice(repository)
        invoice_id = int(invoice["invoice_id"])
        chain_deposit_id = await _insert_unmatched(
            repository,
            usdt_to_minor("100"),
            log_index=4,
        )
        await repository.admin_match_chain_deposit(
            chain_deposit_id,
            invoice_id,
            admin_id=ADMIN_ID,
            reason="First recovery",
        )

        with pytest.raises(RepositoryError, match="Chain deposit is already matched"):
            await repository.admin_match_chain_deposit(
                chain_deposit_id,
                invoice_id,
                admin_id=ADMIN_ID,
                reason="Second recovery",
            )

        assert (
            await _fetch_one(
                repository,
                "SELECT COUNT(*) AS value FROM deposits WHERE invoice_id = ?",
                (invoice_id,),
            )
            == {"value": 1}
        )
    finally:
        await repository.close()


async def test_admin_match_applies_promo_to_invoice_base_amount(tmp_path) -> None:
    repository = await _repo(tmp_path)
    try:
        await _make_percent_promo(repository, code="RECOVER10")
        invoice = await _create_invoice(repository, promo_code="RECOVER10")
        chain_amount = usdt_to_minor("80")
        chain_deposit_id = await _insert_unmatched(
            repository,
            chain_amount,
            log_index=5,
        )

        result = await repository.admin_match_chain_deposit(
            chain_deposit_id,
            int(invoice["invoice_id"]),
            admin_id=ADMIN_ID,
            reason="Recover with invoice promo",
        )

        expected_bonus = usdt_to_minor("10")
        assert result["bonus_minor"] == expected_bonus
        assert result["principal_minor"] == chain_amount + expected_bonus
        redemption = await _fetch_one(
            repository,
            "SELECT bonus_minor, invoice_id FROM promo_redemptions",
        )
        assert redemption == {
            "bonus_minor": expected_bonus,
            "invoice_id": int(invoice["invoice_id"]),
        }
    finally:
        await repository.close()


async def test_admin_match_skips_unavailable_promo_but_credits_transfer(tmp_path) -> None:
    repository = await _repo(tmp_path)
    try:
        promo = await _make_percent_promo(repository, code="RECOVEROFF")
        invoice = await _create_invoice(repository, promo_code="RECOVEROFF")
        await repository.admin_update_promo_code(int(promo["id"]), enabled=False)
        chain_amount = usdt_to_minor("80")
        chain_deposit_id = await _insert_unmatched(
            repository,
            chain_amount,
            log_index=6,
        )

        result = await repository.admin_match_chain_deposit(
            chain_deposit_id,
            int(invoice["invoice_id"]),
            admin_id=ADMIN_ID,
            reason="Credit confirmed transfer",
        )

        assert result["bonus_minor"] == 0
        assert result["principal_minor"] == chain_amount
        deposit = await _fetch_one(
            repository,
            "SELECT bonus_minor, promo_code_id FROM deposits WHERE id = ?",
            (int(result["deposit_id"]),),
        )
        assert deposit == {"bonus_minor": 0, "promo_code_id": None}
        promo_audit = await _fetch_one(
            repository,
            "SELECT details FROM audit_events WHERE event_type = 'promo_redeem_skipped'",
        )
        assert promo_audit is not None
        assert "reason=promo_disabled" in str(promo_audit["details"])
    finally:
        await repository.close()


async def test_admin_match_requires_reason_and_reports_missing_records(tmp_path) -> None:
    repository = await _repo(tmp_path)
    try:
        invoice = await _create_invoice(repository)
        invoice_id = int(invoice["invoice_id"])

        with pytest.raises(RepositoryError, match="Recovery reason is required"):
            await repository.admin_match_chain_deposit(
                999_999,
                invoice_id,
                admin_id=ADMIN_ID,
                reason="   ",
            )
        with pytest.raises(RepositoryError, match="Chain deposit not found"):
            await repository.admin_match_chain_deposit(
                999_999,
                invoice_id,
                admin_id=ADMIN_ID,
                reason="Locate transfer",
            )

        chain_deposit_id = await _insert_unmatched(
            repository,
            usdt_to_minor("100"),
            log_index=7,
        )
        with pytest.raises(RepositoryError, match="Invoice not found"):
            await repository.admin_match_chain_deposit(
                chain_deposit_id,
                999_999,
                admin_id=ADMIN_ID,
                reason="Locate invoice",
            )
    finally:
        await repository.close()


@pytest.mark.parametrize(
    ("user_update", "expected_error"),
    [
        ("blocked = 1", "Account is blocked"),
        ("payout_address = NULL", "User payout wallet is not configured"),
    ],
)
async def test_admin_match_rejects_ineligible_invoice_user(
    tmp_path,
    user_update: str,
    expected_error: str,
) -> None:
    repository = await _repo(tmp_path)
    try:
        invoice = await _create_invoice(repository)
        invoice_id = int(invoice["invoice_id"])
        async with repository.transaction() as connection:
            await connection.execute(
                f"UPDATE users SET {user_update} WHERE telegram_id = ?",
                (USER_ID,),
            )
        chain_deposit_id = await _insert_unmatched(
            repository,
            usdt_to_minor("100"),
            log_index=8,
        )

        with pytest.raises(RepositoryError, match=expected_error):
            await repository.admin_match_chain_deposit(
                chain_deposit_id,
                invoice_id,
                admin_id=ADMIN_ID,
                reason="Ineligible account must not be credited",
            )

        chain_deposit = await _fetch_one(
            repository,
            "SELECT matched FROM chain_deposits WHERE id = ?",
            (chain_deposit_id,),
        )
        assert chain_deposit == {"matched": 0}
    finally:
        await repository.close()


async def test_list_unmatched_chain_deposits_is_newest_first_and_serializes_amount(
    tmp_path,
) -> None:
    repository = await _repo(tmp_path)
    try:
        oldest_id = await _insert_unmatched(
            repository,
            usdt_to_minor("1.25"),
            log_index=9,
        )
        matched_id = await _insert_unmatched(
            repository,
            usdt_to_minor("2.5"),
            log_index=10,
        )
        newest_id = await _insert_unmatched(
            repository,
            usdt_to_minor("3.000001"),
            log_index=11,
        )
        async with repository.transaction() as connection:
            await connection.execute(
                "UPDATE chain_deposits SET matched = 1 WHERE id = ?",
                (matched_id,),
            )

        rows = await repository.list_unmatched_chain_deposits(limit=2)

        assert [int(row["id"]) for row in rows] == [newest_id, oldest_id]
        assert [row["amount"] for row in rows] == ["3.000001", "1.25"]
        assert [int(row["amount_minor"]) for row in rows] == [
            usdt_to_minor("3.000001"),
            usdt_to_minor("1.25"),
        ]
        assert all(int(row["matched"]) == 0 for row in rows)
    finally:
        await repository.close()
