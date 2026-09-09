import time

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.deposit_mismatch import select_mismatch_candidate
from delta_backend.repository import DeltaRepository

WALLET = "0x0000000000000000000000000000000000000002"
TX_HASH = "0x" + "b" * 64


def test_select_by_base_minor():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 1, "amount_minor": 100_000000, "created_at": 1010, "tx_hash": "0xa", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 1


def test_select_within_one_usdt_of_exact():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 2, "amount_minor": 100_370000 - 50, "created_at": 1010, "tx_hash": "0xb", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 2


def test_reject_outside_window_and_tolerance():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    far = {"id": 3, "amount_minor": 50_000000, "created_at": 1010, "tx_hash": "0xc", "matched": 0}
    early = {"id": 4, "amount_minor": 100_000000, "created_at": 100, "tx_hash": "0xd", "matched": 0}
    assert select_mismatch_candidate(invoice, [far, early]) is None


def test_prefer_closest_created_at_then_smaller_delta():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 5, "amount_minor": 100_000000, "created_at": 1500, "tx_hash": "0xe", "matched": 0},
        {"id": 6, "amount_minor": 100_000000, "created_at": 1050, "tx_hash": "0xf", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 6


async def test_get_user_invoice_mismatch_hint(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "mismatch.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(1, "u1", "One", "ru")
        await repo.set_wallet(1, WALLET)
        base_minor = usdt_to_minor(10)
        inv = await repo.create_invoice(1, base_minor, idempotency_key="mismatch-hint-1")
        invoice_id = int(inv["invoice_id"])
        now = int(time.time())
        connection = repo._connection()
        async with repo._lock:
            await connection.execute(
                """
                INSERT INTO chain_deposits(
                    chain_id, tx_hash, log_index, block_number, from_address,
                    to_address, amount_atomic, amount_minor, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    97,
                    TX_HASH,
                    0,
                    1,
                    WALLET,
                    "0x0000000000000000000000000000000000000001",
                    str(base_minor * 10**12),
                    base_minor,
                    now,
                ),
            )
            await connection.commit()

        row = await repo.get_user_invoice(1, invoice_id)
        assert row is not None
        assert row["mismatch_hint"] is True
        assert row["mismatch"] is not None
        assert row["mismatch"]["tx_hash"] == TX_HASH
        assert row["credited"] is False
    finally:
        await repo.close()
