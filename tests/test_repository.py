import time

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.models import TransferEvent
from delta_backend.repository import DeltaRepository


WALLET_ONE = "0x0000000000000000000000000000000000000001"
WALLET_TWO = "0x0000000000000000000000000000000000000002"


async def pay_invoice(repository: DeltaRepository, user_id: int, amount: str, log_index: int) -> int:
    invoice = await repository.create_invoice(user_id, usdt_to_minor(amount))
    exact = int(invoice["exact_minor"])
    result = await repository.apply_transfer(
        TransferEvent(
            chain_id=97,
            tx_hash=f"0x{log_index:064x}",
            log_index=log_index,
            block_number=100 + log_index,
            from_address=WALLET_TWO,
            to_address=WALLET_ONE,
            amount_atomic=exact * 10**12,
            amount_minor=exact,
        )
    )
    assert result["matched"] is True
    return int(result["deposit_id"])


async def deposit_principal_minor(repository: DeltaRepository, deposit_id: int) -> int:
    connection = repository._connection()
    async with repository._lock:
        cursor = await connection.execute(
            "SELECT principal_minor FROM deposits WHERE id = ?",
            (deposit_id,),
        )
        row = await cursor.fetchone()
    assert row is not None
    return int(row["principal_minor"])


async def test_deposit_and_referral_payouts_are_idempotent(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "delta.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(1, "leader", "Leader", "ru")
        await repository.set_wallet(1, WALLET_ONE)
        await repository.ensure_user(2, "partner", "Partner", "ru", referrer_id=1)
        await repository.set_wallet(2, WALLET_TWO)

        await pay_invoice(repository, 1, "50", 1)
        referred_deposit = await pay_invoice(repository, 2, "100", 2)

        async with repository.transaction() as connection:
            await connection.execute(
                "UPDATE deposits SET next_payout_at = ?",
                (int(time.time()) - 1,),
            )

        scheduled = await repository.schedule_due_payouts()
        assert scheduled == 2

        connection = repository._connection()
        async with repository._lock:
            # Since V8 referral rewards accrue to the referrer's balance and are
            # withdrawn on demand; nothing is queued directly into payouts.
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM referral_accruals "
                "WHERE referrer_id = 1 AND source_deposit_id = ? AND level = 1",
                (referred_deposit,),
            )
            assert int((await cursor.fetchone())["value"]) == 1
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM payouts WHERE kind = 'referral' "
                "AND source_deposit_id = ?",
                (referred_deposit,),
            )
            assert int((await cursor.fetchone())["value"]) == 0

        assert await repository.schedule_due_payouts() == 0

        async with repository._lock:
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM referral_accruals WHERE source_deposit_id = ?",
                (referred_deposit,),
            )
            assert int((await cursor.fetchone())["value"]) == 1
    finally:
        await repository.close()


