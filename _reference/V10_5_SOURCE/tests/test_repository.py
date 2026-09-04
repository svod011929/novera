import time

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.models import TransferEvent
from delta_backend.repository import DeltaRepository


WALLET_ONE = "0x0000000000000000000000000000000000000001"
WALLET_TWO = "0x0000000000000000000000000000000000000002"


async def pay_invoice(repository: DeltaRepository, user_id: int, amount: str, log_index: int) -> int:
    invoice = await repository.create_invoice(user_id, usdt_to_minor(amount))
    exact = int(invoice["exact_minor"])
    result = await repository.apply_transfer(
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
    assert result["matched"] is True
    return int(result["deposit_id"])


async def test_deposit_and_referral_payouts_are_idempotent(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "delta.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(1, "leader", "Leader", "ru")
        await repository.set_wallet(1, WALLET_ONE)
        await repository.ensure_user(2, "partner", "Partner", "ru", referrer_id=1)
        await repository.set_wallet(2, WALLET_TWO)

        await pay_invoice(repository, 1, "50", 1)
        referred_deposit = await pay_invoice(repository, 2, "100", 2)

        async with repository.transaction() as connection:
            await connection.execute(
                "UPDATE deposits SET next_payout_at = ?",
                (int(time.time()) - 1,),
            )

        scheduled = await repository.schedule_due_payouts()
        assert scheduled == 2

        connection = repository._connection()
        async with repository._lock:
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM payouts WHERE kind = 'referral' "
                "AND source_deposit_id = ?",
                (referred_deposit,),
            )
            assert int((await cursor.fetchone())["value"]) == 1

        assert await repository.schedule_due_payouts() == 0
    finally:
        await repository.close()


async def test_invoice_idempotency_and_pending_limit(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "delta.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(10, "member", "Member", "ru")
        await repository.set_wallet(10, WALLET_ONE)

        first = await repository.create_invoice(
            10,
            usdt_to_minor("100"),
            "invoice-test-0001",
        )
        repeated = await repository.create_invoice(
            10,
            usdt_to_minor("100"),
            "invoice-test-0001",
        )
        assert repeated["invoice_id"] == first["invoice_id"]
        assert repeated["exact_minor"] == first["exact_minor"]
        assert repeated["reused"] is True
    finally:
        await repository.close()


async def test_blocking_and_broadcast_queue(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "delta.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(20, "admin", "Admin", "ru")
        await repository.ensure_user(21, "active", "Active", "ru")
        await repository.ensure_user(22, "blocked", "Blocked", "ru")
        assert await repository.set_user_blocked(22, True) is True

        broadcast = await repository.create_broadcast(20, "Test message", "all")
        assert broadcast["total_count"] == 2

        first = await repository.claim_next_broadcast_delivery()
        assert first is not None
        await repository.finish_broadcast_delivery(int(first["id"]), delivered=True)
        second = await repository.claim_next_broadcast_delivery()
        assert second is not None
        await repository.finish_broadcast_delivery(int(second["id"]), delivered=True)
        assert await repository.claim_next_broadcast_delivery() is None

        rows = await repository.admin_broadcasts()
        assert rows[0]["status"] == "completed"
        assert rows[0]["delivered_count"] == 2
    finally:
        await repository.close()
