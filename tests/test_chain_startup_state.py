from __future__ import annotations

import base64
import secrets
from types import SimpleNamespace

import pytest
from eth_account import Account

import delta_backend.api as api_module
from delta_backend.api import initialize_chain_runtime
from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings
from delta_backend.repository import DeltaRepository
from delta_backend.runtime_secrets import ChainSecretBundle, RuntimeSecretStore


TOKEN = "123456:STARTUP_STATE_TEST_TOKEN"
SEED = "test test test test test test test test test test test junk"
CONTRACT = "0x55d398326f99059fF775485246999027B3197955"


def _treasury() -> str:
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(SEED, account_path="m/44'/60'/0'/0/0").address


def _bundle(block: int) -> ChainSecretBundle:
    return ChainSecretBundle.create(
        mode="production",
        chain_id=56,
        rpc_url="https://rpc.example.test/key",
        wss_url="wss://wss.example.test/key",
        seed_phrase=SEED,
        token_contract=CONTRACT,
        treasury_address=_treasury(),
        scan_start_block=block,
    )


async def _runtime(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    key = tmp_path / "runtime_config_key.txt"
    key.write_text(base64.b64encode(secrets.token_bytes(32)).decode("ascii") + "\n")
    business = MiniAppSettings(
        _env_file=None,
        demo_mode=False,
        miniapp_url="https://example.test",
        miniapp_origin="https://example.test",
        trusted_hosts="example.test,localhost",
    )
    settings = Settings(
        _env_file=None,
        bot_token=TOKEN,
        owner_ids="42",
        admin_ids="42",
        environment="production",
        database_path=data / "delta.sqlite3",
        chain_enabled=False,
        simulate_payouts=False,
        deposits_enabled=True,
        investments_enabled=True,
        payouts_enabled=True,
        referral_enabled=True,
        runtime_config_key_file=key,
        minimum_native_balance_wei=0,
        minimum_token_balance_usdt=0,
    )
    repository = DeltaRepository(settings.database_path, business)
    await repository.connect()
    store = RuntimeSecretStore(data / "runtime_secrets", key)
    return settings, business, repository, store


class _StartupClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def healthcheck(self):
        if self.settings.scan_start_block == 200:
            raise RuntimeError("provider failed")
        return SimpleNamespace(chain_id=self.settings.chain_id, block_number=300)

    async def websocket_healthcheck(self):
        return SimpleNamespace(
            chain_id=self.settings.chain_id,
            block_number=300,
            subscription_ok=True,
        )

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_fresh_production_runtime_forces_all_financial_flags_off(tmp_path) -> None:
    settings, business, repository, _store = await _runtime(tmp_path)
    try:
        chain, _health, store, setup = await initialize_chain_runtime(
            settings,
            business,
            repository,
        )
        assert chain is None
        assert store is not None
        assert setup.status == "bootstrap"
        assert setup.financial_ready is False
        assert settings.chain_enabled is False
        assert settings.deposits_enabled is False
        assert settings.investments_enabled is False
        assert settings.payouts_enabled is False
        assert settings.referral_enabled is False
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_startup_failure_quarantines_generation_and_degrades(
    tmp_path,
    monkeypatch,
) -> None:
    settings, business, repository, store = await _runtime(tmp_path)
    failed = _bundle(200)
    store.stage(failed)
    store.activate(failed.generation)
    monkeypatch.setattr(api_module, "EvmTokenClient", _StartupClient)
    try:
        chain, _health, _store, setup = await initialize_chain_runtime(
            settings,
            business,
            repository,
        )
        assert chain is None
        assert setup.status == "degraded"
        assert setup.financial_ready is False
        assert setup.last_error_code == "chain_startup_validation_failed"
        assert store.load_active() is None
        assert list(store.root.glob("failed-*.enc"))
        state = await repository.get_chain_config_state()
        assert state["status"] == "degraded"
        assert state["active_generation"] is None
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_startup_failure_rolls_back_to_previous_generation(
    tmp_path,
    monkeypatch,
) -> None:
    settings, business, repository, store = await _runtime(tmp_path)
    previous = _bundle(100)
    failed = _bundle(200)
    store.stage(previous)
    store.activate(previous.generation)
    store.stage(failed)
    store.activate(failed.generation)
    monkeypatch.setattr(api_module, "EvmTokenClient", _StartupClient)
    chain = None
    try:
        chain, _health, _store, setup = await initialize_chain_runtime(
            settings,
            business,
            repository,
        )
        assert chain is not None
        assert setup.status == "active"
        assert setup.financial_ready is True
        assert setup.active_generation == previous.generation
        assert setup.last_error_code == "rolled_back_after_startup_failure"
        assert store.load_active().generation == previous.generation
    finally:
        if chain is not None:
            await chain.close()
        await repository.close()
