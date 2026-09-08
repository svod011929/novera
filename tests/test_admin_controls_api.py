"""API-layer hardening tests for V10.6 admin money controls.

I-08 scope: cover referral-balance / referral-level / investments at the HTTP
boundary. Owner has not approved deposit min/max clamping or new idempotency
keys for balance/level — those stay deferred.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from urllib.parse import urlencode

import pytest

httpx = pytest.importorskip("httpx")

from delta_backend.api import SlidingWindowRateLimiter, app
from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings
from delta_backend.repository import DeltaRepository


TOKEN = "123456:TEST_TOKEN"
ADMIN_ID = 42
USER_ID = 100
WALLET = "0x00000000000000000000000000000000000000Aa"


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


async def _prepare(tmp_path, *, admin_ids: str = str(ADMIN_ID)):
    business = MiniAppSettings(_env_file=None, demo_mode=False, force_https=False)
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        admin_ids=admin_ids,
        environment="testnet",
        chain_enabled=False,
        simulate_payouts=True,
    )
    repository = DeltaRepository(tmp_path / "admin-controls.sqlite3", business)
    await repository.connect()
    await repository.ensure_user(ADMIN_ID, "admin_user", "Admin", "ru")
    await repository.ensure_user(USER_ID, "member", "Member", "ru")
    await repository.set_wallet(USER_ID, WALLET)
    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.rate_limiter = SlidingWindowRateLimiter()
    return repository


@pytest.mark.asyncio
async def test_admin_referral_balance_and_level_api_are_audited(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data()}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post(
                f"/api/admin/users/{USER_ID}/referral-balance",
                headers={**headers, "Idempotency-Key": "admin-ref-bal-api-0001"},
                json={"balance_usdt": "7.5", "reason": "Campaign top-up"},
            )
            assert response.status_code == 200
            body = response.json()
            assert Decimal(body["balance_usdt"]) == Decimal("7.5")
            assert body["new_balance_minor"] == 7_500_000
            assert "old_balance_minor" in body
            assert body.get("reused") is False

            repeated = await client.post(
                f"/api/admin/users/{USER_ID}/referral-balance",
                headers={**headers, "Idempotency-Key": "admin-ref-bal-api-0001"},
                json={"balance_usdt": "7.5", "reason": "Campaign top-up"},
            )
            assert repeated.status_code == 200
            assert repeated.json().get("reused") is True
            assert repeated.json()["new_balance_minor"] == 7_500_000

            conflict = await client.post(
                f"/api/admin/users/{USER_ID}/referral-balance",
                headers={**headers, "Idempotency-Key": "admin-ref-bal-api-0001"},
                json={"balance_usdt": "8.0", "reason": "Campaign top-up"},
            )
            assert conflict.status_code == 409

            response = await client.post(
                f"/api/admin/users/{USER_ID}/referral-level",
                headers={**headers, "Idempotency-Key": "admin-ref-lvl-api-0001"},
                json={"unlocked_level": 3, "reason": "Manual unlock"},
            )
            assert response.status_code == 200
            assert response.json()["unlocked_level"] == 3
            assert response.json().get("reused") is False

            repeated_level = await client.post(
                f"/api/admin/users/{USER_ID}/referral-level",
                headers={**headers, "Idempotency-Key": "admin-ref-lvl-api-0001"},
                json={"unlocked_level": 3, "reason": "Manual unlock"},
            )
            assert repeated_level.status_code == 200
            assert repeated_level.json().get("reused") is True

            detail = await client.get(f"/api/admin/users/{USER_ID}", headers=headers)
            assert detail.status_code == 200
            payload = detail.json()
            assert "partner_stats" in payload
            assert "partners" in payload
            assert payload["referral_balance_adjustments"]
            assert payload["referral_balance_adjustments"][0]["reason"] == "Campaign top-up"
            assert payload["referral_level_adjustments"]
            assert payload["referral_level_override"]["unlocked_level"] == 3
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_admin_investment_api_is_idempotent_and_rejects_bad_input(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data()}
    operation_id = "admin_invest_op_000001"
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            first = await client.post(
                f"/api/admin/users/{USER_ID}/investments",
                headers=headers,
                json={
                    "amount_usdt": "50",
                    "reason": "Manual open",
                    "operation_id": operation_id,
                    "confirm": "OPEN_INVESTMENT",
                },
            )
            assert first.status_code == 200
            first_body = first.json()
            assert first_body["status"] == "active"
            assert first_body["principal_minor"] == 50_000_000

            repeated = await client.post(
                f"/api/admin/users/{USER_ID}/investments",
                headers=headers,
                json={
                    "amount_usdt": "50",
                    "reason": "Manual open",
                    "operation_id": operation_id,
                    "confirm": "OPEN_INVESTMENT",
                },
            )
            assert repeated.status_code == 200
            assert repeated.json()["id"] == first_body["id"]
            assert repeated.json().get("reused") is True

            zero = await client.post(
                f"/api/admin/users/{USER_ID}/investments",
                headers=headers,
                json={
                    "amount_usdt": "0",
                    "reason": "Should fail",
                    "operation_id": "admin_invest_op_000002",
                    "confirm": "OPEN_INVESTMENT",
                },
            )
            assert zero.status_code == 422

            blank_reason = await client.post(
                f"/api/admin/users/{USER_ID}/investments",
                headers=headers,
                json={
                    "amount_usdt": "10",
                    "reason": "  ",
                    "operation_id": "admin_invest_op_000003",
                    "confirm": "OPEN_INVESTMENT",
                },
            )
            assert blank_reason.status_code == 422

            bad_confirm = await client.post(
                f"/api/admin/users/{USER_ID}/investments",
                headers=headers,
                json={
                    "amount_usdt": "10",
                    "reason": "Missing confirm literal",
                    "operation_id": "admin_invest_op_000004",
                    "confirm": "YES",
                },
            )
            assert bad_confirm.status_code == 422
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_admin_controls_reject_non_admin_and_invalid_levels(tmp_path) -> None:
    repository = await _prepare(tmp_path, admin_ids=str(ADMIN_ID))
    admin_headers = {"X-Telegram-Init-Data": signed_init_data(user_id=ADMIN_ID)}
    user_headers = {
        "X-Telegram-Init-Data": signed_init_data(user_id=USER_ID, username="member")
    }
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            forbidden = await client.post(
                f"/api/admin/users/{USER_ID}/referral-balance",
                headers=user_headers,
                json={"balance_usdt": "1", "reason": "Nope"},
            )
            assert forbidden.status_code == 403

            negative = await client.post(
                f"/api/admin/users/{USER_ID}/referral-balance",
                headers=admin_headers,
                json={"balance_usdt": "-1", "reason": "Bad amount"},
            )
            assert negative.status_code == 422

            blank = await client.post(
                f"/api/admin/users/{USER_ID}/referral-balance",
                headers=admin_headers,
                json={"balance_usdt": "1", "reason": "  "},
            )
            assert blank.status_code == 422

            bad_level = await client.post(
                f"/api/admin/users/{USER_ID}/referral-level",
                headers=admin_headers,
                json={"unlocked_level": 9, "reason": "Out of range"},
            )
            assert bad_level.status_code == 422

            missing_wallet_user = 101
            await repository.ensure_user(missing_wallet_user, "nowallet", "NoWallet", "ru")
            no_wallet = await client.post(
                f"/api/admin/users/{missing_wallet_user}/investments",
                headers=admin_headers,
                json={
                    "amount_usdt": "25",
                    "reason": "Needs wallet",
                    "operation_id": "admin_invest_op_000010",
                    "confirm": "OPEN_INVESTMENT",
                },
            )
            assert no_wallet.status_code == 422
            assert "wallet" in no_wallet.json()["detail"].lower()
    finally:
        await repository.close()
