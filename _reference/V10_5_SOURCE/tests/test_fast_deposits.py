from types import SimpleNamespace

import pytest

from delta_backend.models import TransferEvent
from delta_backend.services.deposit_monitor import DepositMonitor


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
