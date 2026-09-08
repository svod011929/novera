import logging
import time
import uuid

from ..amounts import minor_to_atomic

from ..config import Settings
from ..repository import DeltaRepository
from .blockchain import EvmTokenClient
from .safety import PayoutCircuitBreaker


logger = logging.getLogger(__name__)


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

    def _batch_size(self) -> int:
        return max(1, min(int(getattr(self.settings, "payout_batch_size", 8)), 32))

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
        in_flight = sum(1 for p in open_rows if str(p["status"]) in {"signed", "broadcast"})
        room = max(0, self._batch_size() - in_flight)
        if room <= 0:
            return
        if self.circuit is not None and self.circuit.is_open:
            return

        queued = [p for p in open_rows if str(p["status"]) == "queued"][:room]
        if not queued:
            return

        # Shared preflight once per batch instead of 2 balance + gas calls per payout.
        try:
            native_balance, token_balance = await self.chain.signer_balances()
            gas_price = await self.chain.gas_price()
        except Exception as exc:
            if self.circuit is not None:
                self.circuit.add_reason("RPC_UNAVAILABLE")
            safe = self.chain.safe_error(exc)
            logger.error("Payout batch preflight failed: error=%s", safe)
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

    async def _reconcile_broadcast(self, payout: dict[str, object]) -> None:
        if self.chain is None:
            return
        payout_id = int(payout["id"])
        receipt = await self.chain.receipt_status(str(payout["tx_hash"]))
        if receipt is None:
            return
        if receipt is False:
            await self.repository.mark_payout_failed(
                payout_id,
                "transaction receipt status is 0",
            )
            return
        await self.repository.mark_payout_confirmed(
            payout_id,
            str(payout["tx_hash"]),
        )

    async def _broadcast(self, payout_id: int, raw_transaction: str) -> None:
        if self.chain is None:
            return
        try:
            await self.chain.broadcast(raw_transaction)
        except Exception as exc:
            safe = self.chain.safe_error(exc)
            lowered = safe.lower()
            already_known = any(
                marker in lowered
                for marker in ("already known", "known transaction", "nonce too low")
            )
            if already_known:
                await self.repository.mark_payout_broadcast(payout_id)
                return
            if "insufficient funds" in lowered:
                if self.circuit is not None:
                    self.circuit.add_reason("LOW_BNB")
                await self.repository.record_payout_error(payout_id, safe)
                return
            deterministic = any(
                marker in lowered
                for marker in (
                    "invalid sender",
                    "intrinsic gas too low",
                    "transaction type not supported",
                )
            )
            if deterministic:
                await self.repository.mark_payout_failed(payout_id, safe)
            else:
                # A timeout can happen after the node accepted the transaction.
                # Keep the same signed bytes and nonce; never create another transfer.
                await self.repository.record_payout_error(payout_id, safe)
            return
        await self.repository.mark_payout_broadcast(payout_id)
