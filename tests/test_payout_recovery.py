"""Payout worker: delegated-treasury serialization, dropped-tx recovery, gas bumps."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import aiosqlite
import pytest
from eth_account import Account
from hexbytes import HexBytes
from pydantic import SecretStr
from web3.exceptions import TransactionNotFound

from delta_backend.api_settings import MiniAppSettings
from delta_backend.models import SignedTransfer
from delta_backend.repository import DeltaRepository, parse_replaced_tx_hashes
from delta_backend.services import payouts as payouts_module
from delta_backend.services.blockchain import BlockchainRpcError, EvmTokenClient
from delta_backend.services.payouts import DailyPayoutService
from delta_backend.services.safety import PayoutCircuitBreaker, SafetyRuntime

ADDRESS = "0x" + "2" * 40
GWEI = 1_000_000_000


class FakeChain:
    """Scriptable stand-in for EvmTokenClient covering the payout worker surface."""

    def __init__(self, *, delegated: bool = False) -> None:
        self.delegated = delegated
        self.native = 10**18
        self.token = 10**24
        self.gas = GWEI // 20  # 0.05 gwei, as observed on BSC
        self.pending = 0
        self.latest = 0
        self.receipts: dict[str, bool] = {}
        self.known: set[str] = set()
        self.gas_prices: dict[str, int] = {}
        self.broadcast_errors: dict[str, Exception] = {}
        self.broadcast_error_default: Exception | None = None
        self.broadcasts: list[str] = []
        self.sign_calls: list[dict[str, object]] = []
        self.delegation_checks = 0
        self._raw_nonce: dict[str, int] = {}

    async def is_delegated(self) -> bool:
        self.delegation_checks += 1
        return self.delegated

    async def signer_balances(self) -> tuple[int, int]:
        return (self.native, self.token)

    async def gas_price(self) -> int:
        return self.gas

    async def pending_nonce(self) -> int:
        return self.pending

    async def latest_nonce(self) -> int:
        return self.latest

    def safe_error(self, exc: BaseException) -> str:
        return f"{type(exc).__name__}: {exc}"

    async def sign_token_transfer(
        self,
        address: str,
        amount_minor: int,
        *,
        gas_price: int | None = None,
        nonce: int | None = None,
    ) -> SignedTransfer:
        use_nonce = int(nonce) if nonce is not None else self.pending
        index = len(self.sign_calls)
        self.sign_calls.append(
            {"address": address, "amount_minor": amount_minor, "gas_price": gas_price, "nonce": use_nonce}
        )
        tx_hash = "0x" + f"{index:02x}".rjust(64, "f")
        raw = f"0xraw-{index}-nonce{use_nonce}-gas{gas_price}"
        self._raw_nonce[raw] = use_nonce
        return SignedTransfer(tx_hash=tx_hash, raw_transaction=raw, nonce=use_nonce)

    async def broadcast(self, raw_transaction: str) -> str:
        self.broadcasts.append(raw_transaction)
        error = self.broadcast_errors.get(raw_transaction, self.broadcast_error_default)
        if error is not None:
            raise error
        nonce = self._raw_nonce.get(raw_transaction)
        if nonce is not None:
            self.pending = max(self.pending, nonce + 1)
        return "0x" + "0" * 64

    async def receipt_status(self, tx_hash: str) -> bool | None:
        return self.receipts.get(tx_hash)

    async def transaction_exists(self, tx_hash: str) -> bool:
        return tx_hash in self.known

    async def transaction_gas_price(self, tx_hash: str) -> int | None:
        return self.gas_prices.get(tx_hash)


def worker_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "payouts_enabled": True,
        "simulate_payouts": False,
        "token_decimals": 18,
        "safety_min_native_balance_wei": 10**15,
        "payout_batch_size": 8,
        "safety_payout_stuck_seconds": 900,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def open_repository(tmp_path: Path, name: str) -> DeltaRepository:
    repo = DeltaRepository(tmp_path / f"{name}.sqlite3", MiniAppSettings())
    await repo.connect()
    now = int(time.time())
    async with repo.transaction() as tx:
        await tx.execute(
            "INSERT INTO users(telegram_id, first_name, created_at, last_seen_at) VALUES (?,?,?,?)",
            (1, "Payee", now, now),
        )
    return repo


async def insert_payout(
    repo: DeltaRepository,
    key: str,
    *,
    status: str = "queued",
    amount_minor: int = 1_000_000,
    nonce: int | None = None,
    tx_hash: str | None = None,
    raw_transaction: str | None = None,
    status_changed_at: int | None = None,
    replaced_tx_hashes: str | None = None,
) -> int:
    now = int(time.time())
    async with repo.transaction() as tx:
        cursor = await tx.execute(
            """
            INSERT INTO payouts(
                idempotency_key, user_id, kind, amount_minor, address, status, nonce,
                tx_hash, raw_transaction, created_at, updated_at, status_changed_at,
                replaced_tx_hashes
            ) VALUES (?, ?, 'daily', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                1,
                amount_minor,
                ADDRESS,
                status,
                nonce,
                tx_hash,
                raw_transaction,
                now,
                now,
                now if status_changed_at is None else status_changed_at,
                replaced_tx_hashes,
            ),
        )
        return int(cursor.lastrowid)


