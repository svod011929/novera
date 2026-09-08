import asyncio
import logging
import time

from ..config import Settings
from ..models import TransferEvent
from ..repository import DeltaRepository
from .blockchain import EvmTokenClient


logger = logging.getLogger(__name__)


class DepositMonitor:
    """Fast WSS-first deposit monitor with HTTPS only as recovery/backfill.

    Normal path:
    1. Alchemy WSS delivers the USDT Transfer log immediately.
    2. Alchemy WSS newHeads advances the confirmation clock.
    3. Once the configured confirmation depth is reached, the transfer is
       applied directly from the already-received WSS event; no eth_getLogs
       call is required for the normal realtime path.

    HTTPS JSON-RPC remains a safety net for startup/reconnect backfill and for
    confirmation fallback when newHeads is temporarily unavailable.
    """

    def __init__(
        self,
        repository: DeltaRepository,
        settings: Settings,
        chain: EvmTokenClient,
        telemetry: object | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.chain = chain
        self.telemetry = telemetry
        token_key = settings.token_contract.lower()
        self.sync_key = f"last_processed_block:{settings.chain_id}:{token_key}"
        self._scan_lock = asyncio.Lock()
        self._pending_live: dict[tuple[str, int], TransferEvent] = {}
        self._latest_ws_head = -1
        self._live_head_event = asyncio.Event()
        self._wss_connected = False
        self._wss_last_event_at = 0.0

    def mark_wss_connected(self, connected: bool) -> None:
        self._wss_connected = connected
        if connected:
            self._wss_last_event_at = time.time()
        if self.telemetry is not None:
            setattr(self.telemetry, "wss_connected", bool(connected))

    def _http_poll_interval(self) -> float:
        """HTTP is a safety net when WSS is healthy; a fast path when it is not."""
        configured = max(1, int(self.settings.deposit_scan_interval_seconds))
        healthy_min = max(
            configured,
            int(getattr(self.settings, "deposit_scan_healthy_min_seconds", 60)),
        )
        degraded = max(
            2,
            int(getattr(self.settings, "deposit_scan_degraded_seconds", 4)),
        )
        stale_after = max(
            30,
            int(getattr(self.settings, "safety_wss_stale_seconds", 180)) // 2,
        )
        wss_fresh = (
            self._wss_connected
            and self._wss_last_event_at > 0
            and (time.time() - self._wss_last_event_at) < stale_after
        )
        return float(healthy_min if wss_fresh else min(configured, degraded))

    async def _initial_height(self, safe_head: int) -> int:
        stored = await self.repository.get_sync_height(self.sync_key)
        configured_floor = (
            self.settings.scan_start_block - 1
            if self.settings.scan_start_block > 0
            else safe_head
        )
        if stored is None:
            await self.repository.set_sync_height(self.sync_key, configured_floor)
            return configured_floor
        if self.settings.scan_start_block > 0 and stored < configured_floor:
            logger.warning(
                "Deposit sync cursor %s predates configured scan start; "
                "advancing it to %s",
                stored,
                configured_floor,
            )
            await self.repository.set_sync_height(self.sync_key, configured_floor)
            return configured_floor
        return stored

    async def _scan_locked(self, *, drain: bool) -> None:
        """HTTPS recovery path. It is not used to confirm healthy WSS events."""
        await self.repository.expire_invoices()
        head = await self.chain.latest_block()
        if self.telemetry is not None:
            setattr(self.telemetry, "http_last_head", int(head))
        safe_head = head - max(0, int(self.settings.confirmation_blocks))
        if safe_head < 0:
            return

        cursor = await self._initial_height(safe_head)
        while cursor < safe_head:
            from_block = cursor + 1
            chunk = min(
                max(1, int(self.settings.scan_block_chunk)),
                self.chain.adaptive_log_chunk,
            )
            to_block = min(safe_head, from_block + chunk - 1)
            transfers = await self.chain.get_incoming_transfers(from_block, to_block)
            for transfer in transfers:
                await self._apply_transfer(transfer, source="https-backfill")
            await self.repository.set_sync_height(self.sync_key, to_block)
            cursor = to_block
            if not drain:
                break
        if self.telemetry is not None:
            setattr(self.telemetry, "http_last_scan_at", time.time())

    async def scan_confirmed(self) -> None:
        async with self._scan_lock:
            await self._scan_locked(drain=True)

    async def backfill_to_current(self) -> None:
        """Backfill missed confirmed blocks after a WSS subscription/reconnect."""
        async with self._scan_lock:
            await self._scan_locked(drain=True)

    @staticmethod
    def _event_key(transfer: TransferEvent) -> tuple[str, int]:
        return (transfer.tx_hash.lower(), transfer.log_index)

    async def _apply_transfer(self, transfer: TransferEvent, *, source: str) -> None:
        result = await self.repository.apply_transfer(transfer)
        if result.get("duplicate"):
            return
        if result.get("matched"):
            logger.info(
                "Deposit opened from %s: user=%s deposit=%s tx=%s",
                source,
                result.get("user_id"),
                result.get("deposit_id"),
                transfer.tx_hash,
            )
        else:
            logger.info(
                "Unmatched token transfer from %s: tx=%s log_index=%s",
                source,
                transfer.tx_hash,
                transfer.log_index,
            )

    async def handle_live_transfer(self, transfer: TransferEvent) -> None:
        key = self._event_key(transfer)
        confirmations = max(0, int(self.settings.confirmation_blocks))
        safe_head = self._latest_ws_head - confirmations

        if confirmations == 0 or transfer.block_number <= safe_head:
            try:
                await self._apply_transfer(transfer, source="alchemy-wss")
            except Exception:
                self._pending_live[key] = transfer
                self._live_head_event.set()
                raise
            self._pending_live.pop(key, None)
            return

        self._pending_live[key] = transfer
        self._live_head_event.set()

    async def handle_live_head(self, block_number: int) -> None:
        if block_number > self._latest_ws_head:
            self._latest_ws_head = block_number
        self._wss_last_event_at = time.time()
        self._wss_connected = True
        if self.telemetry is not None:
            setattr(self.telemetry, "wss_last_head", int(block_number))
            setattr(self.telemetry, "wss_last_head_at", time.time())
            setattr(self.telemetry, "wss_connected", True)
        self._live_head_event.set()

    async def handle_removed_live_transfer(self, tx_hash: str, log_index: int) -> None:
        self._pending_live.pop((tx_hash.lower(), log_index), None)

    async def _process_confirmed_live(self) -> None:
        if not self._pending_live:
            return

        confirmations = max(0, int(self.settings.confirmation_blocks))
        if self._latest_ws_head < 0:
            # Only a fallback. In healthy operation newHeads supplies this value.
            self._latest_ws_head = await self.chain.latest_block()
        safe_head = self._latest_ws_head - confirmations

        ready = sorted(
            (
                (key, transfer)
                for key, transfer in self._pending_live.items()
                if transfer.block_number <= safe_head
            ),
            key=lambda item: (item[1].block_number, item[1].log_index),
        )
        for key, transfer in ready:
            await self._apply_transfer(transfer, source="alchemy-wss")
            self._pending_live.pop(key, None)

    async def _live_confirmation_worker(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            timed_out = False
            try:
                await asyncio.wait_for(self._live_head_event.wait(), timeout=1.0)
            except TimeoutError:
                timed_out = True
            self._live_head_event.clear()

            if not self._pending_live:
                continue

            if timed_out:
                # If Alchemy newHeads is flowing, this branch is not used.
                # HTTP exists only as a confirmation safety fallback.
                try:
                    head = await self.chain.latest_block()
                    if head > self._latest_ws_head:
                        self._latest_ws_head = head
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.debug(
                        "HTTPS confirmation fallback failed (%s)",
                        self.chain.safe_error(exc),
                    )
                    continue

            try:
                await self._process_confirmed_live()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Live WSS deposit confirmation failed (%s)",
                    self.chain.safe_error(exc),
                )

    async def run_websocket(self, stop_event: asyncio.Event) -> None:
        confirmation_task = asyncio.create_task(
            self._live_confirmation_worker(stop_event),
            name="deposit-live-confirmations",
        )

        async def on_subscribed() -> None:
            self.mark_wss_connected(True)
            await self.backfill_to_current()

        try:
            async for transfer in self.chain.stream_incoming_transfers(
                stop_event,
                on_subscribed=on_subscribed,
                on_head=self.handle_live_head,
                on_removed=self.handle_removed_live_transfer,
            ):
                self._wss_last_event_at = time.time()
                try:
                    await self.handle_live_transfer(transfer)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "Failed to process Alchemy WSS Transfer (%s)",
                        self.chain.safe_error(exc),
                    )
        finally:
            self.mark_wss_connected(False)
            confirmation_task.cancel()
            await asyncio.gather(confirmation_task, return_exceptions=True)

    async def run_polling(self, stop_event: asyncio.Event) -> None:
        """HTTP safety net: slow while WSS is healthy, fast while it is not."""
        while not stop_event.is_set():
            try:
                await self.scan_confirmed()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Deposit safety backfill failed: %s", self.chain.safe_error(exc))
            interval = self._http_poll_interval()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except TimeoutError:
                pass
