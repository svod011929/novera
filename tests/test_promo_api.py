"""API tests for user + admin promo code HTTP surface (I-11 Task 3).

Follows the auth fixture pattern from tests/test_broadcast_api.py and
tests/test_admin_controls_api.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

httpx = pytest.importorskip("httpx")

from delta_backend.amounts import minor_to_text, usdt_to_minor
from delta_backend.api import SlidingWindowRateLimiter, app
from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings
from delta_backend.models import TransferEvent
from delta_backend.repository import DeltaRepository


TOKEN = "123456:TEST_TOKEN"
ADMIN_ID = 42
USER_ID = 100
TREASURY = "0x00000000000000000000000000000000000001"
USER_WALLET = "0x0000000000000000000000000000000000000002"


def signed_init_data(*, user_id: int = ADMIN_ID, username: str = "admin_user") -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "signature": "telegram-third-party-signature",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": f"User {user_id}",
                "username": username,
                "language_code": "ru",
            },
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


async def _prepare(tmp_path):
    business = MiniAppSettings(_env_file=None, demo_mode=False, force_https=False)
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        admin_ids=str(ADMIN_ID),
        environment="testnet",
        chain_enabled=False,
        simulate_payouts=True,
        treasury_address=TREASURY,
    )
    # Flip chain_enabled after construction: constructing with chain_enabled=True
    # requires a full RPC/signing configuration that these HTTP-layer tests do
    # not exercise. create_invoice only checks the boolean flags at request
    # time, so mutating post-validation keeps the fixture minimal like the
    # other API test files while still exercising the enabled-deposits path.
    chain.chain_enabled = True
    repository = DeltaRepository(tmp_path / "promo_api.sqlite3", business)
    await repository.connect()
    await repository.ensure_user(ADMIN_ID, "admin_user", "Admin", "ru")
    await repository.ensure_user(USER_ID, "member", "Member", "ru")
    await repository.set_wallet(USER_ID, USER_WALLET)

    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.rate_limiter = SlidingWindowRateLimiter()
    # The FastAPI app is a shared module-level singleton across test files.
    # Other suites (e.g. test_chain_setup_api.py) leave a non-active
    # ChainSetupRuntime on app.state, which would make
    # require_financial_activation reject deposits here. Clearing it restores
    # the "no lifespan" bypass used by test_api.py / test_broadcast_api.py.
    app.state.chain_setup = None
    return repository


async def _open_deposit_via_transfer(repository: DeltaRepository, exact_minor: int, log_index: int) -> dict:
    result = await repository.apply_transfer(
        TransferEvent(
            chain_id=97,
            tx_hash=f"0x{log_index:064x}",
            log_index=log_index,
            block_number=100 + log_index,
            from_address=USER_WALLET,
            to_address=TREASURY,
            amount_atomic=exact_minor * 10**12,
            amount_minor=exact_minor,
        )
    )
    assert result["matched"] is True
    return result


@pytest.mark.asyncio
async def test_admin_promo_routes_reject_non_admin(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data(user_id=USER_ID, username="member")}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            assert (await client.get("/api/admin/promo-codes", headers=headers)).status_code == 403
            assert (
                await client.post(
                    "/api/admin/promo-codes",
                    headers=headers,
                    json={
                        "code": "NOPE",
                        "bonus_type": "percent",
                        "bonus_percent": "10",
                        "max_redemptions": 10,
                    },
                )
            ).status_code == 403
            assert (
                await client.patch(
                    "/api/admin/promo-codes/1", headers=headers, json={"enabled": False}
                )
            ).status_code == 403
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_admin_can_create_percent_promo(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data()}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post(
                "/api/admin/promo-codes",
                headers=headers,
                json={
                    "code": "welcome10",
                    "bonus_type": "percent",
                    "bonus_percent": "10",
                    "max_redemptions": 100,
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["code"] == "WELCOME10"
            assert body["bonus_type"] == "percent"
            assert int(body["bonus_bps"]) == 1000
            assert body["bonus_percent"] == "10"

            listing = await client.get("/api/admin/promo-codes", headers=headers)
            assert listing.status_code == 200
            assert any(item["code"] == "WELCOME10" for item in listing.json())

            # Duplicate code -> 409.
            duplicate = await client.post(
                "/api/admin/promo-codes",
                headers=headers,
                json={
                    "code": "WELCOME10",
                    "bonus_type": "fixed",
                    "bonus_usdt": "5",
                    "max_redemptions": 10,
                },
            )
            assert duplicate.status_code == 409

            # Percent promo without bonus_percent -> 422.
            missing = await client.post(
                "/api/admin/promo-codes",
                headers=headers,
                json={"code": "BADPCT", "bonus_type": "percent", "max_redemptions": 10},
            )
            assert missing.status_code == 422

            # PATCH toggles enabled flag.
            promo_id = int(body["id"])
            patched = await client.patch(
                f"/api/admin/promo-codes/{promo_id}",
                headers=headers,
                json={"enabled": False},
            )
            assert patched.status_code == 200
            assert patched.json()["enabled"] is False

            missing_patch = await client.patch(
                "/api/admin/promo-codes/999999", headers=headers, json={"enabled": True}
            )
            assert missing_patch.status_code == 404
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_invoice_with_promo_returns_bonus_fields_and_second_use_is_conflict(
    tmp_path,
) -> None:
    repository = await _prepare(tmp_path)
    admin_headers = {"X-Telegram-Init-Data": signed_init_data()}
    user_headers = {
        "X-Telegram-Init-Data": signed_init_data(user_id=USER_ID, username="member")
    }
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            created = await client.post(
                "/api/admin/promo-codes",
                headers=admin_headers,
                json={
                    "code": "PLUS10",
                    "bonus_type": "percent",
                    "bonus_percent": "10",
                    "max_redemptions": 50,
                },
            )
            assert created.status_code == 200

            response = await client.post(
                "/api/deposits/invoice",
                headers={**user_headers, "Idempotency-Key": "invoice-promo-test-0001"},
                json={"amount": 100, "promo_code": "plus10"},
            )
            assert response.status_code == 200
            body = response.json()
            bonus_minor = usdt_to_minor("10")
            base_minor = usdt_to_minor("100")
            assert body["bonus_minor"] == bonus_minor
            assert body["bonus_usdt"] == minor_to_text(bonus_minor, trim=False)
            # Preview is computed from base_minor, not the jittered exact amount.
            assert body["effective_principal_usdt"] == minor_to_text(
                base_minor + bonus_minor, trim=False
            )
            assert body["promo_code_id"] is not None
            exact_minor = usdt_to_minor(body["exact_amount"])

            # Open the deposit so the redemption is actually committed.
            await _open_deposit_via_transfer(repository, exact_minor, log_index=1)

            # A second invoice with the same promo for the same user is rejected.
            conflict = await client.post(
                "/api/deposits/invoice",
                headers={**user_headers, "Idempotency-Key": "invoice-promo-test-0002"},
                json={"amount": 50, "promo_code": "PLUS10"},
            )
            assert conflict.status_code == 409
    finally:
        await repository.close()
