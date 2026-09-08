from types import SimpleNamespace

import pytest

from delta_backend.models import TransferEvent
from delta_backend.services.blockchain import EvmTokenClient
from delta_backend.services.deposit_monitor import DepositMonitor


class _SyncRepository:
    def __init__(self, stored: int | None) -> None:
        self.stored = stored
        self.writes: list[tuple[str, int]] = []

    async def get_sync_height(self, key: str) -> int | None:
        return self.stored

    async def set_sync_height(self, key: str, value: int) -> None:
        self.stored = value
        self.writes.append((key, value))


@pytest.mark.asyncio
async def test_scan_cursor_is_advanced_to_configured_start() -> None:
    settings = SimpleNamespace(
        token_contract="0x1",
        chain_id=56,
        scan_start_block=120_000_000,
        scan_block_chunk=1500,
        confirmation_blocks=12,
        deposit_scan_interval_seconds=120,
    )
    repository = _SyncRepository(stored=3_016_373)
    service = DepositMonitor(
        repository=repository,
        settings=settings,
        chain=SimpleNamespace(),
    )

    height = await service._initial_height(safe_head=120_500_000)

    assert height == 119_999_999
    assert repository.stored == 119_999_999
    assert repository.writes == [(service.sync_key, 119_999_999)]


def test_log_scan_starts_at_configured_chunk_ceiling(monkeypatch) -> None:
    settings = SimpleNamespace(
        token_contract="0x55d398326f99059ff775485246999027b3197955",
        treasury_address="0x0000000000000000000000000000000000000001",
        bsc_rpc_url="https://rpc.example",
        bsc_rpc_fallback_url=None,
        bsc_rpc_timeout_seconds=10,
        bsc_wss_url="wss://rpc.example",
        scan_block_chunk=1500,
        payout_seed_phrase=None,
        payout_private_key=None,
        payout_keystore_password=None,
    )
    monkeypatch.setattr(
        EvmTokenClient,
        "_load_private_key",
        staticmethod(lambda _settings: ""),
    )

    client = EvmTokenClient(settings)

    assert client.adaptive_log_chunk == 1500


@pytest.mark.asyncio
async def test_wss_head_confirms_pending_transfer_without_http_scan(monkeypatch) -> None:
    settings = SimpleNamespace(
        token_contract="0x1",
        chain_id=56,
        scan_start_block=0,
        scan_block_chunk=1500,
        confirmation_blocks=2,
        deposit_scan_interval_seconds=120,
    )
    repository = SimpleNamespace()
    service = DepositMonitor(
        repository=repository,
        settings=settings,
        chain=SimpleNamespace(),
    )
    applied = []

    async def fake_apply(transfer: TransferEvent, *, source: str) -> None:
        applied.append((transfer, source))

    monkeypatch.setattr(service, "_apply_transfer", fake_apply)
    transfer = TransferEvent(
        chain_id=56,
        tx_hash="0xabc",
        log_index=7,
        block_number=100,
        from_address="0xfrom",
        to_address="0xto",
        amount_atomic=1,
        amount_minor=1,
    )

    await service.handle_live_head(100)
    await service.handle_live_transfer(transfer)
    assert applied == []

    await service.handle_live_head(102)
    await service._process_confirmed_live()
    assert applied == [(transfer, "alchemy-wss")]
    assert service._pending_live == {}


@pytest.mark.asyncio
async def test_removed_wss_log_is_dropped_before_confirmation() -> None:
    settings = SimpleNamespace(
        token_contract="0x1",
        chain_id=56,
        scan_start_block=0,
        scan_block_chunk=1500,
        confirmation_blocks=2,
        deposit_scan_interval_seconds=120,
    )
    service = DepositMonitor(
        repository=SimpleNamespace(),
        settings=settings,
        chain=SimpleNamespace(),
    )
    transfer = TransferEvent(
        chain_id=56,
        tx_hash="0xdef",
        log_index=3,
        block_number=200,
        from_address="0xfrom",
        to_address="0xto",
        amount_atomic=1,
        amount_minor=1,
    )

    await service.handle_live_head(200)
    await service.handle_live_transfer(transfer)
    assert service._pending_live

    await service.handle_removed_live_transfer("0xdef", 3)
    assert service._pending_live == {}


def test_http_poll_interval_is_slow_when_wss_healthy_and_fast_when_degraded() -> None:
    settings = SimpleNamespace(
        token_contract="0x1",
        chain_id=56,
        scan_start_block=0,
        scan_block_chunk=1500,
        confirmation_blocks=12,
        deposit_scan_interval_seconds=15,
        deposit_scan_healthy_min_seconds=60,
        deposit_scan_degraded_seconds=4,
        safety_wss_stale_seconds=180,
    )
    service = DepositMonitor(
        repository=SimpleNamespace(),
        settings=settings,
        chain=SimpleNamespace(),
    )

    # No WSS yet → fast HTTP recovery.
    assert service._http_poll_interval() == 4.0

    service.mark_wss_connected(True)
    service._wss_last_event_at = __import__("time").time()
    assert service._http_poll_interval() == 60.0

    # Stale WSS → fall back to fast scan.
    service._wss_last_event_at = __import__("time").time() - 120
    assert service._http_poll_interval() == 4.0
