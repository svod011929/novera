from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

httpx = pytest.importorskip("httpx")

import delta_backend.api as api_module
from delta_backend.api import ChainSetupRuntime, SlidingWindowRateLimiter, app
from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings
from delta_backend.repository import DeltaRepository
from delta_backend.runtime_secrets import RuntimeSecretStore


TOKEN = "123456:CHAIN_SETUP_TEST_TOKEN"
OWNER_ID = 42
ADMIN_ID = 43
SEED = "test test test test test test test test test test test junk"
RPC = "https://rpc.example.test/private-value"
WSS = "wss://wss.example.test/private-value"
CONTRACT = "0x55d398326f99059fF775485246999027B3197955"


def _init_data(user_id: int) -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": f"setup-{user_id}",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": f"User {user_id}",
                "username": f"user_{user_id}",
                "language_code": "ru",
            },
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


class _HealthyClient:
    def __init__(self, settings) -> None:
        self.settings = settings

    async def healthcheck(self):
        return SimpleNamespace(chain_id=self.settings.chain_id, block_number=123456)

    async def websocket_healthcheck(self):
        return SimpleNamespace(
            chain_id=self.settings.chain_id,
            block_number=123456,
            subscription_ok=True,
        )

    async def close(self) -> None:
        return None

    @staticmethod
    def safe_error(exc: Exception) -> str:
        return type(exc).__name__


async def _allow_public_provider(*_args, **_kwargs) -> None:
    return None


async def _prepare(tmp_path):
    key_file = tmp_path / "runtime_config_key.txt"
    key_file.write_text(base64.b64encode(secrets.token_bytes(32)).decode("ascii") + "\n")
    business = MiniAppSettings(
        _env_file=None,
        demo_mode=False,
        miniapp_url="https://example.test",
        miniapp_origin="https://example.test",
        trusted_hosts="example.test,localhost",
    )
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        owner_ids=str(OWNER_ID),
        admin_ids=str(OWNER_ID),
        environment="production",
        chain_enabled=False,
        simulate_payouts=False,
        deposits_enabled=False,
        investments_enabled=False,
        payouts_enabled=False,
        referral_enabled=False,
        runtime_config_key_file=key_file,
        minimum_native_balance_wei=0,
        minimum_token_balance_usdt=0,
    )
    repository = DeltaRepository(tmp_path / "chain-setup.sqlite3", business)
    await repository.connect()
    await repository.ensure_user(OWNER_ID, "owner", "Owner", "ru")
    await repository.ensure_user(ADMIN_ID, "admin", "Admin", "ru")
    await repository.grant_admin(str(ADMIN_ID), OWNER_ID)
    store = RuntimeSecretStore(tmp_path / "runtime_secrets", key_file)
    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.secret_store = store
    app.state.chain_setup = ChainSetupRuntime(status="bootstrap", financial_ready=False)
    app.state.rate_limiter = SlidingWindowRateLimiter()
    return repository, store


@pytest.mark.asyncio
async def test_only_owner_can_stage_and_activate_chain_configuration(
    tmp_path,
    monkeypatch,
) -> None:
    repository, store = await _prepare(tmp_path)
    monkeypatch.setattr(api_module, "validate_public_provider_url", _allow_public_provider)
    monkeypatch.setattr(api_module, "EvmTokenClient", _HealthyClient)
    monkeypatch.setattr(api_module, "schedule_process_restart", lambda: None)
    payload = {
        "mode": "production",
        "token_contract": CONTRACT,
        "scan_start_block": 123400,
        "rpc_url": RPC,
        "wss_url": WSS,
        "seed_phrase": SEED,
        "reason": "Initial owner activation",
    }
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            denied = await client.post(
                "/api/admin/chain-config/validate",
                headers={"X-Telegram-Init-Data": _init_data(ADMIN_ID)},
                json=payload,
            )
            assert denied.status_code == 403
            role_denied = await client.post(
                "/api/admin/admins",
                headers={"X-Telegram-Init-Data": _init_data(ADMIN_ID)},
                json={"identifier": str(OWNER_ID)},
            )
            assert role_denied.status_code == 403

            staged = await client.post(
                "/api/admin/chain-config/validate",
                headers={"X-Telegram-Init-Data": _init_data(OWNER_ID)},
                json=payload,
            )
            assert staged.status_code == 200
            staged_body = staged.json()
            generation = staged_body["generation"]
            treasury = staged_body["treasury_address"]
            serialized = json.dumps(staged_body)
            assert SEED not in serialized
            assert "private-value" not in serialized
            assert store.load_pending(generation).treasury_address == treasury

            activated = await client.post(
                "/api/admin/chain-config/activate",
                headers={"X-Telegram-Init-Data": _init_data(OWNER_ID)},
                json={
                    "generation": generation,
                    "treasury_confirmation": treasury,
                    "operation_id": "activate-chain-000001",
                    "reason": "Treasury address confirmed",
                    "confirm": "ACTIVATE_CHAIN",
                },
            )
            assert activated.status_code == 200
            assert activated.json()["activated"] is True
            assert store.load_active().generation == generation
            state = await repository.get_chain_config_state()
            assert state["status"] == "active"
            assert state["active_generation"] == generation
            operation = await repository.get_chain_activation("activate-chain-000001")
            assert str(operation["reason"]).startswith("sha256:")
            audit = json.dumps(await repository.admin_audit(20))
            assert "Initial owner activation" not in audit
            assert "Treasury address confirmed" not in audit
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_chain_validation_never_echoes_rejected_secret(tmp_path) -> None:
    repository, _store = await _prepare(tmp_path)
    marker = "DO-NOT-ECHO-" + ("x" * 600)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post(
                "/api/admin/chain-config/validate",
                headers={"X-Telegram-Init-Data": _init_data(OWNER_ID)},
                json={
                    "mode": "production",
                    "token_contract": CONTRACT,
                    "scan_start_block": 123400,
                    "rpc_url": RPC,
                    "wss_url": WSS,
                    "seed_phrase": marker,
                    "reason": "Reject oversized secret",
                },
            )
        assert response.status_code == 422
        assert marker not in response.text
        assert "DO-NOT-ECHO" not in response.text
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_provider_validation_blocks_local_and_metadata_addresses() -> None:
    for value in (
        "https://127.0.0.1/rpc",
        "https://169.254.169.254/latest/meta-data",
        "wss://[::1]/rpc",
    ):
        with pytest.raises(HTTPException) as caught:
            await api_module.validate_public_provider_url(
                value,
                schemes=frozenset({"https", "wss"}),
                label="Provider",
            )
        assert caught.value.status_code == 422
