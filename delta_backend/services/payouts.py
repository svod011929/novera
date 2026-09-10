import logging
import time
import uuid

from ..amounts import minor_to_atomic

from ..config import Settings
from ..repository import DeltaRepository, parse_replaced_tx_hashes
from .blockchain import EvmTokenClient
from .safety import PayoutCircuitBreaker


logger = logging.getLogger(__name__)

# eth_sendRawTransaction answers that mean "this exact transaction is already in the
# pool or mined": the same bytes reached the network, so the row may move to broadcast.
ALREADY_KNOWN_MARKERS = ("already known", "known transaction", "nonce too low")
# BSC txpool rules for EIP-7702 delegated senders (one in-flight transaction, no nonce
# gaps). Both clear on their own once the in-flight transaction mines, so a signed
# payout hitting them must be kept and retried, never failed.
DELEGATED_TXPOOL_MARKERS = ("in-flight transaction limit reached", "gapped-nonce")
DETERMINISTIC_BROADCAST_MARKERS = (
    "invalid sender",
    "intrinsic gas too low",
    "transaction type not supported",
)
# A healthy BSC transfer gets its receipt within a tick or two. Only a row without a
# receipt for this long is re-sent (same bytes, same nonce) to every RPC endpoint.
REBROADCAST_AFTER_SECONDS = 15.0
# A broadcast row whose nonce was consumed while its hash is unknown to every RPC is
# failed only after this many consecutive reconcile passes agree. Load-balanced RPC
# pools can lag a block behind each other; one stale answer must never turn a mined
# payout into an admin retry (double payment).
MISSING_TX_CONFIRMATIONS = 3
# Same-nonce gas bumps for a stalled broadcast are bounded: each one is a new
# signature for the same transfer, and fees on BSC make more than a few pointless.
GAS_BUMP_MAX_REPLACEMENTS = 3


