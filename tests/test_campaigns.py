import calendar
import time

import pytest

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.models import TransferEvent
from delta_backend.repository import (
    DeltaRepository,
    RepositoryError,
    compute_next_run_at,
)
from delta_backend.services.campaigns import CampaignService

WALLET_ONE = "0x0000000000000000000000000000000000000001"
WALLET_TWO = "0x0000000000000000000000000000000000000002"


def _utc(year, month, day, hour=0, minute=0) -> int:
    return calendar.timegm((year, month, day, hour, minute, 0, 0, 0, 0))


async def _repo(tmp_path) -> DeltaRepository:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    return repo


async def _pay(repo, user_id, amount, log_index, promo_code=None):
    await repo.set_wallet(user_id, WALLET_ONE)
    invoice = await repo.create_invoice(
        user_id, usdt_to_minor(amount), promo_code=promo_code
    )
    result = await repo.apply_transfer(
        TransferEvent(
            chain_id=97,
            tx_hash=f"0x{log_index:064x}",
            log_index=log_index,
            block_number=100 + log_index,
            from_address=WALLET_TWO,
            to_address=WALLET_ONE,
            amount_atomic=int(invoice["exact_minor"]) * 10**12,
            amount_minor=int(invoice["exact_minor"]),
        )
    )
    assert result["matched"] is True
    return int(result["deposit_id"])


async def _fetch_all(repo, sql, params=()):
    connection = repo._connection()
    async with repo._lock:
        cursor = await connection.execute(sql, params)
        return [dict(row) for row in await cursor.fetchall()]


async def _percent_promo(repo, code, owner, *, bonus_bps=1000, max_redemptions=50):
    return await repo.admin_create_promo_code(
        code=code,
        bonus_type="percent",
        bonus_bps=bonus_bps,
        bonus_fixed_minor=0,
        max_redemptions=max_redemptions,
        min_deposit_minor=0,
        valid_from=None,
        valid_until=None,
        enabled=True,
        created_by=owner,
    )