async def payout_row(repo: DeltaRepository, payout_id: int) -> dict[str, object]:
    connection = repo._connection()
    cursor = await connection.execute("SELECT * FROM payouts WHERE id = ?", (payout_id,))
    return dict(await cursor.fetchone())


def make_service(repo: DeltaRepository, chain: FakeChain, **overrides: object) -> DailyPayoutService:
    runtime = SafetyRuntime()
    circuit = PayoutCircuitBreaker(runtime)
    circuit.set_reasons([])
    service = DailyPayoutService(repo, worker_settings(**overrides), chain, circuit)
    # Scheduling of due deposits is exercised elsewhere; keep these tests on the queue.
    service._last_schedule_at = time.time()
    return service


# --- (A) delegated treasury: one in-flight transaction ------------------------------


@pytest.mark.asyncio
async def test_delegated_treasury_signs_one_payout_at_a_time(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "delegated")
    try:
        ids = [await insert_payout(repo, f"p{i}") for i in range(3)]
        chain = FakeChain(delegated=True)
        service = make_service(repo, chain)

        await service.run_once()
        statuses = [str((await payout_row(repo, pid))["status"]) for pid in ids]
        assert statuses == ["broadcast", "queued", "queued"]
        assert len(chain.sign_calls) == 1

        # Nothing new is signed while the single in-flight transaction is pending.
        await service.run_once()
        assert len(chain.sign_calls) == 1
        first = await payout_row(repo, ids[0])
        assert first["status"] == "broadcast"

        # Once it mines the slot frees up and exactly one more payout is signed.
        chain.receipts[str(first["tx_hash"])] = True
        chain.latest = 1
        await service.run_once()
        statuses = [str((await payout_row(repo, pid))["status"]) for pid in ids]
        assert statuses == ["confirmed", "broadcast", "queued"]
        assert len(chain.sign_calls) == 2
        assert [call["nonce"] for call in chain.sign_calls] == [0, 1]
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_non_delegated_treasury_keeps_batch_signing(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "batch")
    try:
        ids = [await insert_payout(repo, f"p{i}") for i in range(3)]
        chain = FakeChain(delegated=False)
        service = make_service(repo, chain)

        await service.run_once()
        statuses = [str((await payout_row(repo, pid))["status"]) for pid in ids]
        assert statuses == ["broadcast", "broadcast", "broadcast"]
        assert [call["nonce"] for call in chain.sign_calls] == [0, 1, 2]
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_delegation_check_failure_fails_safe_to_serialized_signing(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "delegation-error")
    try:
        ids = [await insert_payout(repo, f"p{i}") for i in range(2)]
        chain = FakeChain(delegated=False)

        async def broken_is_delegated() -> bool:
            raise BlockchainRpcError("eth_getCode failed on all HTTPS RPC endpoints")

        chain.is_delegated = broken_is_delegated  # type: ignore[method-assign]
        service = make_service(repo, chain)

        await service.run_once()
        statuses = [str((await payout_row(repo, pid))["status"]) for pid in ids]
        assert statuses == ["broadcast", "queued"]
    finally:
        await repo.close()


