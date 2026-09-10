import time

import pytest

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.deposit_mismatch import (
    select_mismatch_candidate,
    select_pending_invoice_for_unmatched_deposit,
)
from delta_backend.models import TransferEvent
from delta_backend.repository import DeltaRepository

WALLET = "0x0000000000000000000000000000000000000002"
TX_HASH = "0x" + "b" * 64


def test_select_by_base_minor():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 1, "amount_minor": 100_000000, "created_at": 1010, "tx_hash": "0xa", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 1


@pytest.mark.parametrize("direction", [-1, 1])
def test_select_within_half_usdt_of_exact(direction):
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {
            "id": 2,
            "amount_minor": 100_370000 + direction * usdt_to_minor("0.50"),
            "created_at": 1010,
            "tx_hash": "0xb",
            "matched": 0,
        },
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 2


@pytest.mark.parametrize("direction", [-1, 1])
def test_reject_more_than_one_usdt_from_exact(direction):
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {
            "id": 3,
            "amount_minor": 100_370000 + direction * usdt_to_minor("1.01"),
            "created_at": 1010,
            "tx_hash": "0xc",
            "matched": 0,
        },
    ]
    assert select_mismatch_candidate(invoice, candidates) is None


def test_reject_outside_window_and_tolerance():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    far = {"id": 4, "amount_minor": 50_000000, "created_at": 1010, "tx_hash": "0xd", "matched": 0}
    early = {"id": 5, "amount_minor": 100_000000, "created_at": 100, "tx_hash": "0xe", "matched": 0}
    assert select_mismatch_candidate(invoice, [far, early]) is None


def test_prefer_closest_created_at_then_smaller_delta():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 5, "amount_minor": 100_000000, "created_at": 1500, "tx_hash": "0xe", "matched": 0},
        {"id": 6, "amount_minor": 100_000000, "created_at": 1050, "tx_hash": "0xf", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 6


def test_reverse_select_picks_near_miss_pending_invoice():
    deposit = {
        "id": 9,
        "amount_minor": 100_370000 + usdt_to_minor("1"),
        "created_at": 1010,
        "matched": 0,
    }
    invoices = [
        {
            "id": 1,
            "user_id": 10,
            "created_at": 1000,
            "expires_at": 5000,
            "base_minor": 100_000000,
            "exact_minor": 100_370000,
        },
        {
            "id": 2,
            "user_id": 11,
            "created_at": 1000,
            "expires_at": 5000,
            "base_minor": 50_000000,
            "exact_minor": 50_120000,
        },
    ]
    chosen = select_pending_invoice_for_unmatched_deposit(invoices, deposit)
    assert chosen is not None
    assert chosen["id"] == 1


def test_reverse_select_none_when_far_or_matched():
    deposit = {"id": 9, "amount_minor": 10_000000, "created_at": 1010, "matched": 0}
    invoices = [
        {
            "id": 1,
            "user_id": 10,
            "created_at": 1000,
            "expires_at": 5000,
            "base_minor": 100_000000,
            "exact_minor": 100_370000,
        },
    ]
    assert select_pending_invoice_for_unmatched_deposit(invoices, deposit) is None
    matched = {"id": 9, "amount_minor": 100_370000, "created_at": 1010, "matched": 1}
    assert select_pending_invoice_for_unmatched_deposit(invoices, matched) is None


def test_reverse_select_prefers_closer_invoice_time():
    deposit = {"id": 9, "amount_minor": 100_000000, "created_at": 1100, "matched": 0}
    invoices = [
        {
            "id": 1,
            "user_id": 10,
            "created_at": 1000,
            "expires_at": 5000,
            "base_minor": 100_000000,
            "exact_minor": 100_370000,
        },
        {
            "id": 2,
            "user_id": 11,
            "created_at": 1080,
            "expires_at": 5000,
            "base_minor": 100_000000,
            "exact_minor": 100_370000,
        },
    ]
    assert select_pending_invoice_for_unmatched_deposit(invoices, deposit)["id"] == 2


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


@pytest.mark.asyncio
async def test_apply_transfer_queues_near_miss_telegram_once(tmp_path) -> None:
    repo = DeltaRepository(
        tmp_path / "near-miss-dm.sqlite3", MiniAppSettings(_env_file=None)
    )
    await repo.connect()
    try:
        await repo.ensure_user(1, "u1", "One", "ru")
        await repo.set_wallet(1, WALLET)
        base_minor = usdt_to_minor(10)
        inv = await repo.create_invoice(1, base_minor, idempotency_key="near-miss-dm-1")
        invoice_id = int(inv["invoice_id"])
        exact_minor = int(inv["exact_minor"])
        near_minor = exact_minor + usdt_to_minor("1")
        transfer = TransferEvent(
            chain_id=97,
            tx_hash=TX_HASH,
            log_index=0,
            block_number=42,
            from_address=WALLET,
            to_address="0x0000000000000000000000000000000000000001",
            amount_atomic=near_minor * 10**12,
            amount_minor=near_minor,
        )
        result = await repo.apply_transfer(transfer)
        assert result == {"duplicate": False, "matched": False}

        connection = repo._connection()
        async with repo._lock:
            cursor = await connection.execute(
                "SELECT event_type, dedupe_key, user_id, title FROM user_notifications"
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        assert len(rows) == 1
        assert rows[0]["event_type"] == "deposit_amount_mismatch"
        assert rows[0]["user_id"] == 1
        assert rows[0]["title"] == "Сумма перевода не совпала"
        assert rows[0]["dedupe_key"] == f"deposit-mismatch:{invoice_id}:1"

        duplicate = await repo.apply_transfer(transfer)
        assert duplicate == {"duplicate": True, "matched": False}
        async with repo._lock:
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM user_notifications"
            )
            count = int((await cursor.fetchone())["value"])
        assert count == 1

        far = TransferEvent(
            chain_id=97,
            tx_hash="0x" + "c" * 64,
            log_index=1,
            block_number=43,
            from_address=WALLET,
            to_address="0x0000000000000000000000000000000000000001",
            amount_atomic=usdt_to_minor("50") * 10**12,
            amount_minor=usdt_to_minor("50"),
        )
        far_result = await repo.apply_transfer(far)
        assert far_result == {"duplicate": False, "matched": False}
        async with repo._lock:
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM user_notifications "
                "WHERE event_type = 'deposit_amount_mismatch'"
            )
            mismatch_count = int((await cursor.fetchone())["value"])
        assert mismatch_count == 1
    finally:
        await repo.close()
