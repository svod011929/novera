import logging
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

    async def run_once(self) -> None:
        if not self.settings.payouts_enabled:
            return
        await self.repository.schedule_due_payouts()
        payout = await self.repository.get_next_payout()
        if payout is None:
            return

        payout_id = int(payout["id"])
        if self.settings.simulate_payouts:
            await self.repository.mark_payout_confirmed(
                payout_id,
                f"demo:{uuid.uuid4().hex}",
            )
            return
        if self.chain is None:
            return

        status = str(payout["status"])
        # A safety circuit never blocks reconciliation of already signed/broadcast
        # transactions. It only prevents creation of a new signature/nonce.
        if status == "queued" and self.circuit is not None and self.circuit.is_open:
            return
        if status == "queued":
            try:
                native_balance, token_balance = await self.chain.signer_balances()
                gas_price = await self.chain.gas_price()
                required_token = minor_to_atomic(
                    int(payout["amount_minor"]),
                    int(self.settings.token_decimals),
                )
                required_native = max(
                    int(self.settings.safety_min_native_balance_wei),
                    int(gas_price) * 120_000,
                )
                if int(token_balance) < int(required_token):
                    if self.circuit is not None:
                        self.circuit.add_reason("LOW_USDT")
                    logger.error(
                        "Payout held by safety guard: payout=%s reason=LOW_USDT",
                        payout_id,
                    )
                    return
                if int(native_balance) < required_native:
                    if self.circuit is not None:
                        self.circuit.add_reason("LOW_BNB")
                    logger.error(
                        "Payout held by safety guard: payout=%s reason=LOW_BNB",
                        payout_id,
                    )
                    return
            except Exception as exc:
                if self.circuit is not None:
                    self.circuit.add_reason("RPC_UNAVAILABLE")
                safe = self.chain.safe_error(exc)
                logger.error(
                    "Payout preflight failed without changing payout state: payout=%s error=%s",
                    payout_id,
                    safe,
                )
                return
            try:
                signed = await self.chain.sign_token_transfer(
                    str(payout["address"]),
                    int(payout["amount_minor"]),
                )
                await self.repository.mark_payout_signed(
                    payout_id,
                    signed.tx_hash,
                    signed.raw_transaction,
                    signed.nonce,
                )
                await self._broadcast(payout_id, signed.raw_transaction)
            except Exception as exc:
                safe = self.chain.safe_error(exc)
                await self.repository.mark_payout_failed(payout_id, safe)
                logger.error("Payout signing failed: payout=%s error=%s", payout_id, safe)
            return

        if status == "signed":
            await self._broadcast(payout_id, str(payout["raw_transaction"]))
            return

        if status == "broadcast":
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