@pytest.mark.parametrize(
    "message",
    [
        "in-flight transaction limit reached for delegated accounts",
        "gapped-nonce tx from delegated accounts",
    ],
)
@pytest.mark.asyncio
async def test_delegated_txpool_rejections_keep_payout_signed(tmp_path: Path, message: str) -> None:
    repo = await open_repository(tmp_path, "txpool")
    try:
        raw = "0xsignedbytes"
        payout_id = await insert_payout(
            repo, "signed", status="signed", nonce=4, tx_hash="0x" + "a" * 64, raw_transaction=raw
        )
        chain = FakeChain(delegated=True)
        chain.broadcast_errors[raw] = BlockchainRpcError(f"-32000 {message}")
        service = make_service(repo, chain)

        for _ in range(3):
            await service.run_once()

        row = await payout_row(repo, payout_id)
        assert row["status"] == "signed"
        assert row["nonce"] == 4
        assert row["raw_transaction"] == raw
        assert message in str(row["last_error"])
        assert chain.broadcasts == [raw, raw, raw]
        assert chain.sign_calls == []
    finally:
        await repo.close()


# --- (B) dropped / stalled broadcasts ----------------------------------------------


@pytest.mark.asyncio
async def test_missing_receipt_rebroadcasts_same_bytes_without_resigning(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "rebroadcast")
    try:
        raw = "0xsamebytes"
        tx_hash = "0x" + "b" * 64
        payout_id = await insert_payout(
            repo,
            "bcast",
            status="broadcast",
            nonce=5,
            tx_hash=tx_hash,
            raw_transaction=raw,
            status_changed_at=int(time.time()) - 60,
        )
        chain = FakeChain()
        chain.latest = 5
        service = make_service(repo, chain)

        await service.run_once()
        assert chain.broadcasts == [raw]
        assert chain.sign_calls == []
        row = await payout_row(repo, payout_id)
        assert row["status"] == "broadcast"
        assert row["tx_hash"] == tx_hash

        chain.broadcast_errors[raw] = BlockchainRpcError("already known")
        await service.run_once()
        chain.broadcast_errors[raw] = BlockchainRpcError("nonce too low")
        await service.run_once()
        row = await payout_row(repo, payout_id)
        assert row["status"] == "broadcast"
        assert row["last_error"] is None
        assert chain.broadcasts == [raw, raw, raw]
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_fresh_broadcast_is_not_rebroadcast_before_grace(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "fresh")
    try:
        raw = "0xfreshbytes"
        payout_id = await insert_payout(
            repo, "bcast", status="broadcast", nonce=5, tx_hash="0x" + "b" * 64, raw_transaction=raw
        )
        chain = FakeChain()
        chain.latest = 5
        service = make_service(repo, chain)

        await service.run_once()
        assert chain.broadcasts == []
        assert (await payout_row(repo, payout_id))["status"] == "broadcast"
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_consumed_nonce_with_unknown_tx_fails_after_consecutive_passes(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "consumed")
    try:
        tx_hash = "0x" + "c" * 64
        payout_id = await insert_payout(
            repo, "bcast", status="broadcast", nonce=48, tx_hash=tx_hash, raw_transaction="0xraw"
        )
        chain = FakeChain()
        chain.latest = 49
        service = make_service(repo, chain)

        for _ in range(payouts_module.MISSING_TX_CONFIRMATIONS - 1):
            await service.run_once()
            assert (await payout_row(repo, payout_id))["status"] == "broadcast"

        await service.run_once()
        row = await payout_row(repo, payout_id)
        assert row["status"] == "failed"
        reason = str(row["last_error"])
        assert "nonce 48" in reason
        assert tx_hash in reason
        assert "BscScan" in reason
        assert chain.sign_calls == []

        assert await repo.retry_payout(payout_id) is True
        row = await payout_row(repo, payout_id)
        assert row["status"] == "queued"
        assert row["nonce"] is None and row["tx_hash"] is None
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_consumed_nonce_streak_resets_when_tx_reappears(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "streak")
    try:
        tx_hash = "0x" + "d" * 64
        payout_id = await insert_payout(
            repo, "bcast", status="broadcast", nonce=10, tx_hash=tx_hash, raw_transaction="0xraw"
        )
        chain = FakeChain()
        chain.latest = 11
        service = make_service(repo, chain)

        await service.run_once()
        await service.run_once()
        chain.known.add(tx_hash)  # a lagging node finally sees the mined transaction
        await service.run_once()
        chain.known.discard(tx_hash)
        await service.run_once()
        await service.run_once()
        assert (await payout_row(repo, payout_id))["status"] == "broadcast"

        await service.run_once()
        assert (await payout_row(repo, payout_id))["status"] == "failed"
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_known_transaction_is_never_failed_while_nonce_consumed(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "known")
    try:
        tx_hash = "0x" + "e" * 64
        payout_id = await insert_payout(
            repo, "bcast", status="broadcast", nonce=10, tx_hash=tx_hash, raw_transaction="0xraw"
        )
        chain = FakeChain()
        chain.latest = 11
        chain.known.add(tx_hash)
        service = make_service(repo, chain)

        for _ in range(payouts_module.MISSING_TX_CONFIRMATIONS + 2):
            await service.run_once()
        assert (await payout_row(repo, payout_id))["status"] == "broadcast"

        chain.receipts[tx_hash] = True
        await service.run_once()
        assert (await payout_row(repo, payout_id))["status"] == "confirmed"
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_pending_nonce_keeps_broadcast_row_waiting(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "waiting")
    try:
        payout_id = await insert_payout(
            repo, "bcast", status="broadcast", nonce=10, tx_hash="0x" + "1" * 64, raw_transaction="0xraw"
        )
        chain = FakeChain()
        chain.latest = 10  # nonce not consumed: the transaction can still mine
        service = make_service(repo, chain)

        for _ in range(payouts_module.MISSING_TX_CONFIRMATIONS + 2):
            await service.run_once()
        row = await payout_row(repo, payout_id)
        assert row["status"] == "broadcast"
        assert chain.sign_calls == []
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_recovery_rpc_error_keeps_row_and_tick_alive(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "rpc-error")
    try:
        payout_id = await insert_payout(
            repo, "bcast", status="broadcast", nonce=10, tx_hash="0x" + "2" * 64, raw_transaction="0xraw"
        )
        queued_id = await insert_payout(repo, "queued")
        chain = FakeChain()
        chain.latest = 11
        chain.pending = 11

        async def failing_exists(tx_hash: str) -> bool:
            raise BlockchainRpcError("eth_getTransactionByHash failed: primary: timeout")

        chain.transaction_exists = failing_exists  # type: ignore[method-assign]
        service = make_service(repo, chain)

        for _ in range(payouts_module.MISSING_TX_CONFIRMATIONS + 1):
            await service.run_once()
        assert (await payout_row(repo, payout_id))["status"] == "broadcast"
        # The queue kept moving: the tick was not aborted by the recovery error.
        assert (await payout_row(repo, queued_id))["status"] == "broadcast"
    finally:
        await repo.close()


