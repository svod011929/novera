"""V10.5 / V10.6 financial regression golden amounts.

Pins schedule math that must not change without written owner approval:
daily profit, principal return, referral accruals and floor division.
"""

from __future__ import annotations

import time

import pytest

from delta_backend.amounts import AmountError, calculate_bps, usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.models import TransferEvent
from delta_backend.repository import DeltaRepository


WALLET_A = "0x00000000000000000000000000000000000000Aa"
WALLET_B = "0x00000000000000000000000000000000000000Bb"


@pytest.mark.parametrize(
    ("value_minor", "bps", "expected"),
    [
        (100_000_000, 1000, 10_000_000),  # 100 USDT · 10% = 10 USDT
        (1_000_001, 1000, 100_000),  # floor: 0.1000001 → 0.1 USDT
        (7_000_000, 800, 560_000),  # 7 USDT · 8% = 0.56
        (10_000_000, 250, 250_000),  # 10 USDT · 2.5% = 0.25
        (1, 1, 0),  # tiny amount floors to zero
        (0, 1000, 0),
    ],
)
def test_calculate_bps_matches_v10_5_floor_contract(
    value_minor: int, bps: int, expected: int
) -> None:
    assert calculate_bps(value_minor, bps) == expected


def test_calculate_bps_rejects_negatives() -> None:
    with pytest.raises(AmountError):
        calculate_bps(-1, 1000)
    with pytest.raises(AmountError):
        calculate_bps(1000, -1)


def test_default_terms_match_v10_5_marketing_board() -> None:
    settings = MiniAppSettings(_env_file=None)
    assert settings.daily_profit_bps == 1000
    assert settings.payout_days == 20
    assert settings.referral_level_bps == (800, 400, 250, 150, 100)
    assert settings.referral_personal_thresholds_usdt == (50, 100, 300, 500, 1000)
    assert settings.referral_line_thresholds_usdt == (100, 300, 500, 1500, 5000)


async def test_exact_100_usdt_admin_investment_schedule_without_invoice_tail(
    tmp_path,
) -> None:
    """Admin open-investment uses exact principal — pins marketing 10%/day math."""
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "finance-exact.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(30, "exact", "Exact", "ru")
        await repository.set_wallet(30, WALLET_A)
        opened = await repository.admin_open_investment(
            30,
            100_000_000,
            30,
            "Golden fixture",
            "golden_exact_100usdt_01",
        )
        deposit_id = int(opened["id"])
        assert int(opened["principal_minor"]) == 100_000_000

        async with repository.transaction() as connection:
            await connection.execute(
                "UPDATE deposits SET next_payout_at = ? WHERE id = ?",
                (int(time.time()) - 1, deposit_id),
            )
        await repository.schedule_due_payouts()

        connection = repository._connection()
        async with repository._lock:
            cursor = await connection.execute(
                "SELECT amount_minor FROM payouts WHERE source_deposit_id = ? AND subtype = ''",
                (deposit_id,),
            )
            assert int((await cursor.fetchone())["amount_minor"]) == 10_000_000
    finally:
        await repository.close()


async def _pay(repository: DeltaRepository, user_id: int, amount: str, log_index: int) -> int:
    invoice = await repository.create_invoice(user_id, usdt_to_minor(amount))
    exact = int(invoice["exact_minor"])
    result = await repository.apply_transfer(
        TransferEvent(
            chain_id=97,
            tx_hash=f"0x{log_index:064x}",
            log_index=log_index,
            block_number=100 + log_index,
            from_address=WALLET_B,
            to_address=WALLET_A,
            amount_atomic=exact * 10**12,
            amount_minor=exact,
        )
    )
    assert result["matched"] is True
    return int(result["deposit_id"])


