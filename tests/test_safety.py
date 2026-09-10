import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from delta_backend.api_settings import MiniAppSettings
from delta_backend.repository import DeltaRepository
from delta_backend.services.payouts import DailyPayoutService
from delta_backend.services.safety import PayoutCircuitBreaker, SafetyMonitor, SafetyRuntime


class SafetyStateRepository:
    def __init__(self, raw_state: str | None = None) -> None:
        self.raw_state = raw_state
        self.saved_state: str | None = None

    async def get_safety_state(self, key: str) -> str | None:
        assert key == SafetyMonitor.ALERT_STATE_KEY
        return self.raw_state

    async def set_safety_state(self, key: str, value: str) -> None:
        assert key == SafetyMonitor.ALERT_STATE_KEY
        self.saved_state = value


class RecordingOpsChat:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def notify_safety(self, text: str) -> None:
        self.messages.append(text)


class FailingOpsChat:
    async def notify_safety(self, text: str) -> None:
        raise RuntimeError("ops unavailable")


def safety_monitor_for_transitions(
    repository: SafetyStateRepository,
    ops_chat: object | None,
) -> tuple[SafetyMonitor, list[str]]:
    monitor = object.__new__(SafetyMonitor)
    monitor.repository = repository
    monitor.ops_chat = ops_chat
    admin_messages: list[str] = []

    async def send_admin(text: str) -> None:
        admin_messages.append(text)

    monitor._send_admin = send_admin
    return monitor, admin_messages


@pytest.mark.asyncio
async def test_safety_transition_mirrors_admin_alerts_to_ops_chat() -> None:
    repository = SafetyStateRepository(json.dumps(["LOW_BNB"]))
    ops_chat = RecordingOpsChat()
    monitor, admin_messages = safety_monitor_for_transitions(repository, ops_chat)

    await monitor._publish_transitions({"LOW_USDT"})

    assert ops_chat.messages == admin_messages
    assert ops_chat.messages == [
        monitor._alert_text("LOW_USDT", recovered=False),
        monitor._alert_text("LOW_BNB", recovered=True),
    ]
    assert repository.saved_state == json.dumps(["LOW_USDT"])


@pytest.mark.asyncio
async def test_safety_transition_logs_ops_mirror_failures(caplog: pytest.LogCaptureFixture) -> None:
    repository = SafetyStateRepository()
    monitor, admin_messages = safety_monitor_for_transitions(repository, FailingOpsChat())

    await monitor._publish_transitions({"LOW_BNB"})

    assert admin_messages == [monitor._alert_text("LOW_BNB", recovered=False)]
    assert repository.saved_state == json.dumps(["LOW_BNB"])
    assert "Ops safety mirror failed: RuntimeError" in caplog.text


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
    async def is_delegated(self):
        return False

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