async def test_interval_campaign_creates_broadcast(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        await repo.ensure_user(2, "alice", "Alice", "ru")
        await repo.ensure_user(3, "bob", "Bob", "en")

        now = int(time.time())
        campaign = await repo.admin_create_campaign(
            kind="custom",
            audience="all",
            schedule_mode="interval",
            interval_hours=24,
            message_html="<b>Hello</b>",
            created_by=1,
            next_run_at=now - 60,
        )

        due = await repo.claim_due_campaigns(now)
        assert [int(row["id"]) for row in due] == [int(campaign["id"])]
        assert int(due[0]["next_run_at"]) == now + 24 * 3600

        result = await repo.dispatch_campaign(int(campaign["id"]))
        assert result["status"] == "sent"
        assert result["broadcast_id"]

        broadcasts = await repo.admin_broadcasts()
        assert len(broadcasts) == 1
        assert broadcasts[0]["audience"] == "all"
        assert broadcasts[0]["message"] == "<b>Hello</b>"
        assert int(broadcasts[0]["total_count"]) == 3

        stored = await repo.admin_list_campaigns()
        assert int(stored[0]["last_sent_at"]) >= now
        assert int(stored[0]["next_run_at"]) == now + 24 * 3600
    finally:
        await repo.close()


async def test_promo_campaign_skips_when_code_exhausted(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        await repo.ensure_user(2, "alice", "Alice", "ru")
        promo = await _percent_promo(repo, "ONCE", 1, max_redemptions=1)
        await _pay(repo, 2, "100", 1, promo_code="ONCE")
        assert int((await repo.get_promo_by_code("ONCE"))["redemption_count"]) == 1

        now = int(time.time())
        campaign = await repo.admin_create_campaign(
            kind="promo",
            audience="all",
            schedule_mode="interval",
            interval_hours=24,
            message_html="Code {{code}} gives {{bonus_label}}",
            promo_code_id=int(promo["id"]),
            created_by=1,
            next_run_at=now - 60,
        )

        result = await repo.dispatch_campaign(int(campaign["id"]))
        assert result["status"] == "skipped"
        assert result["reason"] == "promo_cap_reached"
        assert result["broadcast_id"] is None

        assert await repo.admin_broadcasts() == []
        skips = await _fetch_all(
            repo,
            "SELECT details FROM audit_events WHERE event_type = 'campaign_skipped'",
        )
        assert len(skips) == 1
        assert "reason=promo_cap_reached" in skips[0]["details"]

        stored = await repo.admin_list_campaigns()
        assert stored[0]["last_sent_at"] is None
    finally:
        await repo.close()


async def test_promo_campaign_renders_placeholders(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        percent = await _percent_promo(repo, "PLUS10", 1, bonus_bps=1000)
        fixed = await repo.admin_create_promo_code(
            code="PLUS5USDT",
            bonus_type="fixed",
            bonus_bps=0,
            bonus_fixed_minor=usdt_to_minor("5"),
            max_redemptions=10,
            min_deposit_minor=0,
            valid_from=None,
            valid_until=None,
            enabled=True,
            created_by=1,
        )
        now = int(time.time())
        for promo, expected in ((percent, "10%"), (fixed, "5 USDT")):
            campaign = await repo.admin_create_campaign(
                kind="promo",
                audience="all",
                schedule_mode="interval",
                interval_hours=24,
                message_html="Use <b>{{code}}</b> for {{bonus_label}}",
                promo_code_id=int(promo["id"]),
                created_by=1,
                next_run_at=now - 60,
            )
            result = await repo.dispatch_campaign(int(campaign["id"]))
            assert result["status"] == "sent"
            message = str(
                next(
                    row
                    for row in await repo.admin_broadcasts()
                    if int(row["id"]) == int(result["broadcast_id"])
                )["message"]
            )
            assert f"<b>{promo['code']}</b>" in message
            assert f"for {expected}" in message
            assert "{{" not in message
    finally:
        await repo.close()


async def test_promo_campaign_skips_when_code_disabled(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        promo = await _percent_promo(repo, "OFFLINE", 1)
        await repo.admin_update_promo_code(int(promo["id"]), enabled=False)
        now = int(time.time())
        campaign = await repo.admin_create_campaign(
            kind="promo",
            audience="all",
            schedule_mode="interval",
            interval_hours=6,
            message_html="{{code}}",
            promo_code_id=int(promo["id"]),
            created_by=1,
            next_run_at=now - 1,
        )
        result = await repo.dispatch_campaign(int(campaign["id"]))
        assert result["status"] == "skipped"
        assert result["reason"] == "promo_disabled"
        assert await repo.admin_broadcasts() == []
    finally:
        await repo.close()


async def test_promo_campaign_skips_when_code_expired(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        now = int(time.time())
        promo = await _percent_promo(repo, "PAST", 1)
        await repo.admin_update_promo_code(int(promo["id"]), valid_until=now - 3600)
        campaign = await repo.admin_create_campaign(
            kind="promo",
            audience="all",
            schedule_mode="interval",
            interval_hours=6,
            message_html="{{code}}",
            promo_code_id=int(promo["id"]),
            created_by=1,
            next_run_at=now - 1,
        )
        result = await repo.dispatch_campaign(int(campaign["id"]))
        assert result["status"] == "skipped"
        assert result["reason"] == "promo_expired"
    finally:
        await repo.close()


def test_compute_next_run_at_interval() -> None:
    campaign = {"schedule_mode": "interval", "interval_hours": 6}
    assert compute_next_run_at(campaign, 1_000) == 1_000 + 6 * 3600
    # A zero/negative interval must never produce a tight worker loop.
    assert compute_next_run_at({"schedule_mode": "interval", "interval_hours": 0}, 0) == 3600


def test_compute_next_run_at_weekly_uses_utc_weekdays() -> None:
    # 2026-09-09 is a Wednesday (weekday 2); campaign runs Mon and Thu 09:30 UTC.
    campaign = {
        "schedule_mode": "weekly",
        "weekdays_json": "[0, 3]",
        "time_utc": "09:30",
    }
    assert compute_next_run_at(campaign, _utc(2026, 9, 9, 12)) == _utc(2026, 9, 10, 9, 30)
    assert compute_next_run_at(campaign, _utc(2026, 9, 10, 9)) == _utc(2026, 9, 10, 9, 30)
    # Exactly on the slot must advance to the next weekday, never repeat.
    assert compute_next_run_at(campaign, _utc(2026, 9, 10, 9, 30)) == _utc(2026, 9, 14, 9, 30)
    assert compute_next_run_at(campaign, _utc(2026, 9, 14, 10)) == _utc(2026, 9, 17, 9, 30)


async def test_weekly_campaign_advances_to_next_slot(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        await repo.ensure_user(2, "alice", "Alice", "ru")
        now = _utc(2026, 9, 9, 12)
        campaign = await repo.admin_create_campaign(
            kind="partner",
            audience="all",
            schedule_mode="weekly",
            weekdays=[3],
            time_utc="09:30",
            message_html="Partner program",
            created_by=1,
            next_run_at=now - 60,
        )
        assert campaign["weekdays"] == [3]

        due = await repo.claim_due_campaigns(now)
        assert len(due) == 1
        assert int(due[0]["next_run_at"]) == _utc(2026, 9, 10, 9, 30)
        assert await repo.claim_due_campaigns(now) == []
    finally:
        await repo.close()


async def test_claim_due_campaigns_filters_disabled_and_future(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        now = int(time.time())
        disabled = await repo.admin_create_campaign(
            kind="custom",
            audience="all",
            schedule_mode="interval",
            interval_hours=1,
            message_html="off",
            created_by=1,
            enabled=False,
            next_run_at=now - 60,
        )
        future = await repo.admin_create_campaign(
            kind="custom",
            audience="all",
            schedule_mode="interval",
            interval_hours=1,
            message_html="later",
            created_by=1,
            next_run_at=now + 3600,
        )
        due = await repo.admin_create_campaign(
            kind="custom",
            audience="investors",
            schedule_mode="interval",
            interval_hours=1,
            message_html="now",
            created_by=1,
            next_run_at=now - 1,
        )

        claimed = await repo.claim_due_campaigns(now)
        assert [int(row["id"]) for row in claimed] == [int(due["id"])]

        result = await repo.dispatch_campaign(int(disabled["id"]))
        assert result["status"] == "skipped"
        assert result["reason"] == "campaign_disabled"
        forced = await repo.dispatch_campaign(int(disabled["id"]), force=True)
        assert forced["status"] == "sent"

        assert int(future["next_run_at"]) == now + 3600
        with pytest.raises(RepositoryError):
            await repo.dispatch_campaign(999_999)
    finally:
        await repo.close()


async def test_reenable_campaign_with_past_slot_reschedules(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        now = int(time.time())

        weekly = await repo.admin_create_campaign(
            kind="custom",
            audience="all",
            schedule_mode="weekly",
            weekdays=[3],
            time_utc="09:30",
            message_html="weekly",
            created_by=1,
            enabled=False,
            next_run_at=now - 3600,
        )
        updated_weekly = await repo.admin_update_campaign(int(weekly["id"]), enabled=True)
        assert int(updated_weekly["next_run_at"]) > now
        assert bool(updated_weekly["enabled"]) is True

        interval = await repo.admin_create_campaign(
            kind="custom",
            audience="all",
            schedule_mode="interval",
            interval_hours=6,
            message_html="interval",
            created_by=1,
            enabled=False,
            next_run_at=now - 3600,
        )
        updated_interval = await repo.admin_update_campaign(int(interval["id"]), enabled=True)
        assert int(updated_interval["next_run_at"]) > now
        assert bool(updated_interval["enabled"]) is True

        # A campaign whose slot is still in the future must not be touched.
        future = await repo.admin_create_campaign(
            kind="custom",
            audience="all",
            schedule_mode="interval",
            interval_hours=6,
            message_html="future",
            created_by=1,
            enabled=False,
            next_run_at=now + 3600,
        )
        updated_future = await repo.admin_update_campaign(int(future["id"]), enabled=True)
        assert int(updated_future["next_run_at"]) == now + 3600
    finally:
        await repo.close()


async def test_campaign_service_tick_counts_only_sent(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        await repo.ensure_user(2, "alice", "Alice", "ru")
        promo = await _percent_promo(repo, "GONE", 1, max_redemptions=1)
        await _pay(repo, 2, "100", 1, promo_code="GONE")

        now = int(time.time())
        await repo.admin_create_campaign(
            kind="custom",
            audience="all",
            schedule_mode="interval",
            interval_hours=12,
            message_html="Hi",
            created_by=1,
            next_run_at=now - 5,
        )
        await repo.admin_create_campaign(
            kind="promo",
            audience="all",
            schedule_mode="interval",
            interval_hours=12,
            message_html="{{code}}",
            promo_code_id=int(promo["id"]),
            created_by=1,
            next_run_at=now - 5,
        )

        service = CampaignService(repo, interval_seconds=0.01)
        assert await service.tick() == 1
        assert len(await repo.admin_broadcasts()) == 1
        # Both campaigns were claimed, so a second tick has nothing due.
        assert await service.tick() == 0
    finally:
        await repo.close()


async def test_campaign_crud_validation_and_update(tmp_path) -> None:
    repo = await _repo(tmp_path)
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        promo = await _percent_promo(repo, "VALID", 1)

        with pytest.raises(RepositoryError):
            await repo.admin_create_campaign(
                kind="promo",
                audience="all",
                schedule_mode="interval",
                message_html="no promo id",
                created_by=1,
            )
        with pytest.raises(RepositoryError):
            await repo.admin_create_campaign(
                kind="custom",
                audience="everyone",
                schedule_mode="interval",
                message_html="bad audience",
                created_by=1,
            )
        with pytest.raises(RepositoryError):
            await repo.admin_create_campaign(
                kind="custom",
                audience="all",
                schedule_mode="weekly",
                weekdays=[],
                message_html="no weekdays",
                created_by=1,
            )
        with pytest.raises(RepositoryError):
            await repo.admin_create_campaign(
                kind="custom",
                audience="all",
                schedule_mode="weekly",
                weekdays=[9],
                message_html="bad weekday",
                created_by=1,
            )
        with pytest.raises(RepositoryError):
            await repo.admin_create_campaign(
                kind="custom",
                audience="all",
                schedule_mode="weekly",
                weekdays=[1],
                time_utc="24:00",
                message_html="bad time",
                created_by=1,
            )
        with pytest.raises(RepositoryError):
            await repo.admin_create_campaign(
                kind="custom",
                audience="all",
                schedule_mode="interval",
                message_html="   ",
                created_by=1,
            )
        with pytest.raises(RepositoryError):
            await repo.admin_create_campaign(
                kind="promo",
                audience="all",
                schedule_mode="interval",
                message_html="missing promo",
                promo_code_id=999_999,
                created_by=1,
            )

        created = await repo.admin_create_campaign(
            kind="custom",
            audience="all",
            schedule_mode="interval",
            interval_hours=48,
            message_html="Hello",
            created_by=1,
        )
        # Without an explicit next_run_at the first send waits one full interval.
        assert int(created["next_run_at"]) >= int(time.time()) + 48 * 3600 - 5
        assert created["enabled"] is True

        updated = await repo.admin_update_campaign(
            int(created["id"]),
            kind="promo",
            promo_code_id=int(promo["id"]),
            schedule_mode="weekly",
            weekdays=[6, 0, 0],
            time_utc="7:05",
            enabled=False,
        )
        assert updated["kind"] == "promo"
        assert updated["weekdays"] == [0, 6]
        assert updated["time_utc"] == "07:05"
        assert updated["enabled"] is False
        # Switching schedule mode must re-derive the pending slot.
        slot = time.gmtime(int(updated["next_run_at"]))
        assert slot.tm_wday in (0, 6)
        assert (slot.tm_hour, slot.tm_min) == (7, 5)

        with pytest.raises(RepositoryError):
            await repo.admin_update_campaign(int(created["id"]), promo_code_id=None)
        with pytest.raises(RepositoryError):
            await repo.admin_update_campaign(int(created["id"]), mystery=1)
        with pytest.raises(RepositoryError):
            await repo.admin_update_campaign(999_999, enabled=True)
    finally:
        await repo.close()
