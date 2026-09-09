"""API tests for the admin campaigns HTTP surface (Task 5).

Follows the auth fixture pattern from tests/test_broadcast_api.py and
tests/test_promo_api.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
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
    )
    repository = DeltaRepository(tmp_path / "campaigns_api.sqlite3", business)
    await repository.connect()
    await repository.ensure_user(ADMIN_ID, "admin_user", "Admin", "ru")
    await repository.ensure_user(USER_ID, "member", "Member", "ru")

    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.rate_limiter = SlidingWindowRateLimiter()
    # The FastAPI app is a shared module-level singleton across test files.
    # Other suites leave a non-active ChainSetupRuntime on app.state; clear it
    # so it does not leak into these requests.
    app.state.chain_setup = None
    return repository


@pytest.mark.asyncio
async def test_admin_campaign_routes_reject_non_admin(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data(user_id=USER_ID, username="member")}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            assert (await client.get("/api/admin/campaigns", headers=headers)).status_code == 403
            assert (
                await client.post(
                    "/api/admin/campaigns",
                    headers=headers,
                    json={
                        "kind": "custom",
                        "audience": "all",
                        "schedule_mode": "interval",
                        "interval_hours": 24,
                        "message_html": "<b>Hi</b>",
                    },
                )
            ).status_code == 403
            assert (
                await client.patch(
                    "/api/admin/campaigns/1", headers=headers, json={"enabled": False}
                )
            ).status_code == 403
            assert (
                await client.post("/api/admin/campaigns/1/run", headers=headers)
            ).status_code == 403
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_admin_can_create_list_patch_campaign(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data()}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            created = await client.post(
                "/api/admin/campaigns",
                headers=headers,
                json={
                    "kind": "custom",
                    "audience": "all",
                    "schedule_mode": "interval",
                    "interval_hours": 24,
                    "message_html": "<b>Hello</b><div>drop me</div>",
                },
            )
            assert created.status_code == 200
            body = created.json()
            # sanitize_telegram_html must run before persisting: the disallowed
            # <div> tag is stripped but its text content survives.
            assert body["message_html"] == "<b>Hello</b>drop me"
            assert body["enabled"] is True
            campaign_id = int(body["id"])

            listing = await client.get("/api/admin/campaigns", headers=headers)
            assert listing.status_code == 200
            assert any(int(item["id"]) == campaign_id for item in listing.json())

            # Missing message -> 422.
            blank = await client.post(
                "/api/admin/campaigns",
                headers=headers,
                json={
                    "kind": "custom",
                    "audience": "all",
                    "schedule_mode": "interval",
                    "interval_hours": 24,
                    "message_html": "   ",
                },
            )
            assert blank.status_code == 422

            # Unknown promo code -> 404.
            missing_promo = await client.post(
                "/api/admin/campaigns",
                headers=headers,
                json={
                    "kind": "promo",
                    "audience": "all",
                    "schedule_mode": "interval",
                    "interval_hours": 24,
                    "message_html": "{{code}}",
                    "promo_code_id": 999999,
                },
            )
            assert missing_promo.status_code == 404

            patched = await client.patch(
                f"/api/admin/campaigns/{campaign_id}",
                headers=headers,
                json={"enabled": False, "message_html": "<b>Updated</b><script>x</script>"},
            )
            assert patched.status_code == 200
            patched_body = patched.json()
            assert patched_body["enabled"] is False
            assert patched_body["message_html"] == "<b>Updated</b>x"

            missing_patch = await client.patch(
                "/api/admin/campaigns/999999", headers=headers, json={"enabled": True}
            )
            assert missing_patch.status_code == 404
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_run_campaign_dispatches_and_advances_next_run_at(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data()}
    try:
        now = int(time.time())
        campaign = await repository.admin_create_campaign(
            kind="custom",
            audience="all",
            schedule_mode="interval",
            interval_hours=24,
            message_html="Hello",
            created_by=ADMIN_ID,
            enabled=False,
            next_run_at=now - 60,
        )
        campaign_id = int(campaign["id"])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post(
                f"/api/admin/campaigns/{campaign_id}/run", headers=headers
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "sent"
            assert body["broadcast_id"]

            # IMPORTANT: a forced run must advance next_run_at past "now",
            # otherwise the background scheduler would claim the still-due
            # slot on its next tick and send the same campaign a second time.
            stored = (await client.get("/api/admin/campaigns", headers=headers)).json()
            row = next(item for item in stored if int(item["id"]) == campaign_id)
            assert int(row["next_run_at"]) > now

            missing = await client.post(
                "/api/admin/campaigns/999999/run", headers=headers
            )
            assert missing.status_code == 404
    finally:
        await repository.close()