async def test_schedule_golden_amounts_for_100_usdt_and_l1_referral(tmp_path) -> None:
    """~100 USDT principal at default terms → 10% daily, L1 accrual = 8% of daily."""
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "finance-gold.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(1, "leader", "Leader", "ru")
        await repository.set_wallet(1, WALLET_A)
        await repository.ensure_user(2, "partner", "Partner", "ru", referrer_id=1)
        await repository.set_wallet(2, WALLET_B)

        # Leader needs ≥50 USDT personal + ≥100 USDT line for L1 qualification.
        await _pay(repository, 1, "50", 1)
        referred = await _pay(repository, 2, "100", 2)

        connection = repository._connection()
        async with repository._lock:
            cursor = await connection.execute(
                "SELECT principal_minor FROM deposits WHERE id = ?",
                (referred,),
            )
            principal_minor = int((await cursor.fetchone())["principal_minor"])
        # Invoice unique fractional tail keeps principal ≥ base amount.
        assert principal_minor >= 100_000_000
        expected_daily = calculate_bps(principal_minor, business.daily_profit_bps)
        expected_l1 = calculate_bps(expected_daily, 800)

        async with repository.transaction() as connection:
            await connection.execute(
                "UPDATE deposits SET next_payout_at = ? WHERE id = ?",
                (int(time.time()) - 1, referred),
            )

        scheduled = await repository.schedule_due_payouts()
        assert scheduled >= 1

        async with repository._lock:
            cursor = await connection.execute(
                "SELECT amount_minor, payout_day, subtype FROM payouts "
                "WHERE source_deposit_id = ? AND kind = 'daily' ORDER BY id",
                (referred,),
            )
            payouts = [dict(row) for row in await cursor.fetchall()]
            assert len(payouts) == 1
            assert payouts[0]["amount_minor"] == expected_daily
            assert payouts[0]["payout_day"] == 1
            assert payouts[0]["subtype"] == ""

            cursor = await connection.execute(
                "SELECT amount_minor, level, percent_bps FROM referral_accruals "
                "WHERE source_deposit_id = ? AND referrer_id = 1",
                (referred,),
            )
            accruals = [dict(row) for row in await cursor.fetchall()]
            assert len(accruals) == 1
            assert accruals[0]["level"] == 1
            assert accruals[0]["percent_bps"] == 800
            assert accruals[0]["amount_minor"] == expected_l1
    finally:
        await repository.close()


async def test_final_day_schedules_profit_and_principal_separately(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "finance-final.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(10, "solo", "Solo", "ru")
        await repository.set_wallet(10, WALLET_A)
        deposit_id = await _pay(repository, 10, "100", 1)

        connection = repository._connection()
        async with repository._lock:
            cursor = await connection.execute(
                "SELECT principal_minor FROM deposits WHERE id = ?",
                (deposit_id,),
            )
            principal_minor = int((await cursor.fetchone())["principal_minor"])
        expected_daily = calculate_bps(principal_minor, business.daily_profit_bps)

        # Fast-forward to the last schedule day without inventing payouts.
        async with repository.transaction() as connection:
            await connection.execute(
                """
                UPDATE deposits
                SET scheduled_days = ?, next_payout_at = ?
                WHERE id = ?
                """,
                (19, int(time.time()) - 1, deposit_id),
            )

        scheduled = await repository.schedule_due_payouts()
        assert scheduled == 2  # day-20 profit + principal

        async with repository._lock:
            cursor = await connection.execute(
                "SELECT kind, subtype, payout_day, amount_minor FROM payouts "
                "WHERE source_deposit_id = ? ORDER BY id",
                (deposit_id,),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
            assert rows == [
                {
                    "kind": "daily",
                    "subtype": "",
                    "payout_day": 20,
                    "amount_minor": expected_daily,
                },
                {
                    "kind": "daily",
                    "subtype": "principal",
                    "payout_day": 20,
                    "amount_minor": principal_minor,
                },
            ]

        assert sum(r["amount_minor"] for r in rows) == expected_daily + principal_minor
        assert await repository.schedule_due_payouts() == 0
    finally:
        await repository.close()


async def test_full_cycle_profit_total_is_two_hundred_percent(tmp_path) -> None:
    """20 days · 10% of principal = 200% profit; principal is returned separately."""
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "finance-cycle.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(20, "cycle", "Cycle", "ru")
        await repository.set_wallet(20, WALLET_A)
        deposit_id = await _pay(repository, 20, "100", 1)

        connection = repository._connection()
        async with repository._lock:
            cursor = await connection.execute(
                "SELECT principal_minor FROM deposits WHERE id = ?",
                (deposit_id,),
            )
            principal_minor = int((await cursor.fetchone())["principal_minor"])
        expected_daily = calculate_bps(principal_minor, business.daily_profit_bps)

        for _day in range(1, 21):
            async with repository.transaction() as connection:
                await connection.execute(
                    "UPDATE deposits SET next_payout_at = ? WHERE id = ? AND status = 'active'",
                    (int(time.time()) - 1, deposit_id),
                )
            await repository.schedule_due_payouts()

        async with repository._lock:
            cursor = await connection.execute(
                "SELECT COALESCE(SUM(amount_minor),0) AS value FROM payouts "
                "WHERE source_deposit_id = ? AND kind = 'daily' AND subtype = ''",
                (deposit_id,),
            )
            profit = int((await cursor.fetchone())["value"])
            cursor = await connection.execute(
                "SELECT COALESCE(SUM(amount_minor),0) AS value FROM payouts "
                "WHERE source_deposit_id = ? AND subtype = 'principal'",
                (deposit_id,),
            )
            principal = int((await cursor.fetchone())["value"])
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM payouts WHERE source_deposit_id = ?",
                (deposit_id,),
            )
            count = int((await cursor.fetchone())["value"])

        assert profit == expected_daily * 20
        assert principal == principal_minor
        assert count == 21  # 20 daily + 1 principal
        assert profit + principal == expected_daily * 20 + principal_minor
    finally:
        await repository.close()