async def test_invoice_idempotency_and_pending_limit(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "delta.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(10, "member", "Member", "ru")
        await repository.set_wallet(10, WALLET_ONE)

        first = await repository.create_invoice(
            10,
            usdt_to_minor("100"),
            "invoice-test-0001",
        )
        repeated = await repository.create_invoice(
            10,
            usdt_to_minor("100"),
            "invoice-test-0001",
        )
        assert repeated["invoice_id"] == first["invoice_id"]
        assert repeated["exact_minor"] == first["exact_minor"]
        assert repeated["reused"] is True
    finally:
        await repository.close()


async def test_blocking_and_broadcast_queue(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "delta.sqlite3", business)
    await repository.connect()
    try:
        await repository.ensure_user(20, "admin", "Admin", "ru")
        await repository.ensure_user(21, "active", "Active", "ru")
        await repository.ensure_user(22, "blocked", "Blocked", "ru")
        assert await repository.set_user_blocked(22, True) is True

        broadcast = await repository.create_broadcast(20, "Test message", "all")
        assert broadcast["total_count"] == 2

        first = await repository.claim_next_broadcast_delivery()
        assert first is not None
        await repository.finish_broadcast_delivery(int(first["id"]), delivered=True)
        second = await repository.claim_next_broadcast_delivery()
        assert second is not None
        await repository.finish_broadcast_delivery(int(second["id"]), delivered=True)
        assert await repository.claim_next_broadcast_delivery() is None

        rows = await repository.admin_broadcasts()
        assert rows[0]["status"] == "completed"
        assert rows[0]["delivered_count"] == 2
    finally:
        await repository.close()


async def test_admin_referral_controls_are_audited_and_withdrawable(tmp_path) -> None:
    repository = DeltaRepository(tmp_path / "delta.sqlite3", MiniAppSettings(_env_file=None))
    await repository.connect()
    try:
        await repository.ensure_user(30, "admin", "Admin", "ru")
        await repository.ensure_user(31, "partner", "Partner", "ru")
        await repository.set_wallet(31, WALLET_ONE)

        changed = await repository.admin_set_referral_balance(
            31, usdt_to_minor("12.5"), 30, "Manual partner credit", "repo-ref-bal-0001"
        )
        assert changed["new_balance_minor"] == usdt_to_minor("12.5")
        level = await repository.admin_set_referral_level(
            31, 4, 30, "Campaign access", "repo-ref-lvl-0001"
        )
        assert level["unlocked_level"] == 4
        team = await repository.team(31)
        assert team["stats"]["available_minor"] == usdt_to_minor("12.5")
        assert team["stats"]["manual_level"] == 4
        assert team["stats"]["current_level"] == 4

        payout = await repository.request_referral_withdrawal(31, "manual-balance-withdrawal")
        assert payout["amount_minor"] == usdt_to_minor("12.5")
        assert (await repository.team(31))["stats"]["available_minor"] == 0

        detail = await repository.admin_user_detail(31)
        assert detail is not None
        assert detail["referral_balance_adjustments"]
        assert detail["referral_level_adjustments"]
        assert detail["referral_level_override"]["unlocked_level"] == 4
    finally:
        await repository.close()


async def test_admin_investment_is_idempotent_and_due_after_24_hours(tmp_path) -> None:
    repository = DeltaRepository(tmp_path / "delta.sqlite3", MiniAppSettings(_env_file=None))
    await repository.connect()
    try:
        await repository.ensure_user(40, "admin", "Admin", "ru")
        await repository.ensure_user(41, "investor", "Investor", "ru")
        await repository.set_wallet(41, WALLET_TWO)
        before = int(time.time())
        first = await repository.admin_open_investment(
            41, usdt_to_minor("75"), 40, "Manual investment", "test_operation_00000001"
        )
        repeated = await repository.admin_open_investment(
            41, usdt_to_minor("75"), 40, "Manual investment", "test_operation_00000001"
        )
        assert first["id"] == repeated["id"]
        assert repeated["reused"] is True
        assert first["status"] == "active"
        assert int(first["next_payout_at"]) >= before + 86_400
        assert await repository.schedule_due_payouts() == 0

        detail = await repository.admin_user_detail(41)
        assert detail is not None
        created = next(row for row in detail["deposits"] if row["id"] == first["id"])
        assert created["source"] == "admin"
        notifications = await repository.list_notifications(41)
        assert any(row["event_type"] == "admin_investment_opened" for row in notifications["items"])
    finally:
        await repository.close()


async def test_admin_close_investment_cancels_queued_payouts(tmp_path) -> None:
    repository = DeltaRepository(tmp_path / "delta.sqlite3", MiniAppSettings(_env_file=None))
    await repository.connect()
    try:
        await repository.ensure_user(50, "admin", "Admin", "ru")
        await repository.ensure_user(51, "investor", "Investor", "ru")
        await repository.set_wallet(51, WALLET_TWO)
        opened = await repository.admin_open_investment(
            51, usdt_to_minor("100"), 50, "Open for close test", "close_op_open_000001"
        )
        # Force the deposit due so a queued daily payout exists.
        connection = repository._connection()
        await connection.execute(
            "UPDATE deposits SET next_payout_at = 0 WHERE id = ?",
            (opened["id"],),
        )
        await connection.commit()
        assert await repository.schedule_due_payouts() == 1

        closed = await repository.admin_close_investment(
            51, int(opened["id"]), 50, "Owner test reset", "close_op_close_000001"
        )
        repeated = await repository.admin_close_investment(
            51, int(opened["id"]), 50, "Owner test reset", "close_op_close_000001"
        )
        assert closed["status"] == "completed"
        assert closed["cancelled_payouts"] >= 1
        assert repeated["reused"] is True
        assert await repository.schedule_due_payouts() == 0

        detail = await repository.admin_user_detail(51)
        assert detail is not None
        assert int(detail["stats"]["active_minor"] or 0) == 0
        notifications = await repository.list_notifications(51)
        assert any(row["event_type"] == "admin_investment_closed" for row in notifications["items"])
    finally:
        await repository.close()


async def test_connect_rebrands_durable_notifications(tmp_path) -> None:
    database_path = tmp_path / "delta.sqlite3"
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(database_path, business)
    await repository.connect()
    retired = "G" + "FORT"
    try:
        await repository.ensure_user(61, "member", "Member", "ru")
        async with repository.transaction() as connection:
            await repository._queue_notification(
                connection,
                user_id=61,
                category="system",
                event_type="legacy_brand_fixture",
                title=retired,
                body=f"Открыть {retired}",
                telegram_html=f"<b>{retired}</b>",
                dedupe_key="legacy-brand-fixture",
            )
    finally:
        await repository.close()

    repository = DeltaRepository(database_path, business)
    await repository.connect()
    try:
        notifications = await repository.list_notifications(61)
        item = notifications["items"][0]
        assert item["title"] == "NOVERA"
        assert item["body"] == "Открыть NOVERA"
        # API payload intentionally omits telegram_html; verify durable storage.
        async with repository._lock:
            cursor = await repository._connection().execute(
                "SELECT telegram_html FROM user_notifications WHERE id = ?",
                (int(item["id"]),),
            )
            stored = await cursor.fetchone()
        assert stored is not None
        assert retired not in str(stored["telegram_html"])
        assert "NOVERA" in str(stored["telegram_html"])
    finally:
        await repository.close()


async def test_admin_user_detail_includes_partner_turnovers(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "delta.sqlite3", business)
    await repository.connect()
    try:
        # Tree: leader(10)
        #   ├─ alice(11) personal 100; her L1 bob(12) deposits 40 → alice structure 40
        #   └─ carol(13) personal 25; no downline → structure 0
        await repository.ensure_user(10, "leader", "Leader", "ru")
        await repository.set_wallet(10, WALLET_ONE)
        await repository.ensure_user(11, "alice", "Alice", "ru", referrer_id=10)
        await repository.set_wallet(11, WALLET_TWO)
        await repository.ensure_user(12, "bob", "Bob", "ru", referrer_id=11)
        await repository.set_wallet(12, "0x0000000000000000000000000000000000000003")
        await repository.ensure_user(13, "carol", "Carol", "ru", referrer_id=10)
        await repository.set_wallet(13, "0x0000000000000000000000000000000000000004")

        alice_deposit_id = await pay_invoice(repository, 11, "100", 11)
        bob_deposit_id = await pay_invoice(repository, 12, "40", 12)
        carol_deposit_id = await pay_invoice(repository, 13, "25", 13)
        # Invoice amounts get a small anti-collision jitter (create_invoice), so
        # compare against the actually recorded deposit principals rather than
        # the nominal usdt_to_minor("...") values.
        alice_personal_minor = await deposit_principal_minor(repository, alice_deposit_id)
        bob_personal_minor = await deposit_principal_minor(repository, bob_deposit_id)
        carol_personal_minor = await deposit_principal_minor(repository, carol_deposit_id)

        detail = await repository.admin_user_detail(10)
        assert "partner_stats" in detail
        stats = detail["partner_stats"]
        assert int(stats["team_count"]) >= 2
        assert "earned_minor" in stats
        assert "available_minor" in stats
        assert "line_minor" in stats
        assert "current_level" in stats

        partners = {int(p["telegram_id"]): p for p in detail["partners"]}
        assert set(partners) == {11, 13}

        alice = partners[11]
        assert int(alice["personal_turnover_minor"]) == alice_personal_minor
        assert int(alice["structure_turnover_minor"]) == bob_personal_minor
        assert int(alice["structure_member_count"]) == 1
        # Partner's own deposit must not inflate structure turnover
        assert int(alice["structure_turnover_minor"]) != int(alice["personal_turnover_minor"])

        carol = partners[13]
        assert int(carol["personal_turnover_minor"]) == carol_personal_minor
        assert int(carol["structure_turnover_minor"]) == 0
        assert int(carol["structure_member_count"]) == 0

        ordered_ids = [int(p["telegram_id"]) for p in detail["partners"]]
        assert ordered_ids[0] == 11  # higher structure turnover first
    finally:
        await repository.close()