# --- (C) duplicate-nonce guard before signing ----------------------------------------


@pytest.mark.asyncio
async def test_in_flight_nonce_not_seen_by_rpc_pauses_signing(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "nonce-guard")
    try:
        await insert_payout(
            repo, "bcast", status="broadcast", nonce=7, tx_hash="0x" + "3" * 64, raw_transaction="0xraw7"
        )
        queued_id = await insert_payout(repo, "queued")
        chain = FakeChain(delegated=False)
        chain.latest = 7
        chain.pending = 7  # the RPC pool does not hold our nonce-7 transaction
        service = make_service(repo, chain)

        await service.run_once()
        assert chain.sign_calls == []
        assert (await payout_row(repo, queued_id))["status"] == "queued"

        chain.pending = 8
        await service.run_once()
        assert [call["nonce"] for call in chain.sign_calls] == [8]
        assert (await payout_row(repo, queued_id))["status"] == "broadcast"
    finally:
        await repo.close()


# --- (D) same-nonce gas bump -----------------------------------------------------------


@pytest.mark.asyncio
async def test_stalled_transaction_is_replaced_with_same_nonce_and_higher_gas(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "bump")
    try:
        old_hash = "0x" + "4" * 64
        old_raw = "0xoldraw"
        entered = int(time.time()) - 600  # > safety_payout_stuck_seconds / 2
        payout_id = await insert_payout(
            repo,
            "bcast",
            status="broadcast",
            nonce=5,
            tx_hash=old_hash,
            raw_transaction=old_raw,
            status_changed_at=entered,
        )
        chain = FakeChain(delegated=True)
        chain.latest = 5
        chain.gas = GWEI // 20
        chain.gas_prices[old_hash] = GWEI // 20
        service = make_service(repo, chain)

        await service.run_once()
        assert len(chain.sign_calls) == 1
        call = chain.sign_calls[0]
        assert call["nonce"] == 5
        assert call["address"] == ADDRESS
        assert call["amount_minor"] == 1_000_000
        assert call["gas_price"] == max(chain.gas * 3 // 2, (GWEI // 20) * 9 // 8)
        row = await payout_row(repo, payout_id)
        assert row["status"] == "broadcast"
        assert row["nonce"] == 5
        assert row["tx_hash"] != old_hash
        assert row["raw_transaction"] != old_raw
        assert row["status_changed_at"] == entered
        history = parse_replaced_tx_hashes(row["replaced_tx_hashes"])
        assert [entry["tx_hash"] for entry in history] == [old_hash]
        assert chain.broadcasts[-1] == row["raw_transaction"]

        # No second replacement right away, and nothing else is signed while in flight.
        await insert_payout(repo, "queued")
        await service.run_once()
        assert len(chain.sign_calls) == 1

        # The original transaction mines after all: the payout is confirmed with its hash.
        chain.receipts[old_hash] = True
        chain.latest = 6
        await service.run_once()
        row = await payout_row(repo, payout_id)
        assert row["status"] == "confirmed"
        assert row["tx_hash"] == old_hash
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_gas_bump_uses_old_price_floor_when_network_price_is_low(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "bump-floor")
    try:
        old_hash = "0x" + "5" * 64
        await insert_payout(
            repo,
            "bcast",
            status="broadcast",
            nonce=5,
            tx_hash=old_hash,
            raw_transaction="0xoldraw",
            status_changed_at=int(time.time()) - 600,
        )
        chain = FakeChain()
        chain.latest = 5
        chain.gas = GWEI // 20
        chain.gas_prices[old_hash] = GWEI  # the stuck tx already paid far above market
        service = make_service(repo, chain)

        await service.run_once()
        assert chain.sign_calls[0]["gas_price"] == GWEI * 9 // 8
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_gas_bump_is_skipped_before_threshold_cap_or_when_tx_is_unseen(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "bump-skip")
    try:
        fresh_hash = "0x" + "6" * 64
        await insert_payout(
            repo, "fresh", status="broadcast", nonce=1, tx_hash=fresh_hash, raw_transaction="0xr1"
        )
        capped_hash = "0x" + "7" * 64
        old = int(time.time()) - 5000
        await insert_payout(
            repo,
            "capped",
            status="broadcast",
            nonce=1,
            tx_hash=capped_hash,
            raw_transaction="0xr2",
            status_changed_at=old,
            replaced_tx_hashes=json.dumps(
                [
                    {"tx_hash": "0x" + f"{i}" * 64, "replaced_at": old + i}
                    for i in range(payouts_module.GAS_BUMP_MAX_REPLACEMENTS)
                ]
            ),
        )
        unseen_hash = "0x" + "8" * 64
        await insert_payout(
            repo,
            "unseen",
            status="broadcast",
            nonce=1,
            tx_hash=unseen_hash,
            raw_transaction="0xr3",
            status_changed_at=old,
        )
        chain = FakeChain()
        chain.latest = 1
        chain.gas_prices[fresh_hash] = GWEI // 20
        chain.gas_prices[capped_hash] = GWEI // 20
        service = make_service(repo, chain)

        await service.run_once()
        assert chain.sign_calls == []
        # Stalled rows were still re-broadcast with their own bytes; the fresh one waits.
        assert set(chain.broadcasts) == {"0xr2", "0xr3"}
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_gas_bump_confirms_replacement_when_it_mines(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "bump-confirm")
    try:
        old_hash = "0x" + "9" * 64
        payout_id = await insert_payout(
            repo,
            "bcast",
            status="broadcast",
            nonce=5,
            tx_hash=old_hash,
            raw_transaction="0xoldraw",
            status_changed_at=int(time.time()) - 600,
        )
        chain = FakeChain()
        chain.latest = 5
        chain.gas_prices[old_hash] = GWEI // 20
        service = make_service(repo, chain)

        await service.run_once()
        row = await payout_row(repo, payout_id)
        new_hash = str(row["tx_hash"])
        assert new_hash != old_hash

        chain.receipts[new_hash] = True
        chain.latest = 6
        await service.run_once()
        row = await payout_row(repo, payout_id)
        assert row["status"] == "confirmed"
        assert row["tx_hash"] == new_hash
        assert row["raw_transaction"] is None
    finally:
        await repo.close()


# --- gas price floor -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signing_raises_network_gas_price_to_floor(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "gas-floor")
    try:
        await insert_payout(repo, "p0")
        chain = FakeChain()
        chain.gas = GWEI // 20  # BSC quote that stalled in mempools for 10+ minutes
        service = make_service(repo, chain, payout_gas_price_floor_wei=GWEI)

        await service.run_once()
        assert chain.sign_calls[0]["gas_price"] == GWEI
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_gas_price_floor_never_lowers_a_higher_network_price(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "gas-floor-high")
    try:
        await insert_payout(repo, "p0")
        chain = FakeChain()
        chain.gas = 3 * GWEI
        service = make_service(repo, chain, payout_gas_price_floor_wei=GWEI)

        await service.run_once()
        assert chain.sign_calls[0]["gas_price"] == 3 * GWEI
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_missing_floor_setting_keeps_network_price(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "gas-floor-absent")
    try:
        await insert_payout(repo, "p0")
        chain = FakeChain()
        chain.gas = GWEI // 20
        service = make_service(repo, chain)

        await service.run_once()
        assert chain.sign_calls[0]["gas_price"] == GWEI // 20
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_gas_bump_starts_from_floor_when_network_price_is_low(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "gas-floor-bump")
    try:
        old_hash = "0x" + "a" * 64
        await insert_payout(
            repo,
            "bcast",
            status="broadcast",
            nonce=5,
            tx_hash=old_hash,
            raw_transaction="0xoldraw",
            status_changed_at=int(time.time()) - 600,
        )
        chain = FakeChain()
        chain.latest = 5
        chain.gas = GWEI // 20
        chain.gas_prices[old_hash] = GWEI // 20  # legacy row signed before the floor existed
        service = make_service(repo, chain, payout_gas_price_floor_wei=GWEI)

        await service.run_once()
        # max(floor * 1.5, old * 1.125) — the floor, not the 0.05 gwei quote, drives the bump.
        assert chain.sign_calls[0]["gas_price"] == GWEI * 3 // 2
        assert chain.sign_calls[0]["nonce"] == 5
    finally:
        await repo.close()


# --- repository --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replace_payout_transaction_only_for_broadcast_rows(tmp_path: Path) -> None:
    repo = await open_repository(tmp_path, "replace")
    try:
        broadcast_id = await insert_payout(
            repo, "b", status="broadcast", nonce=3, tx_hash="0xold1", raw_transaction="0xraw1"
        )
        queued_id = await insert_payout(repo, "q")
        failed_id = await insert_payout(repo, "f", status="failed", nonce=2, tx_hash="0xf")

        assert await repo.replace_payout_transaction(broadcast_id, "0xnew1", "0xnewraw1") is True
        assert await repo.replace_payout_transaction(broadcast_id, "0xnew2", "0xnewraw2") is True
        assert await repo.replace_payout_transaction(queued_id, "0xn", "0xr") is False
        assert await repo.replace_payout_transaction(failed_id, "0xn", "0xr") is False
        assert await repo.replace_payout_transaction(999_999, "0xn", "0xr") is False

        row = await payout_row(repo, broadcast_id)
        assert row["status"] == "broadcast"
        assert row["nonce"] == 3
        assert row["tx_hash"] == "0xnew2"
        assert row["raw_transaction"] == "0xnewraw2"
        assert row["attempts"] == 2
        history = parse_replaced_tx_hashes(row["replaced_tx_hashes"])
        assert [entry["tx_hash"] for entry in history] == ["0xold1", "0xnew1"]
        assert all(entry["replaced_at"] > 0 for entry in history)

        await repo.mark_payout_failed(broadcast_id, "test")
        assert await repo.retry_payout(broadcast_id) is True
        row = await payout_row(repo, broadcast_id)
        assert row["status"] == "queued"
        assert row["replaced_tx_hashes"] is None
        assert row["tx_hash"] is None and row["raw_transaction"] is None and row["nonce"] is None
    finally:
        await repo.close()


def test_parse_replaced_tx_hashes_tolerates_garbage() -> None:
    assert parse_replaced_tx_hashes(None) == []
    assert parse_replaced_tx_hashes("") == []
    assert parse_replaced_tx_hashes("not json") == []
    assert parse_replaced_tx_hashes('{"tx_hash": "0x1"}') == []
    assert parse_replaced_tx_hashes('[{"tx_hash": "0x1"}, {"nope": 1}, 5]') == [
        {"tx_hash": "0x1", "replaced_at": 0}
    ]


@pytest.mark.asyncio
async def test_migration_adds_replaced_tx_hashes_to_legacy_payouts(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    async with aiosqlite.connect(path) as legacy:
        await legacy.execute(
            """
            CREATE TABLE payouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                source_deposit_id INTEGER,
                kind TEXT NOT NULL,
                subtype TEXT NOT NULL DEFAULT '',
                payout_day INTEGER,
                referral_level INTEGER,
                admin_test INTEGER NOT NULL DEFAULT 0,
                amount_minor INTEGER NOT NULL,
                address TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                tx_hash TEXT,
                raw_transaction TEXT,
                nonce INTEGER,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                status_changed_at INTEGER,
                confirmed_at INTEGER
            )
            """
        )
        await legacy.commit()

    repo = DeltaRepository(path, MiniAppSettings())
    await repo.connect()
    try:
        connection = repo._connection()
        cursor = await connection.execute("PRAGMA table_info(payouts)")
        columns = {str(row[1]) for row in await cursor.fetchall()}
        assert "replaced_tx_hashes" in columns
    finally:
        await repo.close()


# --- EvmTokenClient helpers ------------------------------------------------------------


class FakeEth:
    def __init__(
        self,
        *,
        code: bytes = b"",
        transactions: dict[str, dict[str, object]] | None = None,
        latest: int = 0,
        pending: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.code = code
        self.transactions = transactions or {}
        self.latest = latest
        self.pending = pending
        self.error = error
        self.calls: list[tuple[str, object]] = []

    async def get_code(self, address: str) -> HexBytes:
        self.calls.append(("eth_getCode", address))
        if self.error is not None:
            raise self.error
        return HexBytes(self.code)

    async def get_transaction(self, tx_hash: str) -> dict[str, object]:
        self.calls.append(("eth_getTransactionByHash", tx_hash))
        if self.error is not None:
            raise self.error
        if tx_hash not in self.transactions:
            raise TransactionNotFound(tx_hash)
        return self.transactions[tx_hash]

    async def get_transaction_count(self, address: str, block_identifier: str) -> int:
        self.calls.append(("eth_getTransactionCount", block_identifier))
        if self.error is not None:
            raise self.error
        return self.pending if block_identifier == "pending" else self.latest


def make_client(*eths: FakeEth, account_key: bytes | None = None) -> EvmTokenClient:
    key = account_key or Account.create().key
    account = Account.from_key(key)
    settings = SimpleNamespace(
        token_contract="0x55d398326f99059ff775485246999027b3197955",
        treasury_address=account.address,
        chain_id=56,
        token_decimals=18,
        bsc_rpc_url="https://rpc.example/primary",
        bsc_rpc_fallback_url="https://rpc.example/fallback",
        bsc_rpc_timeout_seconds=10,
        bsc_wss_url="wss://rpc.example",
        scan_block_chunk=1500,
        payout_seed_phrase=None,
        payout_private_key=SecretStr(HexBytes(key).hex()),
        payout_keystore_path=None,
        payout_keystore_password=None,
    )
    client = EvmTokenClient(settings)
    client._http_clients = [SimpleNamespace(eth=eth) for eth in eths]
    return client


@pytest.mark.asyncio
async def test_is_delegated_detects_eip7702_prefix_and_caches() -> None:
    delegate = bytes.fromhex("ef0100") + bytes.fromhex("11" * 20)
    eth = FakeEth(code=delegate)
    client = make_client(eth)

    assert await client.is_delegated() is True
    assert await client.is_delegated() is True
    assert eth.calls == [("eth_getCode", client.treasury_address)]

    plain = make_client(FakeEth(code=b""))
    assert await plain.is_delegated() is False
    contract_like = make_client(FakeEth(code=bytes.fromhex("6080604052")))
    assert await contract_like.is_delegated() is False


@pytest.mark.asyncio
async def test_is_delegated_uses_fallback_and_raises_when_all_fail() -> None:
    primary = FakeEth(error=RuntimeError("primary down"))
    fallback = FakeEth(code=bytes.fromhex("ef0100") + bytes.fromhex("22" * 20))
    client = make_client(primary, fallback)
    assert await client.is_delegated() is True

    broken = make_client(FakeEth(error=RuntimeError("down")), FakeEth(error=RuntimeError("down")))
    with pytest.raises(BlockchainRpcError):
        await broken.is_delegated()


@pytest.mark.asyncio
async def test_transaction_lookup_semantics_across_endpoints() -> None:
    tx = {"hash": "0xabc", "gasPrice": 75_000_000, "nonce": 5}
    found_on_fallback = make_client(FakeEth(), FakeEth(transactions={"0xabc": tx}))
    assert await found_on_fallback.transaction_exists("0xabc") is True
    assert await found_on_fallback.transaction_gas_price("0xabc") == 75_000_000

    nowhere = make_client(FakeEth(), FakeEth())
    assert await nowhere.transaction_exists("0xabc") is False
    assert await nowhere.transaction_gas_price("0xabc") is None

    # An endpoint error without a positive answer is not "dropped": it raises.
    flaky = make_client(FakeEth(error=RuntimeError("timeout")), FakeEth())
    with pytest.raises(BlockchainRpcError):
        await flaky.transaction_exists("0xabc")

    hex_price = make_client(FakeEth(transactions={"0xabc": {"gasPrice": "0x47868c0"}}))
    assert await hex_price.transaction_gas_price("0xabc") == 75_000_000


@pytest.mark.asyncio
async def test_latest_and_pending_nonce_use_block_identifiers() -> None:
    eth = FakeEth(latest=48, pending=49)
    client = make_client(eth)
    assert await client.latest_nonce() == 48
    assert await client.pending_nonce() == 49
    assert eth.calls == [
        ("eth_getTransactionCount", "latest"),
        ("eth_getTransactionCount", "pending"),
    ]


class FakeTransferFunction:
    def __init__(self, sender: str, token: str) -> None:
        self.sender = sender
        self.token = token

    async def estimate_gas(self, params: dict[str, object]) -> int:
        assert params == {"from": self.sender}
        return 50_000

    async def build_transaction(self, params: dict[str, object]) -> dict[str, object]:
        return {**params, "to": self.token, "value": 0, "data": "0xa9059cbb"}


class FakeSigningEth(FakeEth):
    def __init__(self, sender: str, token: str, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.sender = sender
        self.token = token

    def contract(self, *, address: str, abi: object) -> SimpleNamespace:
        function = FakeTransferFunction(self.sender, address)
        return SimpleNamespace(
            functions=SimpleNamespace(transfer=lambda _to, _value: function)
        )

    @property
    def gas_price(self) -> object:
        # Mirrors web3's awaitable ``eth.gas_price`` property.
        async def value() -> int:
            return 1

        return value()


@pytest.mark.asyncio
async def test_sign_token_transfer_honours_explicit_nonce_for_replacement() -> None:
    key = Account.create().key
    sender = Account.from_key(key).address
    eth = FakeSigningEth(sender, "0x55d398326f99059ff775485246999027b3197955", pending=12)
    client = make_client(eth, account_key=key)

    default = await client.sign_token_transfer(ADDRESS, 1_000_000, gas_price=50_000_000)
    assert default.nonce == 12
    assert ("eth_getTransactionCount", "pending") in eth.calls

    eth.calls.clear()
    replacement = await client.sign_token_transfer(
        ADDRESS, 1_000_000, gas_price=75_000_000, nonce=5
    )
    assert replacement.nonce == 5
    assert ("eth_getTransactionCount", "pending") not in eth.calls
    assert replacement.tx_hash != default.tx_hash
    assert replacement.raw_transaction.startswith("0x")
