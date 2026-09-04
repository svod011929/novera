import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from delta_backend.api_settings import MiniAppSettings
from delta_backend.repository import DeltaRepository
from delta_backend.services.payouts import DailyPayoutService
from delta_backend.services.safety import PayoutCircuitBreaker, SafetyRuntime


@pytest.mark.asyncio
async def test_safety_state_and_payout_metrics(tmp_path: Path):
    repo = DeltaRepository(tmp_path / "safety.sqlite3", MiniAppSettings())
    await repo.connect()
    try:
        assert await repo.database_quick_check() == "ok"
        await repo.set_safety_state("test", '["LOW_BNB"]')
        assert await repo.get_safety_state("test") == '["LOW_BNB"]'

        now = int(time.time())
        async with repo.transaction() as tx:
            await tx.execute(
                "INSERT INTO users(telegram_id, first_name, created_at, last_seen_at) VALUES (?,?,?,?)",
                (1, "Safety", now, now),
            )
            await tx.execute(
                """
                INSERT INTO payouts(
                    idempotency_key,user_id,kind,amount_minor,address,status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                ("safety-payout", 1, "daily", 2_000_000, "0x" + "1" * 40, "queued", now, now),
            )
        metrics = await repo.payout_safety_metrics()
        assert metrics["pending_count"] == 1
        assert metrics["pending_minor"] == 2_000_000
        assert metrics["next_queued_minor"] == 2_000_000
        assert metrics["oldest_age_seconds"] is None
    finally:
        await repo.close()


class NoFundsChain:
    async def signer_balances(self):
        return (10**18, 0)

    async def gas_price(self):
        return 1_000_000_000

    def safe_error(self, exc):
        return str(exc)

    async def sign_token_transfer(self, address, amount_minor):  # pragma: no cover
        raise AssertionError("safety preflight must prevent signing")


@pytest.mark.asyncio
async def test_low_token_balance_keeps_payout_queued(tmp_path: Path):
    repo = DeltaRepository(tmp_path / "guard.sqlite3", MiniAppSettings())
    await repo.connect()
    try:
        now = int(time.time())
        async with repo.transaction() as tx:
            await tx.execute(
                "INSERT INTO users(telegram_id, first_name, created_at, last_seen_at) VALUES (?,?,?,?)",
                (2, "Guard", now, now),
            )
            await tx.execute(
                """
                INSERT INTO payouts(
                    idempotency_key,user_id,kind,amount_minor,address,status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                ("guard-payout", 2, "daily", 1_000_000, "0x" + "2" * 40, "queued", now, now),
            )
        runtime = SafetyRuntime()
        circuit = PayoutCircuitBreaker(runtime)
        circuit.set_reasons([])
        settings = SimpleNamespace(
            payouts_enabled=True,
            simulate_payouts=False,
            token_decimals=18,
            safety_min_native_balance_wei=1_000_000_000_000_000,
        )
        service = DailyPayoutService(repo, settings, NoFundsChain(), circuit)
        await service.run_once()
        row = await repo.get_next_payout()
        assert row is not None
        assert row["status"] == "queued"
        assert "LOW_USDT" in runtime.circuit_reasons
    finally:
        await repo.close()