class DailyPayoutService:
    def __init__(
        self,
        repository: DeltaRepository,
        settings: Settings,
        chain: EvmTokenClient | None,
        circuit: PayoutCircuitBreaker | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.chain = chain
        self.circuit = circuit
        self._last_schedule_at = 0.0
        self._missing_streak: dict[int, int] = {}
        self._last_gas_bump_attempt_at: dict[int, float] = {}

    def _batch_size(self) -> int:
        return max(1, min(int(getattr(self.settings, "payout_batch_size", 8)), 32))

    def _gas_bump_interval(self) -> float:
        stuck_seconds = int(getattr(self.settings, "safety_payout_stuck_seconds", 900))
        return max(30.0, stuck_seconds / 2)

    def _forget(self, payout_id: int) -> None:
        self._missing_streak.pop(payout_id, None)
        self._last_gas_bump_attempt_at.pop(payout_id, None)

    @staticmethod
    def _entered_broadcast_at(payout: dict[str, object]) -> float:
        return float(payout.get("status_changed_at") or payout.get("updated_at") or 0)

    async def run_once(self) -> None:
        if not self.settings.payouts_enabled:
            return
        # Due-schedule is SQLite-heavy; run at most once per 15s while still
        # reconciling/signing every payout tick for the ≤15s confirmation target.
        now = time.time()
        if (now - self._last_schedule_at) >= 15.0:
            await self.repository.schedule_due_payouts()
            self._last_schedule_at = now
        open_rows = await self.repository.list_open_payouts(limit=self._batch_size() * 3)
        if not open_rows:
            return

        if self.settings.simulate_payouts:
            for payout in open_rows[: self._batch_size()]:
                await self.repository.mark_payout_confirmed(
                    int(payout["id"]),
                    f"demo:{uuid.uuid4().hex}",
                )
            return
        if self.chain is None:
            return

        # 1) Reconcile every in-flight broadcast without blocking the queue.
        broadcast_rows = [p for p in open_rows if str(p["status"]) == "broadcast"]
        for payout in broadcast_rows[: self._batch_size()]:
            await self._reconcile_broadcast(payout)

        # Refresh after reconciliation so newly freed slots can be signed.
        open_rows = await self.repository.list_open_payouts(limit=self._batch_size() * 3)

        # 2) Finish already-signed transactions (same nonce/bytes — never re-sign).
        signed_rows = [p for p in open_rows if str(p["status"]) == "signed"]
        for payout in signed_rows[: self._batch_size()]:
            await self._broadcast(int(payout["id"]), str(payout["raw_transaction"]))

        open_rows = await self.repository.list_open_payouts(limit=self._batch_size() * 3)
        queued = [p for p in open_rows if str(p["status"]) == "queued"]
        if not queued:
            return
        if self.circuit is not None and self.circuit.is_open:
            return
        in_flight = [p for p in open_rows if str(p["status"]) in {"signed", "broadcast"}]
        room = max(0, await self._signing_capacity() - len(in_flight))
        if room <= 0:
            return
        queued = queued[:room]

        # Shared preflight once per batch instead of 2 balance + gas calls per payout.
        try:
            native_balance, token_balance = await self.chain.signer_balances()
            gas_price = await self.chain.gas_price()
            pending_nonce = await self.chain.pending_nonce() if in_flight else None
        except Exception as exc:
            if self.circuit is not None:
                self.circuit.add_reason("RPC_UNAVAILABLE")
            safe = self.chain.safe_error(exc)
            logger.error("Payout batch preflight failed: error=%s", safe)
            return
        if pending_nonce is not None and self._in_flight_nonce_conflict(in_flight, pending_nonce):
            return

        required_native = max(
            int(self.settings.safety_min_native_balance_wei),
            int(gas_price) * 120_000,
        )
        if int(native_balance) < required_native:
            if self.circuit is not None:
                self.circuit.add_reason("LOW_BNB")
            logger.error("Payout batch held by safety guard: reason=LOW_BNB")
            return

        remaining_token = int(token_balance)
        for payout in queued:
            payout_id = int(payout["id"])
            required_token = minor_to_atomic(
                int(payout["amount_minor"]),
                int(self.settings.token_decimals),
            )
            if remaining_token < required_token:
                if self.circuit is not None:
                    self.circuit.add_reason("LOW_USDT")
                logger.error(
                    "Payout held by safety guard: payout=%s reason=LOW_USDT",
                    payout_id,
                )
                # Keep later smaller payouts from starving: continue scanning the batch.
                continue
            try:
                signed = await self.chain.sign_token_transfer(
                    str(payout["address"]),
                    int(payout["amount_minor"]),
                    gas_price=int(gas_price),
                )
                await self.repository.mark_payout_signed(
                    payout_id,
                    signed.tx_hash,
                    signed.raw_transaction,
                    signed.nonce,
                )
                remaining_token -= required_token
                await self._broadcast(payout_id, signed.raw_transaction)
            except Exception as exc:
                safe = self.chain.safe_error(exc)
                await self.repository.mark_payout_failed(payout_id, safe)
                logger.error("Payout signing failed: payout=%s error=%s", payout_id, safe)

    async def _signing_capacity(self) -> int:
        """How many payouts may be signed+broadcast at once.

        BSC txpool admits a single in-flight transaction from an EIP-7702 delegated
        account and rejects gapped nonces, so a delegated treasury is serialized: no
        new signature while any signed/broadcast row exists. Non-delegated treasuries
        keep the configured batch. An unanswered delegation check fails safe to 1.
        """
        if self.chain is None:
            return 0
        try:
            delegated = await self.chain.is_delegated()
        except Exception as exc:
            logger.warning(
                "Treasury delegation check failed; signing serialized this tick: error=%s",
                self.chain.safe_error(exc),
            )
            return 1
        return 1 if delegated else self._batch_size()

    def _in_flight_nonce_conflict(
        self,
        in_flight: list[dict[str, object]],
        pending_nonce: int,
    ) -> bool:
        """Refuse to sign while the RPC pending nonce does not cover every in-flight row.

        sign_token_transfer takes eth_getTransactionCount(pending) from the RPC. If a
        signed/broadcast row already holds that nonce (its bytes were dropped by the
        pool, the pool lags, or the row came back through retry_payout while an
        older transaction was still alive), signing now would create a second
        transfer with a duplicate nonce. Delegated treasuries never reach this check
        with anything in flight (see _signing_capacity), so duplicates are
        structurally impossible there; for batch treasuries the pause makes the
        reconcile path (rebroadcast / consumed-nonce failure) resolve the conflict
        first.
        """
        nonces = [int(p["nonce"]) for p in in_flight if p.get("nonce") is not None]
        if not nonces:
            return False
        highest = max(nonces)
        if highest < int(pending_nonce):
            return False
        logger.warning(
            "Payout signing paused: in-flight nonce %s is not below RPC pending nonce %s; "
            "signing now would reuse a nonce",
            highest,
            pending_nonce,
        )
        return True

    async def _reconcile_broadcast(self, payout: dict[str, object]) -> None:
        if self.chain is None:
            return
        payout_id = int(payout["id"])
        tx_hash = str(payout["tx_hash"])
        receipt = await self.chain.receipt_status(tx_hash)
        if receipt is None:
            # A same-nonce predecessor (gas bump) may be the one the network mined.
            for entry in parse_replaced_tx_hashes(payout.get("replaced_tx_hashes")):
                previous_hash = str(entry["tx_hash"])
                receipt = await self.chain.receipt_status(previous_hash)
                if receipt is not None:
                    tx_hash = previous_hash
                    break
        if receipt is None:
            await self._recover_missing_receipt(payout)
            return
        self._forget(payout_id)
        if receipt is False:
            await self.repository.mark_payout_failed(
                payout_id,
                "transaction receipt status is 0",
            )
            return
        await self.repository.mark_payout_confirmed(payout_id, tx_hash)

    async def _recover_missing_receipt(self, payout: dict[str, object]) -> None:
        """Handle a broadcast payout that no endpoint has a receipt for.

        The nonce is read *before* the transaction lookup: a transaction that mines
        between the two calls is then still seen as present, so a payout is never
        failed while its own bytes could still confirm. Any RPC error only skips
        this tick; the row keeps its status.
        """
        if self.chain is None:
            return
        payout_id = int(payout["id"])
        tx_hash = str(payout["tx_hash"])
        raw_transaction = payout.get("raw_transaction")
        nonce = payout.get("nonce")
        stalled = (time.time() - self._entered_broadcast_at(payout)) >= REBROADCAST_AFTER_SECONDS
        try:
            if raw_transaction and stalled:
                await self._rebroadcast(payout_id, tx_hash, str(raw_transaction))
            if nonce is None:
                return
            latest_nonce = await self.chain.latest_nonce()
            if latest_nonce > int(nonce):
                await self._handle_consumed_nonce(payout, latest_nonce)
                return
            self._missing_streak.pop(payout_id, None)
            if latest_nonce == int(nonce):
                await self._maybe_bump_gas(payout)
        except Exception as exc:
            logger.warning(
                "Payout recovery skipped this tick: payout=%s error=%s",
                payout_id,
                self.chain.safe_error(exc),
            )

    async def _rebroadcast(self, payout_id: int, tx_hash: str, raw_transaction: str) -> None:
        """Re-send the stored signed bytes (same nonce) so a pool that dropped them recovers."""
        if self.chain is None:
            return
        try:
            await self.chain.broadcast(raw_transaction)
        except Exception as exc:
            safe = self.chain.safe_error(exc)
            lowered = safe.lower()
            if any(marker in lowered for marker in ALREADY_KNOWN_MARKERS):
                return
            logger.warning(
                "Payout rebroadcast rejected: payout=%s tx=%s error=%s",
                payout_id,
                tx_hash,
                safe,
            )
            return
        logger.info("Payout re-broadcast to RPC: payout=%s tx=%s", payout_id, tx_hash)

    async def _handle_consumed_nonce(self, payout: dict[str, object], latest_nonce: int) -> None:
        if self.chain is None:
            return
        payout_id = int(payout["id"])
        tx_hash = str(payout["tx_hash"])
        nonce = int(payout["nonce"])
        # eth_getTransactionByHash covers pending pools and mined blocks; the receipt
        # of a just-mined transaction can lag one pass behind on a load-balanced RPC.
        known_hashes = [tx_hash] + [
            str(entry["tx_hash"])
            for entry in parse_replaced_tx_hashes(payout.get("replaced_tx_hashes"))
        ]
        for candidate in known_hashes:
            if await self.chain.transaction_exists(candidate):
                self._missing_streak.pop(payout_id, None)
                return
        streak = self._missing_streak.get(payout_id, 0) + 1
        self._missing_streak[payout_id] = streak
        if streak < MISSING_TX_CONFIRMATIONS:
            logger.warning(
                "Payout transaction missing after nonce was consumed: payout=%s nonce=%s "
                "latest_nonce=%s tx=%s pass=%s/%s",
                payout_id,
                nonce,
                latest_nonce,
                tx_hash,
                streak,
                MISSING_TX_CONFIRMATIONS,
            )
            return
        self._forget(payout_id)
        reason = (
            f"nonce {nonce} consumed by another transaction (latest nonce {latest_nonce}); "
            f"tx {tx_hash} unknown to all RPC endpoints, transfer did not execute. "
            f"Check treasury nonce {nonce} on BscScan before retry."
        )
        await self.repository.mark_payout_failed(payout_id, reason)
        logger.error(
            "Payout failed after its transaction was dropped: payout=%s nonce=%s tx=%s",
            payout_id,
            nonce,
            tx_hash,
        )

    async def _maybe_bump_gas(self, payout: dict[str, object]) -> None:
        """Replace a stalled pending transaction with the same nonce at a higher gas price.

        Preconditions checked by the caller: no receipt anywhere and the on-chain
        nonce equals the payout nonce (still pending). The row is updated before the
        replacement is sent so a crash in between can only leave a recorded-but-unsent
        replacement, which the next pass simply rebroadcasts.
        """
        if self.chain is None:
            return
        payout_id = int(payout["id"])
        tx_hash = str(payout["tx_hash"])
        nonce = int(payout["nonce"])
        history = parse_replaced_tx_hashes(payout.get("replaced_tx_hashes"))
        if len(history) >= GAS_BUMP_MAX_REPLACEMENTS:
            return
        now = time.time()
        interval = self._gas_bump_interval()
        anchors = [
            self._entered_broadcast_at(payout),
            self._last_gas_bump_attempt_at.get(payout_id, 0.0),
        ]
        anchors.extend(float(entry["replaced_at"]) for entry in history)
        if now - max(anchors) < interval:
            return
        self._last_gas_bump_attempt_at[payout_id] = now

        old_gas_price = await self.chain.transaction_gas_price(tx_hash)
        if old_gas_price is None:
            # Not in any pool right now: the rebroadcast above re-seeds it; bump only a
            # transaction the network can actually see and replace.
            return
        current_gas_price = await self.chain.gas_price()
        new_gas_price = max(int(current_gas_price) * 3 // 2, int(old_gas_price) * 9 // 8)
        signed = await self.chain.sign_token_transfer(
            str(payout["address"]),
            int(payout["amount_minor"]),
            gas_price=new_gas_price,
            nonce=nonce,
        )
        if int(signed.nonce) != nonce:
            raise RuntimeError(
                f"replacement nonce mismatch: expected {nonce}, signed {signed.nonce}"
            )
        replaced = await self.repository.replace_payout_transaction(
            payout_id,
            signed.tx_hash,
            signed.raw_transaction,
        )
        if not replaced:
            return
        logger.warning(
            "Payout gas bump: payout=%s nonce=%s old_tx=%s new_tx=%s gas_price %s -> %s",
            payout_id,
            nonce,
            tx_hash,
            signed.tx_hash,
            old_gas_price,
            new_gas_price,
        )
        await self._rebroadcast(payout_id, signed.tx_hash, signed.raw_transaction)

    async def _broadcast(self, payout_id: int, raw_transaction: str) -> None:
        if self.chain is None:
            return
        try:
            await self.chain.broadcast(raw_transaction)
        except Exception as exc:
            safe = self.chain.safe_error(exc)
            lowered = safe.lower()
            if any(marker in lowered for marker in ALREADY_KNOWN_MARKERS):
                await self.repository.mark_payout_broadcast(payout_id)
                return
            if any(marker in lowered for marker in DELEGATED_TXPOOL_MARKERS):
                # Delegated treasury: the pool admits one transaction at a time. Keep the
                # signed bytes and nonce; the next tick retries once the in-flight
                # transaction has mined.
                await self.repository.record_payout_error(payout_id, safe)
                return
            if "insufficient funds" in lowered:
                if self.circuit is not None:
                    self.circuit.add_reason("LOW_BNB")
                await self.repository.record_payout_error(payout_id, safe)
                return
            deterministic = any(marker in lowered for marker in DETERMINISTIC_BROADCAST_MARKERS)
            if deterministic:
                await self.repository.mark_payout_failed(payout_id, safe)
            else:
                # A timeout can happen after the node accepted the transaction.
                # Keep the same signed bytes and nonce; never create another transfer.
                await self.repository.record_payout_error(payout_id, safe)
            return
        await self.repository.mark_payout_broadcast(payout_id)
