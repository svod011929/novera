import asyncio
import hashlib
import html
import json
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from .amounts import MINOR_FACTOR, bps_to_percent_text, calculate_bps, minor_to_text
from .api_settings import MiniAppSettings
from .deposit_mismatch import (
    MISMATCH_LOOKAHEAD_AFTER_EXPIRY_SECONDS,
    MISMATCH_LOOKBACK_SECONDS,
    select_mismatch_candidate,
)
from .models import TransferEvent
from .telegram_auth import TelegramUser
# NOVERA admin inviter management
# NOVERA real admin treasury test payouts
# NOVERA durable Telegram + in-app user notifications
# NOVERA production safety state + payout telemetry
# NOVERA audited admin financial and partner controls


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'ru',
    payout_address TEXT,
    referrer_id INTEGER REFERENCES users(telegram_id),
    blocked INTEGER NOT NULL DEFAULT 0 CHECK (blocked IN (0, 1)),
    manual_balance_minor INTEGER NOT NULL DEFAULT 0 CHECK (manual_balance_minor >= 0),
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    CHECK (referrer_id IS NULL OR referrer_id <> telegram_id)
);

CREATE INDEX IF NOT EXISTS idx_users_referrer ON users(referrer_id);

CREATE TABLE IF NOT EXISTS admin_grants (
    telegram_id INTEGER PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    granted_by INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS web_login_tokens (
    token_hash TEXT PRIMARY KEY,
    telegram_id INTEGER NOT NULL,
    username TEXT,
    first_name TEXT NOT NULL DEFAULT '',
    language TEXT,
    start_param TEXT,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_web_login_tokens_expiry
ON web_login_tokens(expires_at);

CREATE TABLE IF NOT EXISTS deposit_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id),
    idempotency_key TEXT,
    base_minor INTEGER NOT NULL CHECK (base_minor > 0),
    exact_minor INTEGER NOT NULL CHECK (exact_minor >= base_minor),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'expired')),
    expires_at INTEGER NOT NULL,
    tx_hash TEXT,
    created_at INTEGER NOT NULL,
    paid_at INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_invoice_amount
ON deposit_invoices(exact_minor) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS chain_deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id INTEGER NOT NULL,
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    block_number INTEGER NOT NULL,
    from_address TEXT NOT NULL,
    to_address TEXT NOT NULL,
    amount_atomic TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    invoice_id INTEGER REFERENCES deposit_invoices(id),
    matched INTEGER NOT NULL DEFAULT 0 CHECK (matched IN (0, 1)),
    created_at INTEGER NOT NULL,
    UNIQUE(chain_id, tx_hash, log_index)
);

CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id),
    invoice_id INTEGER NOT NULL UNIQUE REFERENCES deposit_invoices(id),
    principal_minor INTEGER NOT NULL CHECK (principal_minor > 0),
    payout_address TEXT NOT NULL,
    paid_days INTEGER NOT NULL DEFAULT 0 CHECK (paid_days BETWEEN 0 AND 20),
    scheduled_days INTEGER NOT NULL DEFAULT 0 CHECK (scheduled_days BETWEEN 0 AND 20),
    next_payout_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'paused', 'failed')),
    opened_at INTEGER NOT NULL,
    completed_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_deposits_due
ON deposits(status, next_payout_at, scheduled_days);
CREATE INDEX IF NOT EXISTS idx_deposits_user
ON deposits(user_id, opened_at DESC);

CREATE TABLE IF NOT EXISTS payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id),
    source_deposit_id INTEGER REFERENCES deposits(id),
    kind TEXT NOT NULL CHECK (kind IN ('daily', 'referral')),
    subtype TEXT NOT NULL DEFAULT '' CHECK (subtype IN ('', 'principal')),
    payout_day INTEGER,
    referral_level INTEGER,
    admin_test INTEGER NOT NULL DEFAULT 0 CHECK (admin_test IN (0, 1)),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    address TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'signed', 'broadcast', 'confirmed', 'failed')),
    tx_hash TEXT,
    raw_transaction TEXT,
    nonce INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    status_changed_at INTEGER,
    confirmed_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_payouts_work ON payouts(status, id);
CREATE INDEX IF NOT EXISTS idx_payouts_user ON payouts(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS referral_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL REFERENCES users(telegram_id),
    referred_id INTEGER NOT NULL REFERENCES users(telegram_id),
    source_deposit_id INTEGER NOT NULL REFERENCES deposits(id),
    source_payout_day INTEGER NOT NULL,
    level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
    percent_bps INTEGER NOT NULL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    payout_id INTEGER NOT NULL UNIQUE REFERENCES payouts(id),
    created_at INTEGER NOT NULL,
    UNIQUE(source_deposit_id, source_payout_day, level)
);

CREATE TABLE IF NOT EXISTS referral_accruals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL REFERENCES users(telegram_id),
    referred_id INTEGER NOT NULL REFERENCES users(telegram_id),
    source_deposit_id INTEGER NOT NULL REFERENCES deposits(id),
    source_payout_day INTEGER NOT NULL,
    level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
    percent_bps INTEGER NOT NULL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    withdrawal_payout_id INTEGER REFERENCES payouts(id),
    created_at INTEGER NOT NULL,
    UNIQUE(source_deposit_id, source_payout_day, level)
);

CREATE INDEX IF NOT EXISTS idx_referral_accruals_balance
ON referral_accruals(referrer_id, withdrawal_payout_id, created_at);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS safety_state (
    key TEXT PRIMARY KEY,
    value_text TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_by INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chain_config_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    status TEXT NOT NULL DEFAULT 'bootstrap'
        CHECK (status IN ('bootstrap', 'configured', 'active', 'degraded')),
    active_generation TEXT,
    pending_generation TEXT,
    public_fingerprint TEXT,
    last_error_code TEXT,
    updated_by INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chain_config_activations (
    operation_key TEXT PRIMARY KEY,
    generation TEXT NOT NULL,
    actor_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('activated', 'failed')),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS balance_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    old_balance_minor INTEGER NOT NULL,
    new_balance_minor INTEGER NOT NULL,
    delta_minor INTEGER NOT NULL,
    reason TEXT NOT NULL,
    changed_by INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_balance_adjustments_user
ON balance_adjustments(user_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS referrer_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    old_referrer_id INTEGER REFERENCES users(telegram_id),
    new_referrer_id INTEGER REFERENCES users(telegram_id),
    changed_by INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_referrer_adjustments_user
ON referrer_adjustments(user_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS referral_balance_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    old_balance_minor INTEGER NOT NULL CHECK (old_balance_minor >= 0),
    new_balance_minor INTEGER NOT NULL CHECK (new_balance_minor >= 0),
    delta_minor INTEGER NOT NULL,
    reason TEXT NOT NULL,
    withdrawal_payout_id INTEGER REFERENCES payouts(id),
    changed_by INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_referral_balance_adjustments_user
ON referral_balance_adjustments(user_id, withdrawal_payout_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS referral_level_overrides (
    user_id INTEGER PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    unlocked_level INTEGER NOT NULL CHECK (unlocked_level BETWEEN 1 AND 5),
    reason TEXT NOT NULL,
    changed_by INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS referral_level_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    old_level INTEGER NOT NULL CHECK (old_level BETWEEN 0 AND 5),
    new_level INTEGER NOT NULL CHECK (new_level BETWEEN 0 AND 5),
    reason TEXT NOT NULL,
    changed_by INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_referral_level_adjustments_user
ON referral_level_adjustments(user_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS admin_investment_openings (
    deposit_id INTEGER PRIMARY KEY REFERENCES deposits(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    operation_key TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    opened_by INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_admin_investment_openings_user
ON admin_investment_openings(user_id, created_at DESC, deposit_id DESC);

CREATE TABLE IF NOT EXISTS admin_investment_closures (
    deposit_id INTEGER PRIMARY KEY REFERENCES deposits(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    operation_key TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    closed_by INTEGER NOT NULL,
    cancelled_payouts INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_admin_investment_closures_user
ON admin_investment_closures(user_id, created_at DESC, deposit_id DESC);

CREATE TABLE IF NOT EXISTS admin_control_idempotency (
    operation_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    actor_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_admin_control_idempotency_user
ON admin_control_idempotency(user_id, kind, created_at DESC);

CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by INTEGER NOT NULL REFERENCES users(telegram_id),
    audience TEXT NOT NULL CHECK (audience IN ('all', 'investors', 'partners')),
    message TEXT NOT NULL,
    parse_mode TEXT NOT NULL DEFAULT 'HTML',
    media_path TEXT,
    media_file_id TEXT,
    buttons_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'sending', 'completed', 'failed')),
    total_count INTEGER NOT NULL DEFAULT 0,
    delivered_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    started_at INTEGER,
    completed_at INTEGER
);

CREATE TABLE IF NOT EXISTS broadcast_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'sending', 'delivered', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    sent_at INTEGER,
    UNIQUE(broadcast_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_broadcast_delivery_queue
ON broadcast_deliveries(status, id);


CREATE TABLE IF NOT EXISTS user_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('deposit', 'payout', 'partner', 'system')),
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    telegram_html TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    dedupe_key TEXT NOT NULL UNIQUE,
    read_at INTEGER,
    telegram_status TEXT NOT NULL DEFAULT 'queued'
        CHECK (telegram_status IN ('queued', 'sending', 'delivered', 'failed')),
    telegram_attempts INTEGER NOT NULL DEFAULT 0,
    telegram_error TEXT,
    telegram_sent_at INTEGER,
    telegram_updated_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_notifications_user
ON user_notifications(user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_user_notifications_unread
ON user_notifications(user_id, read_at, id DESC);
CREATE INDEX IF NOT EXISTS idx_user_notifications_delivery
ON user_notifications(telegram_status, telegram_updated_at, id);
"""


BROADCAST_AUDIENCE_FILTERS = {
    "all": "1 = 1",
    "investors": "EXISTS (SELECT 1 FROM deposits WHERE deposits.user_id = users.telegram_id)",
    "partners": "EXISTS (SELECT 1 FROM users AS child WHERE child.referrer_id = users.telegram_id)",
}


class RepositoryError(RuntimeError):
    pass


PROMO_CODE_MAX_LENGTH = 32
PROMO_BONUS_TYPES = {"percent", "fixed"}


def compute_promo_bonus_minor(promo: dict[str, object], base_minor: int) -> int:
    kind = str(promo.get("bonus_type") or "")
    if kind == "percent":
        return (int(base_minor) * int(promo.get("bonus_bps") or 0)) // 10_000
    if kind == "fixed":
        return int(promo.get("bonus_fixed_minor") or 0)
    raise RepositoryError("Invalid promo bonus type")


CAMPAIGN_KINDS = {"promo", "partner", "custom"}
CAMPAIGN_SCHEDULE_MODES = {"interval", "weekly"}
CAMPAIGN_MESSAGE_MAX_LENGTH = 4096
CAMPAIGN_MAX_INTERVAL_HOURS = 24 * 365
CAMPAIGN_DAY_SECONDS = 86_400


def parse_campaign_weekdays(raw: object) -> list[int]:
    """Normalise a weekday selection into a sorted list of 0=Mon .. 6=Sun."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            values = json.loads(raw or "[]")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RepositoryError("weekdays must be a list of integers 0-6") from exc
    else:
        values = raw
    if not isinstance(values, list | tuple):
        raise RepositoryError("weekdays must be a list of integers 0-6")
    weekdays: set[int] = set()
    for value in values:
        if isinstance(value, bool):
            raise RepositoryError("weekdays must be a list of integers 0-6")
        try:
            day = int(value)
        except (TypeError, ValueError) as exc:
            raise RepositoryError("weekdays must be a list of integers 0-6") from exc
        if not 0 <= day <= 6:
            raise RepositoryError("weekdays must be a list of integers 0-6")
        weekdays.add(day)
    return sorted(weekdays)


def parse_campaign_time_utc(raw: object) -> tuple[int, int]:
    parts = str(raw or "").strip().split(":")
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        raise RepositoryError("time_utc must use the HH:MM format")
    hour, minute = (int(part) for part in parts)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise RepositoryError("time_utc must use the HH:MM format")
    return hour, minute


def compute_next_run_at(campaign: dict[str, object], after: int) -> int:
    after = int(after)
    mode = str(campaign.get("schedule_mode") or "")
    if mode == "interval":
        hours = max(1, int(campaign.get("interval_hours") or 0))
        return after + hours * 3600
    if mode != "weekly":
        raise RepositoryError("Unsupported campaign schedule mode")
    raw_weekdays = campaign.get("weekdays")
    if raw_weekdays is None:
        raw_weekdays = campaign.get("weekdays_json")
    weekdays = parse_campaign_weekdays(raw_weekdays)
    if not weekdays:
        raise RepositoryError("Weekly campaigns require at least one weekday")
    hour, minute = parse_campaign_time_utc(campaign.get("time_utc"))
    target = hour * 3600 + minute * 60
    midnight_utc = after - after % CAMPAIGN_DAY_SECONDS
    for offset in range(8):
        candidate = midnight_utc + offset * CAMPAIGN_DAY_SECONDS + target
        if candidate > after and time.gmtime(candidate).tm_wday in weekdays:
            return candidate
    raise RepositoryError("Weekly campaign has no reachable run slot")


def campaign_promo_bonus_label(promo: dict[str, object]) -> str:
    kind = str(promo.get("bonus_type") or "")
    if kind == "percent":
        return f"{bps_to_percent_text(int(promo.get('bonus_bps') or 0))}%"
    if kind == "fixed":
        return f"{minor_to_text(int(promo.get('bonus_fixed_minor') or 0))} USDT"
    raise RepositoryError("Invalid promo bonus type")


DEFAULT_PROMO_CAMPAIGN_MESSAGE = (
    "🎁 <b>Промокод NOVERA</b>\n\n"
    "Бонус к депозиту: <b>{{bonus_label}}</b>\n\n"
    "Ваш код:\n"
    "<code>{{code}}</code>\n\n"
    "Откройте по ссылке:\n"
    "https://t.me/{{bot_username}}?start=promo_{{code}}\n\n"
    "Или в NOVERA → <b>Пополнить</b> → вставьте промокод при создании депозита.\n"
    "Бонус увеличивает сумму депозита. Один раз на пользователя."
)


def parse_promo_start_param(start_param: str | None) -> str | None:
    """Extract a normalized promo code from ``promo_*`` / ``promo-*`` start payload.

    Referral payloads (``ref_``) and invalid bodies return ``None`` without raising.
    """
    raw = str(start_param or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower.startswith("ref_"):
        return None
    if lower.startswith("promo_"):
        body = raw[len("promo_") :]
    elif lower.startswith("promo-"):
        body = raw[len("promo-") :]
    else:
        return None
    try:
        return DeltaRepository._normalize_promo_code(body)
    except RepositoryError:
        return None

DEFAULT_PARTNER_CAMPAIGN_MESSAGE = (
    "👥 <b>NOVERA Partner Network</b>\n\n"
    "Приглашайте партнёров по своей ссылке и получайте процент с их депозитов "
    "на 5 уровнях.\n"
    "Доступ к уровням открывается по обороту 1-й линии — личный депозит "
    "не требуется.\n\n"
    "Откройте вкладку <b>Команда</b> в NOVERA и скопируйте партнёрскую ссылку."
)


def default_campaign_message(kind: str) -> str:
    if kind == "promo":
        return DEFAULT_PROMO_CAMPAIGN_MESSAGE
    if kind == "partner":
        return DEFAULT_PARTNER_CAMPAIGN_MESSAGE
    return ""


def render_campaign_message(
    message_html: str,
    promo: dict[str, object] | None,
    *,
    bot_username: str | None = None,
) -> str:
    message = str(message_html or "")
    username = str(bot_username or "").lstrip("@").strip()
    if username:
        message = message.replace("{{bot_username}}", html.escape(username))
    if promo is None:
        return message
    return message.replace(
        "{{code}}", html.escape(str(promo.get("code") or ""))
    ).replace("{{bonus_label}}", html.escape(campaign_promo_bonus_label(promo)))


def campaign_promo_skip_reason(promo: dict[str, object] | None, now: int) -> str | None:
    """Return why a promo campaign must not be sent, or ``None`` when it may run."""
    if not promo:
        return "promo_missing"
    if not promo.get("enabled"):
        return "promo_disabled"
    valid_from = promo.get("valid_from")
    if valid_from is not None and int(now) < int(valid_from):
        return "promo_not_active"
    valid_until = promo.get("valid_until")
    if valid_until is not None and int(now) > int(valid_until):
        return "promo_expired"
    if int(promo.get("redemption_count") or 0) >= int(promo.get("max_redemptions") or 0):
        return "promo_cap_reached"
    return None


class DeltaRepository:
    def __init__(self, path: Path | str, business: MiniAppSettings) -> None:
        self.path = Path(path)
        self.business = business
        self.connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA busy_timeout = 5000")
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.execute("PRAGMA synchronous = NORMAL")
        await connection.executescript(SCHEMA)
        await self._migrate(connection)
        await connection.commit()
        self.connection = connection

    async def _migrate(self, connection: aiosqlite.Connection) -> None:
        cursor = await connection.execute("PRAGMA table_info(deposit_invoices)")
        columns = {str(row[1]) for row in await cursor.fetchall()}
        if "idempotency_key" not in columns:
            await connection.execute(
                "ALTER TABLE deposit_invoices ADD COLUMN idempotency_key TEXT"
            )
        await connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_idempotency "
            "ON deposit_invoices(user_id, idempotency_key) "
            "WHERE idempotency_key IS NOT NULL"
        )

        cursor = await connection.execute("PRAGMA table_info(users)")
        user_columns = {str(row[1]) for row in await cursor.fetchall()}
        if "manual_balance_minor" not in user_columns:
            await connection.execute(
                "ALTER TABLE users ADD COLUMN manual_balance_minor INTEGER NOT NULL DEFAULT 0"
            )

        cursor = await connection.execute("PRAGMA table_info(payouts)")
        payout_columns = {str(row[1]) for row in await cursor.fetchall()}
        if "subtype" not in payout_columns:
            await connection.execute(
                "ALTER TABLE payouts ADD COLUMN subtype TEXT NOT NULL DEFAULT '' "
                "CHECK (subtype IN ('', 'principal'))"
            )
        if "admin_test" not in payout_columns:
            await connection.execute(
                "ALTER TABLE payouts ADD COLUMN admin_test INTEGER NOT NULL DEFAULT 0 "
                "CHECK (admin_test IN (0, 1))"
            )
        if "status_changed_at" not in payout_columns:
            await connection.execute(
                "ALTER TABLE payouts ADD COLUMN status_changed_at INTEGER"
            )
            await connection.execute(
                "UPDATE payouts SET status_changed_at = updated_at "
                "WHERE status_changed_at IS NULL"
            )

        # V8: convert only legacy referral payouts that are still safely queued
        # (never signed/broadcast) into the new on-demand accrual balance.
        await connection.execute(
            """
            INSERT OR IGNORE INTO referral_accruals(
                referrer_id, referred_id, source_deposit_id, source_payout_day,
                level, percent_bps, amount_minor, created_at
            )
            SELECT rr.referrer_id, rr.referred_id, rr.source_deposit_id,
                   rr.source_payout_day, rr.level, rr.percent_bps,
                   rr.amount_minor, rr.created_at
            FROM referral_rewards AS rr
            JOIN payouts AS p ON p.id = rr.payout_id
            WHERE p.kind = 'referral'
              AND p.status = 'queued'
              AND p.idempotency_key LIKE 'referral:%'
              AND p.source_deposit_id IS NOT NULL
              AND p.tx_hash IS NULL
              AND p.raw_transaction IS NULL
            """
        )
        await connection.execute(
            """
            DELETE FROM referral_rewards
            WHERE payout_id IN (
                SELECT id FROM payouts
                WHERE kind = 'referral'
                  AND status = 'queued'
                  AND idempotency_key LIKE 'referral:%'
                  AND source_deposit_id IS NOT NULL
                  AND tx_hash IS NULL
                  AND raw_transaction IS NULL
            )
            """
        )
        await connection.execute(
            """
            DELETE FROM payouts
            WHERE kind = 'referral'
              AND status = 'queued'
              AND idempotency_key LIKE 'referral:%'
              AND source_deposit_id IS NOT NULL
              AND tx_hash IS NULL
              AND raw_transaction IS NULL
            """
        )

        cursor = await connection.execute("PRAGMA table_info(broadcasts)")
        broadcast_columns = {str(row[1]) for row in await cursor.fetchall()}
        broadcast_migrations = {
            "parse_mode": "ALTER TABLE broadcasts ADD COLUMN parse_mode TEXT NOT NULL DEFAULT 'HTML'",
            "media_path": "ALTER TABLE broadcasts ADD COLUMN media_path TEXT",
            "media_file_id": "ALTER TABLE broadcasts ADD COLUMN media_file_id TEXT",
            "buttons_json": "ALTER TABLE broadcasts ADD COLUMN buttons_json TEXT NOT NULL DEFAULT '[]'",
        }
        for name, statement in broadcast_migrations.items():
            if name not in broadcast_columns:
                await connection.execute(statement)

        await connection.execute(
            "UPDATE broadcast_deliveries SET status = 'queued' WHERE status = 'sending'"
        )
        # Remove the retired brand from durable content already stored in the
        # database so old in-app notifications and queued Telegram deliveries
        # are rendered exclusively as NOVERA after this upgrade.
        retired_brand = "G" + "FORT"
        replacements = (
            (retired_brand, "NOVERA"),
            (retired_brand.capitalize(), "Novera"),
            (retired_brand.lower(), "novera"),
        )
        for table, columns in (
            ("user_notifications", ("title", "body", "telegram_html")),
            ("broadcasts", ("message", "buttons_json")),
            ("audit_events", ("details",)),
        ):
            for column in columns:
                for old, new in replacements:
                    await connection.execute(
                        f"UPDATE {table} SET {column} = replace({column}, ?, ?) "
                        f"WHERE instr({column}, ?) > 0",
                        (old, new, old),
                    )

        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS promo_codes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              code TEXT NOT NULL UNIQUE,
              bonus_type TEXT NOT NULL CHECK (bonus_type IN ('percent', 'fixed')),
              bonus_bps INTEGER NOT NULL DEFAULT 0 CHECK (bonus_bps >= 0),
              bonus_fixed_minor INTEGER NOT NULL DEFAULT 0 CHECK (bonus_fixed_minor >= 0),
              max_redemptions INTEGER NOT NULL CHECK (max_redemptions >= 1),
              redemption_count INTEGER NOT NULL DEFAULT 0 CHECK (redemption_count >= 0),
              min_deposit_minor INTEGER NOT NULL DEFAULT 0 CHECK (min_deposit_minor >= 0),
              valid_from INTEGER,
              valid_until INTEGER,
              enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
              created_by INTEGER NOT NULL,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS promo_redemptions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              promo_code_id INTEGER NOT NULL REFERENCES promo_codes(id),
              user_id INTEGER NOT NULL,
              deposit_id INTEGER NOT NULL,
              invoice_id INTEGER NOT NULL,
              bonus_minor INTEGER NOT NULL CHECK (bonus_minor > 0),
              created_at INTEGER NOT NULL,
              UNIQUE(promo_code_id, user_id)
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              kind TEXT NOT NULL CHECK (kind IN ('promo', 'partner', 'custom')),
              audience TEXT NOT NULL CHECK (audience IN ('all', 'investors', 'partners')),
              schedule_mode TEXT NOT NULL CHECK (schedule_mode IN ('interval', 'weekly')),
              interval_hours INTEGER NOT NULL DEFAULT 24 CHECK (interval_hours >= 1),
              weekdays_json TEXT NOT NULL DEFAULT '[]',
              time_utc TEXT NOT NULL DEFAULT '12:00',
              message_html TEXT NOT NULL,
              promo_code_id INTEGER REFERENCES promo_codes(id),
              enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
              last_sent_at INTEGER,
              next_run_at INTEGER NOT NULL,
              created_by INTEGER NOT NULL,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_campaigns_due ON campaigns(enabled, next_run_at)"
        )

        cursor = await connection.execute("PRAGMA table_info(deposit_invoices)")
        invoice_columns = {str(row[1]) for row in await cursor.fetchall()}
        if "promo_code_id" not in invoice_columns:
            await connection.execute(
                "ALTER TABLE deposit_invoices ADD COLUMN promo_code_id INTEGER"
            )

        cursor = await connection.execute("PRAGMA table_info(deposits)")
        deposit_columns = {str(row[1]) for row in await cursor.fetchall()}
        if "bonus_minor" not in deposit_columns:
            await connection.execute(
                "ALTER TABLE deposits ADD COLUMN bonus_minor INTEGER NOT NULL DEFAULT 0"
            )
        if "promo_code_id" not in deposit_columns:
            await connection.execute(
                "ALTER TABLE deposits ADD COLUMN promo_code_id INTEGER"
            )

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    def _connection(self) -> aiosqlite.Connection:
        if self.connection is None:
            raise RuntimeError("Repository is not connected")
        return self.connection

    async def ping(self) -> bool:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute("SELECT 1")
            row = await cursor.fetchone()
        return bool(row and int(row[0]) == 1)

    async def database_quick_check(self) -> str:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute("PRAGMA quick_check")
            row = await cursor.fetchone()
        return str(row[0]) if row else "missing"

    async def get_safety_state(self, key: str) -> str | None:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT value_text FROM safety_state WHERE key = ?",
                (key,),
            )
            row = await cursor.fetchone()
        return str(row["value_text"]) if row else None

    async def set_safety_state(self, key: str, value: str) -> None:
        now = int(time.time())
        async with self.transaction() as connection:
            await connection.execute(
                """
                INSERT INTO safety_state(key, value_text, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_text = excluded.value_text, updated_at = excluded.updated_at
                """,
                (key, value, now),
            )

    async def granted_admin_ids(self) -> set[int]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute("SELECT telegram_id FROM admin_grants")
            rows = await cursor.fetchall()
        return {int(row["telegram_id"]) for row in rows}

    async def payout_safety_metrics(self) -> dict[str, int | None]:
        connection = self._connection()
        now = int(time.time())
        async with self._lock:
            cursor = await connection.execute(
                """
                SELECT
                    COUNT(*) AS pending_count,
                    COALESCE(SUM(amount_minor), 0) AS pending_minor,
                    MIN(CASE WHEN status IN ('signed', 'broadcast') THEN COALESCE(status_changed_at, updated_at) END) AS oldest_inflight_at
                FROM payouts
                WHERE status IN ('queued', 'signed', 'broadcast')
                """
            )
            pending = await cursor.fetchone()
            cursor = await connection.execute(
                "SELECT amount_minor FROM payouts WHERE status = 'queued' ORDER BY id LIMIT 1"
            )
            next_queued = await cursor.fetchone()
            cursor = await connection.execute(
                "SELECT MAX(confirmed_at) AS last_confirmed_at FROM payouts WHERE status = 'confirmed'"
            )
            confirmed = await cursor.fetchone()
        oldest = int(pending["oldest_inflight_at"]) if pending and pending["oldest_inflight_at"] is not None else None
        return {
            "pending_count": int(pending["pending_count"] or 0) if pending else 0,
            "pending_minor": int(pending["pending_minor"] or 0) if pending else 0,
            "next_queued_minor": int(next_queued["amount_minor"]) if next_queued else 0,
            "oldest_age_seconds": max(0, now - oldest) if oldest is not None else None,
            "last_confirmed_at": int(confirmed["last_confirmed_at"]) if confirmed and confirmed["last_confirmed_at"] is not None else None,
        }

    async def get_runtime_settings(self) -> dict[str, object]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT key, value_json FROM runtime_settings ORDER BY key"
            )
            rows = await cursor.fetchall()
        result: dict[str, object] = {}
        for row in rows:
            try:
                result[str(row["key"])] = json.loads(str(row["value_json"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return result

    async def set_runtime_settings(
        self,
        values: dict[str, object],
        changed_by: int,
    ) -> dict[str, object]:
        if not values:
            return await self.get_runtime_settings()
        now = int(time.time())
        if "payout_days" in values:
            requested_days = int(values["payout_days"])
            connection = self._connection()
            async with self._lock:
                cursor = await connection.execute(
                    "SELECT COALESCE(MAX(CASE WHEN scheduled_days > paid_days THEN scheduled_days ELSE paid_days END), 0) AS progress "
                    "FROM deposits WHERE status = 'active'"
                )
                row = await cursor.fetchone()
                progress = int(row["progress"] or 0)
            if requested_days < progress:
                raise RepositoryError(
                    f"Payout period cannot be below current active progress ({progress} days)"
                )
        async with self.transaction() as connection:
            for key, value in values.items():
                payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                await connection.execute(
                    "INSERT INTO runtime_settings(key, value_json, updated_by, updated_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                    "updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                    (key, payload, changed_by, now),
                )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "runtime_settings_updated",
                    f"admin={changed_by};keys={','.join(sorted(values))}",
                    now,
                ),
            )
        return await self.get_runtime_settings()

    async def get_chain_config_state(self) -> dict[str, object]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT status, active_generation, pending_generation, "
                "public_fingerprint, last_error_code, updated_by, updated_at "
                "FROM chain_config_state WHERE singleton = 1"
            )
            row = await cursor.fetchone()
        if row is None:
            return {
                "status": "bootstrap",
                "active_generation": None,
                "pending_generation": None,
                "public_fingerprint": None,
                "last_error_code": None,
                "updated_by": 0,
                "updated_at": 0,
            }
        return dict(row)

    async def record_chain_config_staged(
        self,
        generation: str,
        public_fingerprint: str,
        actor_id: int,
        reason: str,
    ) -> dict[str, object]:
        now = int(time.time())
        reason_audit = (
            f"sha256:{hashlib.sha256(reason.encode('utf-8')).hexdigest()[:16]};"
            f"length={len(reason)}"
        )
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT status FROM chain_config_state WHERE singleton = 1"
            )
            row = await cursor.fetchone()
            status = "active" if row and str(row["status"]) == "active" else "configured"
            await connection.execute(
                """
                INSERT INTO chain_config_state(
                    singleton, status, pending_generation, public_fingerprint,
                    last_error_code, updated_by, updated_at
                ) VALUES (1, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    status=excluded.status,
                    pending_generation=excluded.pending_generation,
                    public_fingerprint=excluded.public_fingerprint,
                    last_error_code=NULL,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """,
                (status, generation, public_fingerprint, int(actor_id), now),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "chain_config_staged",
                    f"owner={int(actor_id)};generation={generation};"
                    f"fingerprint={public_fingerprint};reason={reason_audit}",
                    now,
                ),
            )
        return await self.get_chain_config_state()

    async def get_chain_activation(self, operation_key: str) -> dict[str, object] | None:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT operation_key, generation, actor_id, reason, status, "
                "created_at, updated_at FROM chain_config_activations "
                "WHERE operation_key = ?",
                (operation_key,),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def record_chain_config_activated(
        self,
        operation_key: str,
        generation: str,
        public_fingerprint: str,
        actor_id: int,
        reason: str,
    ) -> dict[str, object]:
        now = int(time.time())
        reason_audit = (
            f"sha256:{hashlib.sha256(reason.encode('utf-8')).hexdigest()[:16]};"
            f"length={len(reason)}"
        )
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT generation, actor_id, status FROM chain_config_activations "
                "WHERE operation_key = ?",
                (operation_key,),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                if (
                    str(existing["generation"]) != generation
                    or int(existing["actor_id"]) != int(actor_id)
                ):
                    raise RepositoryError("Idempotency key was already used")
                return {
                    "generation": str(existing["generation"]),
                    "status": str(existing["status"]),
                    "reused": True,
                }
            await connection.execute(
                "INSERT INTO chain_config_activations("
                "operation_key, generation, actor_id, reason, status, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, 'activated', ?, ?)",
                (operation_key, generation, int(actor_id), reason_audit, now, now),
            )
            await connection.execute(
                """
                INSERT INTO chain_config_state(
                    singleton, status, active_generation, pending_generation,
                    public_fingerprint, last_error_code, updated_by, updated_at
                ) VALUES (1, 'active', ?, NULL, ?, NULL, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    status='active',
                    active_generation=excluded.active_generation,
                    pending_generation=NULL,
                    public_fingerprint=excluded.public_fingerprint,
                    last_error_code=NULL,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """,
                (generation, public_fingerprint, int(actor_id), now),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "chain_config_activated",
                    f"owner={int(actor_id)};generation={generation};"
                    f"fingerprint={public_fingerprint};reason={reason_audit}",
                    now,
                ),
            )
        return {"generation": generation, "status": "activated", "reused": False}

    async def mark_chain_config_runtime(
        self,
        status: str,
        *,
        generation: str | None,
        public_fingerprint: str | None,
        error_code: str | None = None,
    ) -> None:
        if status not in {"bootstrap", "configured", "active", "degraded"}:
            raise ValueError("Invalid chain setup state")
        now = int(time.time())
        async with self.transaction() as connection:
            await connection.execute(
                """
                INSERT INTO chain_config_state(
                    singleton, status, active_generation, public_fingerprint,
                    last_error_code, updated_by, updated_at
                ) VALUES (1, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    status=excluded.status,
                    active_generation=excluded.active_generation,
                    public_fingerprint=excluded.public_fingerprint,
                    last_error_code=excluded.last_error_code,
                    updated_at=excluded.updated_at
                """,
                (status, generation, public_fingerprint, error_code, now),
            )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = self._connection()
        async with self._lock:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                await connection.rollback()
                raise
            else:
                await connection.commit()

    async def _queue_notification(
        self,
        connection: aiosqlite.Connection,
        *,
        user_id: int,
        category: str,
        event_type: str,
        title: str,
        body: str,
        telegram_html: str,
        dedupe_key: str,
        data: dict[str, object] | None = None,
        created_at: int | None = None,
    ) -> bool:
        now = int(time.time()) if created_at is None else int(created_at)
        payload = json.dumps(data or {}, ensure_ascii=False, separators=(",", ":"))
        cursor = await connection.execute(
            """
            INSERT OR IGNORE INTO user_notifications(
                user_id, category, event_type, title, body, telegram_html,
                data_json, dedupe_key, telegram_updated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id), category, event_type, title, body, telegram_html,
                payload, dedupe_key, now, now,
            ),
        )
        return bool(cursor.rowcount)

    async def list_notifications(
        self,
        user_id: int,
        *,
        limit: int = 50,
        category: str | None = None,
        after_id: int | None = None,
    ) -> dict[str, object]:
        connection = self._connection()
        params: list[object] = [int(user_id)]
        where = ["user_id = ?"]
        if category in {"deposit", "payout", "partner", "system"}:
            where.append("category = ?")
            params.append(category)
        if after_id is not None and int(after_id) > 0:
            where.append("id > ?")
            params.append(int(after_id))
        params.append(max(1, min(int(limit), 100)))
        async with self._lock:
            cursor = await connection.execute(
                f"SELECT * FROM user_notifications WHERE {' AND '.join(where)} "
                "ORDER BY id DESC LIMIT ?",
                tuple(params),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM user_notifications "
                "WHERE user_id = ? AND read_at IS NULL",
                (int(user_id),),
            )
            unread = int((await cursor.fetchone())["value"] or 0)
        for row in rows:
            try:
                row["data"] = json.loads(str(row.get("data_json") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                row["data"] = {}
            row.pop("telegram_html", None)
            row.pop("data_json", None)
            row.pop("dedupe_key", None)
            row.pop("telegram_status", None)
            row.pop("telegram_attempts", None)
            row.pop("telegram_error", None)
            row.pop("telegram_sent_at", None)
            row.pop("telegram_updated_at", None)
        return {"items": rows, "unread_count": unread}

    async def mark_notification_read(self, user_id: int, notification_id: int) -> bool:
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "UPDATE user_notifications SET read_at = COALESCE(read_at, ?) "
                "WHERE id = ? AND user_id = ?",
                (int(time.time()), int(notification_id), int(user_id)),
            )
            return bool(cursor.rowcount)

    async def mark_all_notifications_read(self, user_id: int) -> int:
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "UPDATE user_notifications SET read_at = ? "
                "WHERE user_id = ? AND read_at IS NULL",
                (int(time.time()), int(user_id)),
            )
            return int(cursor.rowcount)

    async def claim_next_notification_delivery(self) -> dict[str, object] | None:
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM user_notifications
                WHERE telegram_status = 'queued'
                   OR (telegram_status = 'sending' AND telegram_updated_at < ?)
                ORDER BY id
                LIMIT 1
                """,
                (now - 300,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            notification_id = int(row["id"])
            await connection.execute(
                "UPDATE user_notifications SET telegram_status = 'sending', "
                "telegram_attempts = telegram_attempts + 1, telegram_updated_at = ?, "
                "telegram_error = NULL WHERE id = ?",
                (now, notification_id),
            )
            cursor = await connection.execute(
                "SELECT * FROM user_notifications WHERE id = ?",
                (notification_id,),
            )
            return dict(await cursor.fetchone())

    async def requeue_notification_delivery(self, notification_id: int, error: str) -> None:
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT telegram_attempts FROM user_notifications WHERE id = ?",
                (int(notification_id),),
            )
            row = await cursor.fetchone()
            attempts = int(row["telegram_attempts"] or 0) if row else 0
            status = "failed" if attempts >= 5 else "queued"
            await connection.execute(
                "UPDATE user_notifications SET telegram_status = ?, telegram_error = ?, "
                "telegram_updated_at = ? WHERE id = ?",
                (status, str(error)[:300], now, int(notification_id)),
            )

    async def finish_notification_delivery(
        self,
        notification_id: int,
        *,
        delivered: bool,
        error: str | None = None,
    ) -> None:
        now = int(time.time())
        async with self.transaction() as connection:
            await connection.execute(
                "UPDATE user_notifications SET telegram_status = ?, telegram_error = ?, "
                "telegram_sent_at = ?, telegram_updated_at = ? WHERE id = ?",
                (
                    "delivered" if delivered else "failed",
                    None if delivered else str(error or "delivery failed")[:300],
                    now if delivered else None,
                    now,
                    int(notification_id),
                ),
            )

    async def ensure_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str,
        language: str | None,
        referrer_id: int | None = None,
    ) -> bool:
        now = int(time.time())
        if referrer_id == telegram_id:
            referrer_id = None
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT telegram_id, referrer_id FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            existing = await cursor.fetchone()
            is_new_user = existing is None
            current_referrer = (
                None
                if existing is None or existing["referrer_id"] is None
                else int(existing["referrer_id"])
            )
            if referrer_id is not None:
                cursor = await connection.execute(
                    "SELECT 1 FROM users WHERE telegram_id = ?",
                    (referrer_id,),
                )
                if await cursor.fetchone() is None:
                    referrer_id = None

            # First-touch only: bind when the user has no inviter yet; never overwrite.
            can_bind = referrer_id is not None and current_referrer is None
            insert_referrer = referrer_id if (is_new_user or can_bind) else None

            await connection.execute(
                """
                INSERT INTO users(
                    telegram_id, username, first_name, language, referrer_id,
                    created_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    language = excluded.language,
                    last_seen_at = excluded.last_seen_at,
                    referrer_id = CASE
                        WHEN users.referrer_id IS NULL AND excluded.referrer_id IS NOT NULL
                        THEN excluded.referrer_id
                        ELSE users.referrer_id
                    END
                """,
                (
                    telegram_id,
                    username,
                    first_name,
                    language or "ru",
                    insert_referrer,
                    now,
                    now,
                ),
            )
            if referrer_id is not None and (can_bind or is_new_user):
                joined_referrer = int(referrer_id)
                label = f"@{username}" if username else (first_name.strip() or f"ID {telegram_id}")
                safe_label = html.escape(label)
                await self._queue_notification(
                    connection,
                    user_id=joined_referrer,
                    category="partner",
                    event_type="referral_joined",
                    title="Новый партнёр в команде",
                    body=f"{label} зарегистрировался по вашей партнёрской ссылке.",
                    telegram_html=(
                        "👥 <b>Новый партнёр в команде</b>\n\n"
                        f"Пользователь: <b>{safe_label}</b>\n"
                        "Он уже отображается в вашей структуре NOVERA."
                    ),
                    dedupe_key=f"referral-joined:{telegram_id}",
                    data={"target_view": "team", "member_id": int(telegram_id)},
                    created_at=now,
                )
            cursor = await connection.execute(
                "SELECT blocked FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            return bool(row and row["blocked"])

    async def create_web_login_token(
        self,
        user: TelegramUser,
        *,
        ttl_seconds: int = 600,
    ) -> str:
        if ttl_seconds < 60 or ttl_seconds > 3600:
            raise ValueError("Invalid web login token lifetime")
        now = int(time.time())
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with self.transaction() as connection:
            await connection.execute(
                "DELETE FROM web_login_tokens WHERE expires_at <= ?",
                (now,),
            )
            await connection.execute(
                """
                INSERT INTO web_login_tokens(
                    token_hash, telegram_id, username, first_name, language,
                    start_param, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash,
                    user.id,
                    user.username,
                    user.first_name,
                    user.language_code,
                    user.start_param,
                    now + ttl_seconds,
                    now,
                ),
            )
        return token

    async def consume_web_login_token(self, token: str) -> TelegramUser | None:
        if not token or len(token) > 256:
            return None
        now = int(time.time())
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT telegram_id, username, first_name, language, start_param, expires_at
                FROM web_login_tokens
                WHERE token_hash = ?
                """,
                (token_hash,),
            )
            row = await cursor.fetchone()
            await connection.execute(
                "DELETE FROM web_login_tokens WHERE token_hash = ? OR expires_at <= ?",
                (token_hash, now),
            )
        if row is None or int(row["expires_at"]) <= now:
            return None
        return TelegramUser(
            id=int(row["telegram_id"]),
            username=row["username"],
            first_name=str(row["first_name"] or ""),
            language_code=row["language"],
            start_param=row["start_param"],
        )

    async def set_wallet(self, user_id: int, address: str) -> None:
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "UPDATE users SET payout_address = ?, last_seen_at = ? "
                "WHERE telegram_id = ? AND blocked = 0",
                (address, int(time.time()), user_id),
            )
            if not cursor.rowcount:
                raise RepositoryError("User is missing or blocked")

    @staticmethod
    def _normalize_promo_code(code: str) -> str:
        normalized = str(code or "").strip().upper()
        if not normalized:
            raise RepositoryError("Promo code is required")
        if len(normalized) > PROMO_CODE_MAX_LENGTH:
            raise RepositoryError(
                f"Promo code must be at most {PROMO_CODE_MAX_LENGTH} characters"
            )
        return normalized

    @staticmethod
    def _validate_promo_bonus(
        bonus_type: str, bonus_bps: int, bonus_fixed_minor: int
    ) -> None:
        if bonus_type not in PROMO_BONUS_TYPES:
            raise RepositoryError("Invalid promo bonus type")
        bonus_bps = int(bonus_bps)
        bonus_fixed_minor = int(bonus_fixed_minor)
        if bonus_bps < 0 or bonus_fixed_minor < 0:
            raise RepositoryError("Promo bonus values cannot be negative")
        if bonus_type == "percent":
            if bonus_bps <= 0:
                raise RepositoryError("Percent promo requires bonus_bps > 0")
            if bonus_fixed_minor != 0:
                raise RepositoryError(
                    "Percent promo must not set bonus_fixed_minor"
                )
        else:
            if bonus_fixed_minor <= 0:
                raise RepositoryError("Fixed promo requires bonus_fixed_minor > 0")
            if bonus_bps != 0:
                raise RepositoryError("Fixed promo must not set bonus_bps")

    @staticmethod
    def _promo_row_to_dict(row: aiosqlite.Row) -> dict[str, object]:
        data = dict(row)
        data["enabled"] = bool(int(data.get("enabled") or 0))
        return data

    async def admin_create_promo_code(
        self,
        *,
        code: str,
        bonus_type: str,
        bonus_bps: int,
        bonus_fixed_minor: int,
        max_redemptions: int,
        min_deposit_minor: int,
        valid_from: int | None,
        valid_until: int | None,
        enabled: bool,
        created_by: int,
    ) -> dict[str, object]:
        normalized_code = self._normalize_promo_code(code)
        self._validate_promo_bonus(bonus_type, bonus_bps, bonus_fixed_minor)
        if int(max_redemptions) < 1:
            raise RepositoryError("max_redemptions must be at least 1")
        if int(min_deposit_minor) < 0:
            raise RepositoryError("min_deposit_minor cannot be negative")
        now = int(time.time())
        async with self.transaction() as connection:
            try:
                cursor = await connection.execute(
                    """
                    INSERT INTO promo_codes(
                        code, bonus_type, bonus_bps, bonus_fixed_minor,
                        max_redemptions, min_deposit_minor, valid_from, valid_until,
                        enabled, created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_code,
                        bonus_type,
                        int(bonus_bps),
                        int(bonus_fixed_minor),
                        int(max_redemptions),
                        int(min_deposit_minor),
                        None if valid_from is None else int(valid_from),
                        None if valid_until is None else int(valid_until),
                        1 if enabled else 0,
                        int(created_by),
                        now,
                        now,
                    ),
                )
            except aiosqlite.IntegrityError as exc:
                raise RepositoryError("Promo code already exists") from exc
            cursor = await connection.execute(
                "SELECT * FROM promo_codes WHERE id = ?", (cursor.lastrowid,)
            )
            row = await cursor.fetchone()
        return self._promo_row_to_dict(row)

    async def admin_list_promo_codes(self) -> list[dict[str, object]]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT * FROM promo_codes ORDER BY id DESC"
            )
            rows = await cursor.fetchall()
        return [self._promo_row_to_dict(row) for row in rows]

    async def admin_update_promo_code(
        self, promo_id: int, **fields: object
    ) -> dict[str, object]:
        allowed = {
            "code",
            "bonus_type",
            "bonus_bps",
            "bonus_fixed_minor",
            "max_redemptions",
            "min_deposit_minor",
            "valid_from",
            "valid_until",
            "enabled",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise RepositoryError(f"Unknown promo field(s): {', '.join(sorted(unknown))}")

        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT * FROM promo_codes WHERE id = ?", (int(promo_id),)
            )
            row = await cursor.fetchone()
            if not row:
                raise RepositoryError("Promo code not found")
            current = dict(row)

            if "code" in fields:
                current["code"] = self._normalize_promo_code(str(fields["code"]))
            if "bonus_type" in fields:
                current["bonus_type"] = str(fields["bonus_type"])
            if "bonus_bps" in fields:
                current["bonus_bps"] = int(fields["bonus_bps"])
            if "bonus_fixed_minor" in fields:
                current["bonus_fixed_minor"] = int(fields["bonus_fixed_minor"])
            self._validate_promo_bonus(
                str(current["bonus_type"]),
                int(current["bonus_bps"]),
                int(current["bonus_fixed_minor"]),
            )

            if "max_redemptions" in fields:
                if int(fields["max_redemptions"]) < 1:
                    raise RepositoryError("max_redemptions must be at least 1")
                current["max_redemptions"] = int(fields["max_redemptions"])
            if "min_deposit_minor" in fields:
                if int(fields["min_deposit_minor"]) < 0:
                    raise RepositoryError("min_deposit_minor cannot be negative")
                current["min_deposit_minor"] = int(fields["min_deposit_minor"])
            if "valid_from" in fields:
                value = fields["valid_from"]
                current["valid_from"] = None if value is None else int(value)
            if "valid_until" in fields:
                value = fields["valid_until"]
                current["valid_until"] = None if value is None else int(value)
            if "enabled" in fields:
                current["enabled"] = 1 if fields["enabled"] else 0

            try:
                await connection.execute(
                    """
                    UPDATE promo_codes SET
                        code = ?, bonus_type = ?, bonus_bps = ?, bonus_fixed_minor = ?,
                        max_redemptions = ?, min_deposit_minor = ?, valid_from = ?,
                        valid_until = ?, enabled = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        current["code"],
                        current["bonus_type"],
                        int(current["bonus_bps"]),
                        int(current["bonus_fixed_minor"]),
                        int(current["max_redemptions"]),
                        int(current["min_deposit_minor"]),
                        current["valid_from"],
                        current["valid_until"],
                        int(current["enabled"]),
                        int(time.time()),
                        int(promo_id),
                    ),
                )
            except aiosqlite.IntegrityError as exc:
                raise RepositoryError("Promo code already exists") from exc

            cursor = await connection.execute(
                "SELECT * FROM promo_codes WHERE id = ?", (int(promo_id),)
            )
            row = await cursor.fetchone()
        return self._promo_row_to_dict(row)

    async def get_promo_by_code(self, code: str) -> dict[str, object] | None:
        normalized_code = str(code or "").strip().upper()
        if not normalized_code:
            return None
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT * FROM promo_codes WHERE code = ?", (normalized_code,)
            )
            row = await cursor.fetchone()
        return self._promo_row_to_dict(row) if row else None

    @staticmethod
    def _campaign_row_to_dict(row: aiosqlite.Row | dict[str, object]) -> dict[str, object]:
        data = dict(row)
        data["enabled"] = bool(int(data.get("enabled") or 0))
        data["weekdays"] = parse_campaign_weekdays(data.get("weekdays_json"))
        return data

    @staticmethod
    def _prepare_campaign_fields(
        *,
        kind: object,
        audience: object,
        schedule_mode: object,
        interval_hours: object,
        weekdays: object,
        time_utc: object,
        message_html: object,
        promo_code_id: object,
    ) -> dict[str, object]:
        kind = str(kind or "")
        if kind not in CAMPAIGN_KINDS:
            raise RepositoryError("Unsupported campaign kind")
        audience = str(audience or "")
        if audience not in BROADCAST_AUDIENCE_FILTERS:
            raise RepositoryError("Unsupported campaign audience")
        schedule_mode = str(schedule_mode or "")
        if schedule_mode not in CAMPAIGN_SCHEDULE_MODES:
            raise RepositoryError("Unsupported campaign schedule mode")
        hours = int(interval_hours)
        if not 1 <= hours <= CAMPAIGN_MAX_INTERVAL_HOURS:
            raise RepositoryError(
                f"interval_hours must be between 1 and {CAMPAIGN_MAX_INTERVAL_HOURS}"
            )
        parsed_weekdays = parse_campaign_weekdays(weekdays)
        if schedule_mode == "weekly" and not parsed_weekdays:
            raise RepositoryError("Weekly campaigns require at least one weekday")
        hour, minute = parse_campaign_time_utc(time_utc)
        message = str(message_html or "").strip()
        if not message:
            message = default_campaign_message(kind).strip()
        if not message:
            raise RepositoryError("Campaign message is required")
        if len(message) > CAMPAIGN_MESSAGE_MAX_LENGTH:
            raise RepositoryError(
                f"Campaign message must be at most {CAMPAIGN_MESSAGE_MAX_LENGTH} characters"
            )
        promo_id = None if promo_code_id is None else int(promo_code_id)
        if kind == "promo" and promo_id is None:
            raise RepositoryError("Promo campaigns require promo_code_id")
        return {
            "kind": kind,
            "audience": audience,
            "schedule_mode": schedule_mode,
            "interval_hours": hours,
            "weekdays": parsed_weekdays,
            "weekdays_json": json.dumps(parsed_weekdays, separators=(",", ":")),
            "time_utc": f"{hour:02d}:{minute:02d}",
            "message_html": message,
            "promo_code_id": promo_id,
        }

    @staticmethod
    async def _assert_promo_code_exists(
        connection: aiosqlite.Connection, promo_code_id: object
    ) -> None:
        if promo_code_id is None:
            return
        cursor = await connection.execute(
            "SELECT 1 FROM promo_codes WHERE id = ?", (int(promo_code_id),)
        )
        if not await cursor.fetchone():
            raise RepositoryError("Promo code not found")

    async def admin_create_campaign(
        self,
        *,
        kind: str,
        audience: str,
        schedule_mode: str,
        message_html: str,
        created_by: int,
        interval_hours: int = 24,
        weekdays: list[int] | None = None,
        time_utc: str = "12:00",
        promo_code_id: int | None = None,
        enabled: bool = True,
        next_run_at: int | None = None,
    ) -> dict[str, object]:
        prepared = self._prepare_campaign_fields(
            kind=kind,
            audience=audience,
            schedule_mode=schedule_mode,
            interval_hours=interval_hours,
            weekdays=weekdays,
            time_utc=time_utc,
            message_html=message_html,
            promo_code_id=promo_code_id,
        )
        now = int(time.time())
        run_at = compute_next_run_at(prepared, now) if next_run_at is None else int(next_run_at)
        async with self.transaction() as connection:
            await self._assert_promo_code_exists(connection, prepared["promo_code_id"])
            cursor = await connection.execute(
                """
                INSERT INTO campaigns(
                    kind, audience, schedule_mode, interval_hours, weekdays_json,
                    time_utc, message_html, promo_code_id, enabled, next_run_at,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prepared["kind"],
                    prepared["audience"],
                    prepared["schedule_mode"],
                    prepared["interval_hours"],
                    prepared["weekdays_json"],
                    prepared["time_utc"],
                    prepared["message_html"],
                    prepared["promo_code_id"],
                    1 if enabled else 0,
                    run_at,
                    int(created_by),
                    now,
                    now,
                ),
            )
            cursor = await connection.execute(
                "SELECT * FROM campaigns WHERE id = ?", (cursor.lastrowid,)
            )
            row = await cursor.fetchone()
        return self._campaign_row_to_dict(row)

    async def admin_list_campaigns(self) -> list[dict[str, object]]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute("SELECT * FROM campaigns ORDER BY id DESC")
            rows = await cursor.fetchall()
        return [self._campaign_row_to_dict(row) for row in rows]

    async def admin_update_campaign(
        self, campaign_id: int, **fields: object
    ) -> dict[str, object]:
        allowed = {
            "kind",
            "audience",
            "schedule_mode",
            "interval_hours",
            "weekdays",
            "time_utc",
            "message_html",
            "promo_code_id",
            "enabled",
            "next_run_at",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise RepositoryError(
                f"Unknown campaign field(s): {', '.join(sorted(unknown))}"
            )

        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT * FROM campaigns WHERE id = ?", (int(campaign_id),)
            )
            row = await cursor.fetchone()
            if not row:
                raise RepositoryError("Campaign not found")
            current = self._campaign_row_to_dict(row)
            prepared = self._prepare_campaign_fields(
                kind=fields.get("kind", current["kind"]),
                audience=fields.get("audience", current["audience"]),
                schedule_mode=fields.get("schedule_mode", current["schedule_mode"]),
                interval_hours=fields.get("interval_hours", current["interval_hours"]),
                weekdays=fields.get("weekdays", current["weekdays"]),
                time_utc=fields.get("time_utc", current["time_utc"]),
                message_html=fields.get("message_html", current["message_html"]),
                promo_code_id=fields.get("promo_code_id", current["promo_code_id"]),
            )
            await self._assert_promo_code_exists(connection, prepared["promo_code_id"])

            enabled = bool(fields["enabled"]) if "enabled" in fields else bool(current["enabled"])
            was_enabled = bool(current["enabled"])
            schedule_keys = ("schedule_mode", "interval_hours", "weekdays", "time_utc")
            if fields.get("next_run_at") is not None:
                next_run_at = int(fields["next_run_at"])
            elif any(key in fields for key in schedule_keys):
                # A rescheduled campaign must not keep the slot derived from the old schedule.
                next_run_at = compute_next_run_at(prepared, now)
            elif enabled and not was_enabled and int(current["next_run_at"]) <= now:
                # Re-enabling a campaign whose slot already passed must not let it
                # fire immediately off-schedule; recompute a future slot instead.
                next_run_at = compute_next_run_at(prepared, now)
            else:
                next_run_at = int(current["next_run_at"])

            await connection.execute(
                """
                UPDATE campaigns SET
                    kind = ?, audience = ?, schedule_mode = ?, interval_hours = ?,
                    weekdays_json = ?, time_utc = ?, message_html = ?, promo_code_id = ?,
                    enabled = ?, next_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    prepared["kind"],
                    prepared["audience"],
                    prepared["schedule_mode"],
                    prepared["interval_hours"],
                    prepared["weekdays_json"],
                    prepared["time_utc"],
                    prepared["message_html"],
                    prepared["promo_code_id"],
                    1 if enabled else 0,
                    next_run_at,
                    now,
                    int(campaign_id),
                ),
            )
            cursor = await connection.execute(
                "SELECT * FROM campaigns WHERE id = ?", (int(campaign_id),)
            )
            row = await cursor.fetchone()
        return self._campaign_row_to_dict(row)

    async def claim_due_campaigns(self, now: int, limit: int = 10) -> list[dict[str, object]]:
        """Take ownership of every campaign that is due, advancing its next slot.

        The slot is advanced inside the claiming transaction, so a second worker
        (or a second tick) cannot pick the same due window up again. Advancing
        from ``now`` rather than from the stored slot also means a worker outage
        never replays a backlog of missed sends.
        """
        now = int(now)
        claimed: list[dict[str, object]] = []
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM campaigns
                WHERE enabled = 1 AND next_run_at <= ?
                ORDER BY next_run_at, id
                LIMIT ?
                """,
                (now, max(1, min(int(limit), 100))),
            )
            for row in await cursor.fetchall():
                campaign = self._campaign_row_to_dict(row)
                try:
                    next_run_at = compute_next_run_at(campaign, now)
                except RepositoryError:
                    next_run_at = now + CAMPAIGN_DAY_SECONDS
                await connection.execute(
                    "UPDATE campaigns SET next_run_at = ?, updated_at = ? WHERE id = ?",
                    (next_run_at, now, int(campaign["id"])),
                )
                campaign["next_run_at"] = next_run_at
                claimed.append(campaign)
        return claimed

    async def _record_campaign_skip(
        self, campaign_id: int, kind: str, reason: str, now: int
    ) -> dict[str, object]:
        async with self.transaction() as connection:
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) "
                "VALUES ('campaign_skipped', ?, ?)",
                (f"campaign={campaign_id};kind={kind};reason={reason}", now),
            )
        return {
            "campaign_id": int(campaign_id),
            "status": "skipped",
            "reason": reason,
            "broadcast_id": None,
        }

    async def dispatch_campaign(
        self, campaign_id: int, *, force: bool = False
    ) -> dict[str, object]:
        """Queue one broadcast for a campaign, or report why it was skipped.

        ``force`` ignores the enabled flag for admin-triggered sends; promo
        availability is always enforced so an exhausted code is never advertised.
        """
        campaign_id = int(campaign_id)
        now = int(time.time())
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
            )
            row = await cursor.fetchone()
            campaign = self._campaign_row_to_dict(row) if row else None
            promo: dict[str, object] | None = None
            if campaign is not None and campaign["promo_code_id"] is not None:
                cursor = await connection.execute(
                    "SELECT * FROM promo_codes WHERE id = ?",
                    (int(campaign["promo_code_id"]),),
                )
                promo_row = await cursor.fetchone()
                promo = self._promo_row_to_dict(promo_row) if promo_row else None

        if campaign is None:
            raise RepositoryError("Campaign not found")
        kind = str(campaign["kind"])
        if not campaign["enabled"] and not force:
            return await self._record_campaign_skip(
                campaign_id, kind, "campaign_disabled", now
            )
        if campaign["promo_code_id"] is not None or kind == "promo":
            reason = campaign_promo_skip_reason(promo, now)
            if reason is not None:
                return await self._record_campaign_skip(campaign_id, kind, reason, now)

        message = render_campaign_message(
            str(campaign["message_html"]),
            promo,
            bot_username=self.business.bot_username,
        )
        broadcast = await self.create_broadcast(
            int(campaign["created_by"]),
            message,
            str(campaign["audience"]),
        )
        broadcast_id = int(broadcast["id"])
        async with self.transaction() as connection:
            if force:
                # A forced admin "run now" send must still push the schedule
                # forward. Without this the slot stays due (or in the past),
                # so the background scheduler's next tick would claim it and
                # send the same campaign again within seconds.
                try:
                    next_run_at = compute_next_run_at(campaign, now)
                except RepositoryError:
                    next_run_at = now + CAMPAIGN_DAY_SECONDS
                await connection.execute(
                    "UPDATE campaigns SET last_sent_at = ?, next_run_at = ?, "
                    "updated_at = ? WHERE id = ?",
                    (now, next_run_at, now, campaign_id),
                )
            else:
                await connection.execute(
                    "UPDATE campaigns SET last_sent_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, campaign_id),
                )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) "
                "VALUES ('campaign_dispatched', ?, ?)",
                (
                    f"campaign={campaign_id};kind={kind};"
                    f"audience={campaign['audience']};broadcast={broadcast_id};"
                    f"total={int(broadcast['total_count'])}",
                    now,
                ),
            )
        return {
            "campaign_id": campaign_id,
            "status": "sent",
            "reason": None,
            "broadcast_id": broadcast_id,
            "audience": str(campaign["audience"]),
            "total_count": int(broadcast["total_count"]),
        }

    async def create_invoice(
        self,
        user_id: int,
        base_minor: int,
        idempotency_key: str | None = None,
        promo_code: str | None = None,
    ) -> dict[str, int | bool | None]:
        minimum = self.business.deposit_min_usdt * MINOR_FACTOR
        maximum = self.business.deposit_max_usdt * MINOR_FACTOR
        if not minimum <= base_minor <= maximum:
            raise RepositoryError("Deposit amount is outside configured limits")

        now = int(time.time())
        expires_at = now + self.business.invoice_ttl_minutes * 60
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT payout_address, blocked FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            user = await cursor.fetchone()
            if not user or user["blocked"]:
                raise RepositoryError("User is missing or blocked")
            if not user["payout_address"]:
                raise RepositoryError("Set a payout wallet before creating a deposit")

            await connection.execute(
                "UPDATE deposit_invoices SET status = 'expired' "
                "WHERE status = 'pending' AND expires_at < ?",
                (now,),
            )

            requested_promo_code: str | None = None
            if promo_code is not None and str(promo_code).strip():
                requested_promo_code = self._normalize_promo_code(promo_code)

            # Idempotent replays must resolve before promo validation so a retry
            # keeps returning its invoice even after the promo was disabled,
            # capped or expired in the meantime.
            if idempotency_key:
                cursor = await connection.execute(
                    """
                    SELECT invoice.id, invoice.base_minor, invoice.exact_minor,
                           invoice.expires_at, invoice.promo_code_id,
                           promo.code AS promo_code, promo.bonus_type,
                           promo.bonus_bps, promo.bonus_fixed_minor
                    FROM deposit_invoices invoice
                    LEFT JOIN promo_codes promo ON promo.id = invoice.promo_code_id
                    WHERE invoice.user_id = ? AND invoice.idempotency_key = ?
                    """,
                    (user_id, idempotency_key),
                )
                existing = await cursor.fetchone()
                if existing:
                    if int(existing["base_minor"]) != base_minor:
                        raise RepositoryError(
                            "Idempotency key was already used for another amount"
                        )
                    existing_promo_id = existing["promo_code_id"]
                    existing_promo_id = (
                        int(existing_promo_id) if existing_promo_id is not None else None
                    )
                    existing_promo_code = existing["promo_code"]
                    if (
                        None if existing_promo_code is None else str(existing_promo_code)
                    ) != requested_promo_code:
                        raise RepositoryError(
                            "Idempotency key was already used with a different promo code"
                        )
                    existing_bonus_minor = 0
                    if existing_promo_id is not None:
                        try:
                            existing_bonus_minor = compute_promo_bonus_minor(
                                dict(existing), base_minor
                            )
                        except RepositoryError:
                            existing_bonus_minor = 0
                    return {
                        "invoice_id": int(existing["id"]),
                        "exact_minor": int(existing["exact_minor"]),
                        "expires_at": int(existing["expires_at"]),
                        "reused": True,
                        "promo_code_id": existing_promo_id,
                        "bonus_minor": existing_bonus_minor,
                        "effective_principal_preview_minor": base_minor
                        + existing_bonus_minor,
                    }

            promo_code_id: int | None = None
            bonus_minor = 0
            if requested_promo_code is not None:
                promo_cursor = await connection.execute(
                    "SELECT * FROM promo_codes WHERE code = ?", (requested_promo_code,)
                )
                promo_row = await promo_cursor.fetchone()
                if not promo_row or not promo_row["enabled"]:
                    raise RepositoryError("Promo code is not available")
                promo = dict(promo_row)
                if promo["valid_from"] is not None and now < int(promo["valid_from"]):
                    raise RepositoryError("Promo code is not yet active")
                if promo["valid_until"] is not None and now > int(promo["valid_until"]):
                    raise RepositoryError("Promo code has expired")
                if int(promo["redemption_count"]) >= int(promo["max_redemptions"]):
                    raise RepositoryError("Promo code redemption limit reached")
                if base_minor < int(promo["min_deposit_minor"]):
                    raise RepositoryError("Deposit amount is below promo minimum")
                redeemed_cursor = await connection.execute(
                    "SELECT 1 FROM promo_redemptions WHERE promo_code_id = ? AND user_id = ?",
                    (int(promo["id"]), user_id),
                )
                if await redeemed_cursor.fetchone():
                    raise RepositoryError("Promo code already redeemed by this user")
                bonus_minor = compute_promo_bonus_minor(promo, base_minor)
                if bonus_minor <= 0:
                    raise RepositoryError("Promo code does not grant a bonus")
                if base_minor + bonus_minor > maximum:
                    raise RepositoryError("Promo would exceed deposit maximum")
                promo_code_id = int(promo["id"])

            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM deposit_invoices "
                "WHERE user_id = ? AND status = 'pending'",
                (user_id,),
            )
            if int((await cursor.fetchone())["value"]) >= 3:
                raise RepositoryError("Too many pending deposit invoices")

            for _ in range(30):
                exact_minor = base_minor + secrets.randbelow(99) + 1
                try:
                    cursor = await connection.execute(
                        """
                        INSERT INTO deposit_invoices(
                            user_id, idempotency_key, base_minor, exact_minor,
                            expires_at, created_at, promo_code_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            idempotency_key,
                            base_minor,
                            exact_minor,
                            expires_at,
                            now,
                            promo_code_id,
                        ),
                    )
                except aiosqlite.IntegrityError:
                    continue
                return {
                    "invoice_id": int(cursor.lastrowid),
                    "exact_minor": exact_minor,
                    "expires_at": expires_at,
                    "reused": False,
                    "promo_code_id": promo_code_id,
                    "bonus_minor": bonus_minor,
                    "effective_principal_preview_minor": base_minor + bonus_minor,
                }
        raise RepositoryError("Could not reserve a unique deposit amount")

    async def _invoice_mismatch_hint(
        self,
        connection: aiosqlite.Connection,
        *,
        created_at: int,
        expires_at: int,
        base_minor: int,
        exact_minor: int,
    ) -> dict | None:
        start = int(created_at) - MISMATCH_LOOKBACK_SECONDS
        end = int(expires_at) + MISMATCH_LOOKAHEAD_AFTER_EXPIRY_SECONDS
        cursor = await connection.execute(
            """
            SELECT id, amount_minor, created_at, tx_hash, matched
            FROM chain_deposits
            WHERE matched = 0
              AND created_at BETWEEN ? AND ?
            """,
            (start, end),
        )
        candidates = [dict(row) for row in await cursor.fetchall()]
        return select_mismatch_candidate(
            {
                "created_at": int(created_at),
                "expires_at": int(expires_at),
                "base_minor": int(base_minor),
                "exact_minor": int(exact_minor),
            },
            candidates,
        )

    async def get_user_invoice(
        self, user_id: int, invoice_id: int
    ) -> dict[str, object] | None:
        """Return an invoice owned by ``user_id``, or ``None`` if missing/foreign."""
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT invoice.id, invoice.status, invoice.expires_at,
                       invoice.created_at, invoice.exact_minor, invoice.base_minor,
                       invoice.promo_code_id,
                       promo.bonus_type, promo.bonus_bps, promo.bonus_fixed_minor,
                       deposit.id AS deposit_id
                FROM deposit_invoices invoice
                LEFT JOIN promo_codes promo ON promo.id = invoice.promo_code_id
                LEFT JOIN deposits deposit ON deposit.invoice_id = invoice.id
                WHERE invoice.id = ? AND invoice.user_id = ?
                """,
                (int(invoice_id), int(user_id)),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            status = str(row["status"])
            expires_at = int(row["expires_at"])
            if status == "pending" and expires_at <= now:
                status = "expired"
                await connection.execute(
                    "UPDATE deposit_invoices SET status = 'expired' "
                    "WHERE id = ? AND status = 'pending'",
                    (int(invoice_id),),
                )
            deposit_id = row["deposit_id"]
            deposit_id = int(deposit_id) if deposit_id is not None else None
            bonus_minor = 0
            if row["promo_code_id"] is not None:
                try:
                    bonus_minor = compute_promo_bonus_minor(
                        dict(row), int(row["base_minor"])
                    )
                except RepositoryError:
                    bonus_minor = 0
            base_minor = int(row["base_minor"])
            exact_minor = int(row["exact_minor"])
            credited = status == "paid" or deposit_id is not None
            mismatch_row = None
            if not credited:
                mismatch_row = await self._invoice_mismatch_hint(
                    connection,
                    created_at=int(row["created_at"]),
                    expires_at=expires_at,
                    base_minor=base_minor,
                    exact_minor=exact_minor,
                )
            mismatch: dict[str, object] | None = None
            if mismatch_row is not None:
                mismatch = {
                    "observed_amount": minor_to_text(
                        int(mismatch_row["amount_minor"]), trim=False
                    ),
                    "expected_amount": minor_to_text(exact_minor, trim=False),
                    "tx_hash": str(mismatch_row["tx_hash"]),
                    "created_at": int(mismatch_row["created_at"]),
                }
            return {
                "id": int(row["id"]),
                "status": status,
                "expires_at": expires_at,
                "exact_amount": minor_to_text(exact_minor, trim=False),
                "bonus_usdt": minor_to_text(bonus_minor, trim=False),
                "effective_principal_usdt": minor_to_text(
                    base_minor + bonus_minor, trim=False
                ),
                "deposit_id": deposit_id,
                "credited": credited,
                "mismatch_hint": mismatch is not None,
                "mismatch": mismatch,
            }

    async def expire_invoices(self) -> int:
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "UPDATE deposit_invoices SET status = 'expired' "
                "WHERE status = 'pending' AND expires_at < ?",
                (int(time.time()),),
            )
            return int(cursor.rowcount)

    async def _reserve_promo_redemption(
        self,
        connection: aiosqlite.Connection,
        *,
        promo_code_id: int,
        user_id: int,
        base_minor: int,
        now: int,
    ) -> tuple[int, str | None]:
        """Claim a redemption slot for an invoice promo without raising.

        Returns ``(bonus_minor, skip_reason)``. A non-null skip reason means the
        promo must be dropped from the deposit; nothing was reserved. Callers
        must still credit the transfer, because a confirmed on-chain payment can
        never be rejected over promo bookkeeping.
        """
        cursor = await connection.execute(
            "SELECT * FROM promo_codes WHERE id = ?", (promo_code_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return 0, "promo_missing"
        promo = dict(row)
        if not promo["enabled"]:
            return 0, "promo_disabled"
        if promo["valid_from"] is not None and now < int(promo["valid_from"]):
            return 0, "promo_not_active"
        if promo["valid_until"] is not None and now > int(promo["valid_until"]):
            return 0, "promo_expired"
        try:
            bonus_minor = compute_promo_bonus_minor(promo, base_minor)
        except RepositoryError:
            return 0, "promo_bonus_invalid"
        if bonus_minor <= 0:
            return 0, "promo_bonus_invalid"
        cursor = await connection.execute(
            "SELECT 1 FROM promo_redemptions WHERE promo_code_id = ? AND user_id = ?",
            (promo_code_id, user_id),
        )
        if await cursor.fetchone():
            return 0, "promo_already_redeemed"
        cursor = await connection.execute(
            """
            UPDATE promo_codes
            SET redemption_count = redemption_count + 1
            WHERE id = ? AND redemption_count < max_redemptions
            """,
            (promo_code_id,),
        )
        if not cursor.rowcount:
            return 0, "promo_cap_reached"
        return bonus_minor, None

    async def list_unmatched_chain_deposits(
        self, *, limit: int = 50
    ) -> list[dict[str, object]]:
        connection = self._connection()
        capped = max(1, min(int(limit), 200))
        async with self._lock:
            cursor = await connection.execute(
                "SELECT * FROM chain_deposits "
                "WHERE matched = 0 ORDER BY id DESC LIMIT ?",
                (capped,),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        for row in rows:
            row["amount"] = minor_to_text(int(row["amount_minor"]))
        return rows

    async def admin_match_chain_deposit(
        self,
        chain_deposit_id: int,
        invoice_id: int,
        *,
        admin_id: int,
        reason: str,
    ) -> dict[str, object]:
        clean_reason = str(reason or "").strip()
        if not clean_reason:
            raise RepositoryError("Recovery reason is required")
        clean_reason = clean_reason[:500]
        now = int(time.time())

        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT * FROM chain_deposits WHERE id = ?",
                (int(chain_deposit_id),),
            )
            chain_deposit = await cursor.fetchone()
            if chain_deposit is None:
                raise RepositoryError("Chain deposit not found")
            if bool(chain_deposit["matched"]) or chain_deposit["invoice_id"] is not None:
                raise RepositoryError("Chain deposit is already matched")

            cursor = await connection.execute(
                """
                SELECT invoice.*, users.payout_address, users.blocked
                FROM deposit_invoices AS invoice
                LEFT JOIN users ON users.telegram_id = invoice.user_id
                WHERE invoice.id = ?
                """,
                (int(invoice_id),),
            )
            invoice = await cursor.fetchone()
            if invoice is None:
                raise RepositoryError("Invoice not found")

            status = str(invoice["status"])
            if status == "pending" and int(invoice["expires_at"]) <= now:
                await connection.execute(
                    "UPDATE deposit_invoices SET status = 'expired' "
                    "WHERE id = ? AND status = 'pending'",
                    (int(invoice_id),),
                )
                status = "expired"
            if status == "paid":
                raise RepositoryError("Invoice is already paid")
            if status not in {"pending", "expired"}:
                raise RepositoryError("Invoice is not recoverable")
            if bool(invoice["blocked"]):
                raise RepositoryError("Account is blocked")
            payout_address = str(invoice["payout_address"] or "").strip()
            if not payout_address:
                raise RepositoryError("User payout wallet is not configured")

            cursor = await connection.execute(
                "SELECT 1 FROM deposits WHERE invoice_id = ?",
                (int(invoice_id),),
            )
            if await cursor.fetchone() is not None:
                raise RepositoryError("Invoice already has a deposit")

            tx_hash = str(chain_deposit["tx_hash"])
            cursor = await connection.execute(
                """
                UPDATE deposit_invoices
                SET status = 'paid', tx_hash = ?, paid_at = ?
                WHERE id = ? AND status IN ('pending', 'expired')
                """,
                (tx_hash, now, int(invoice_id)),
            )
            if not cursor.rowcount:
                raise RepositoryError("Invoice is not recoverable")
            cursor = await connection.execute(
                """
                UPDATE chain_deposits
                SET invoice_id = ?, matched = 1
                WHERE id = ? AND matched = 0 AND invoice_id IS NULL
                """,
                (int(invoice_id), int(chain_deposit_id)),
            )
            if not cursor.rowcount:
                raise RepositoryError("Chain deposit is already matched")

            bonus_minor = 0
            promo_code_id = invoice["promo_code_id"]
            promo_code_id = int(promo_code_id) if promo_code_id is not None else None
            skipped_promo_code_id = promo_code_id
            promo_skip_reason: str | None = None
            if promo_code_id is not None:
                bonus_minor, promo_skip_reason = await self._reserve_promo_redemption(
                    connection,
                    promo_code_id=promo_code_id,
                    user_id=int(invoice["user_id"]),
                    base_minor=int(invoice["base_minor"]),
                    now=now,
                )
                if promo_skip_reason is not None:
                    bonus_minor = 0
                    promo_code_id = None

            amount_minor = int(chain_deposit["amount_minor"])
            principal_minor = amount_minor + bonus_minor
            cursor = await connection.execute(
                """
                INSERT INTO deposits(
                    user_id, invoice_id, principal_minor, payout_address,
                    next_payout_at, opened_at, bonus_minor, promo_code_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(invoice["user_id"]),
                    int(invoice_id),
                    principal_minor,
                    payout_address,
                    now + 86_400,
                    now,
                    bonus_minor,
                    promo_code_id,
                ),
            )
            deposit_id = int(cursor.lastrowid)

            if promo_code_id is not None:
                try:
                    await connection.execute(
                        """
                        INSERT INTO promo_redemptions(
                            promo_code_id, user_id, deposit_id, invoice_id,
                            bonus_minor, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            promo_code_id,
                            int(invoice["user_id"]),
                            deposit_id,
                            int(invoice_id),
                            bonus_minor,
                            now,
                        ),
                    )
                except aiosqlite.IntegrityError:
                    await connection.execute(
                        "UPDATE promo_codes SET redemption_count = redemption_count - 1 "
                        "WHERE id = ? AND redemption_count > 0",
                        (promo_code_id,),
                    )
                    await connection.execute(
                        "UPDATE deposits SET principal_minor = ?, bonus_minor = 0, "
                        "promo_code_id = NULL WHERE id = ?",
                        (amount_minor, deposit_id),
                    )
                    principal_minor = amount_minor
                    bonus_minor = 0
                    promo_code_id = None
                    promo_skip_reason = "promo_redemption_conflict"

            if promo_skip_reason is not None:
                await connection.execute(
                    "INSERT INTO audit_events(event_type, details, created_at) "
                    "VALUES ('promo_redeem_skipped', ?, ?)",
                    (
                        f"deposit={deposit_id};invoice={int(invoice_id)};"
                        f"promo={skipped_promo_code_id};reason={promo_skip_reason}",
                        now,
                    ),
                )

            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) "
                "VALUES ('deposit_recovery_matched', ?, ?)",
                (
                    f"admin={int(admin_id)};chain_deposit={int(chain_deposit_id)};"
                    f"invoice={int(invoice_id)};deposit={deposit_id};tx={tx_hash};"
                    f"amount_minor={amount_minor};principal_minor={principal_minor};"
                    f"bonus_minor={bonus_minor};reason={clean_reason}",
                    now,
                ),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) "
                "VALUES ('deposit_opened', ?, ?)",
                (f"deposit={deposit_id};tx={tx_hash}", now),
            )

            amount_text = minor_to_text(amount_minor)
            principal_text = minor_to_text(principal_minor)
            if bonus_minor > 0:
                bonus_text = minor_to_text(bonus_minor)
                body = (
                    f"Зачислено {amount_text} USDT + бонус {bonus_text} USDT = "
                    f"{principal_text} USDT. Депозит #{deposit_id} активирован."
                )
                telegram_html = (
                    "✅ <b>Пополнение подтверждено</b>\n\n"
                    f"💰 Зачислено: <b>{amount_text} USDT</b>\n"
                    f"🎁 Бонус: <b>+{bonus_text} USDT</b>\n"
                    f"📦 Депозит: <b>#{deposit_id}</b> на сумму "
                    f"<b>{principal_text} USDT</b>\n"
                    "⏱ Первая выплата — через 24 часа."
                )
            else:
                body = (
                    f"Зачислено {principal_text} USDT. "
                    f"Депозит #{deposit_id} активирован."
                )
                telegram_html = (
                    "✅ <b>Пополнение подтверждено</b>\n\n"
                    f"💰 Зачислено: <b>{principal_text} USDT</b>\n"
                    f"📦 Депозит: <b>#{deposit_id}</b>\n"
                    "⏱ Первая выплата — через 24 часа."
                )
            await self._queue_notification(
                connection,
                user_id=int(invoice["user_id"]),
                category="deposit",
                event_type="deposit_confirmed",
                title="Пополнение подтверждено",
                body=body,
                telegram_html=telegram_html,
                dedupe_key=f"deposit-confirmed:{deposit_id}",
                data={
                    "target_view": "assets",
                    "deposit_id": deposit_id,
                    "chain_deposit_id": int(chain_deposit_id),
                    "amount_minor": amount_minor,
                    "bonus_minor": bonus_minor,
                    "principal_minor": principal_minor,
                    "tx_hash": tx_hash,
                    "source": "admin_recovery",
                },
                created_at=now,
            )
            if promo_skip_reason is not None:
                await self._queue_notification(
                    connection,
                    user_id=int(invoice["user_id"]),
                    category="deposit",
                    event_type="promo_skipped",
                    title="Промокод не применён",
                    body=(
                        "Промокод к этому пополнению не применён — бонус, показанный "
                        "в счёте, не зачислен. Депозит открыт на фактическую сумму "
                        "перевода."
                    ),
                    telegram_html=(
                        "⚠️ <b>Промокод не применён</b>\n\n"
                        "Бонус, показанный в счёте, не зачислен — депозит открыт "
                        "на фактическую сумму перевода."
                    ),
                    dedupe_key=f"deposit-promo-skipped:{deposit_id}",
                    data={
                        "target_view": "assets",
                        "deposit_id": deposit_id,
                        "promo_skip_reason": promo_skip_reason,
                    },
                    created_at=now,
                )

            return {
                "deposit_id": deposit_id,
                "invoice_id": int(invoice_id),
                "chain_deposit_id": int(chain_deposit_id),
                "principal_minor": principal_minor,
                "bonus_minor": bonus_minor,
                "tx_hash": tx_hash,
                "reused": False,
            }

    async def apply_transfer(self, transfer: TransferEvent) -> dict[str, object]:
        now = int(time.time())
        async with self.transaction() as connection:
            try:
                cursor = await connection.execute(
                    """
                    INSERT INTO chain_deposits(
                        chain_id, tx_hash, log_index, block_number, from_address,
                        to_address, amount_atomic, amount_minor, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transfer.chain_id,
                        transfer.tx_hash,
                        transfer.log_index,
                        transfer.block_number,
                        transfer.from_address,
                        transfer.to_address,
                        str(transfer.amount_atomic),
                        transfer.amount_minor,
                        now,
                    ),
                )
            except aiosqlite.IntegrityError:
                return {"duplicate": True, "matched": False}
            chain_deposit_id = int(cursor.lastrowid)

            cursor = await connection.execute(
                """
                SELECT invoice.*, users.payout_address
                FROM deposit_invoices invoice
                JOIN users ON users.telegram_id = invoice.user_id
                WHERE invoice.status = 'pending'
                  AND invoice.exact_minor = ?
                  AND invoice.expires_at >= ?
                  AND users.blocked = 0
                ORDER BY invoice.id
                LIMIT 1
                """,
                (transfer.amount_minor, now),
            )
            invoice = await cursor.fetchone()
            if not invoice or not invoice["payout_address"]:
                await connection.execute(
                    "INSERT INTO audit_events(event_type, details, created_at) "
                    "VALUES ('unmatched_deposit', ?, ?)",
                    (f"{transfer.tx_hash}:{transfer.log_index}", now),
                )
                return {"duplicate": False, "matched": False}

            await connection.execute(
                """
                UPDATE deposit_invoices
                SET status = 'paid', tx_hash = ?, paid_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (transfer.tx_hash, now, invoice["id"]),
            )
            await connection.execute(
                "UPDATE chain_deposits SET invoice_id = ?, matched = 1 WHERE id = ?",
                (invoice["id"], chain_deposit_id),
            )

            bonus_minor = 0
            promo_code_id = invoice["promo_code_id"]
            promo_code_id = int(promo_code_id) if promo_code_id is not None else None
            skipped_promo_code_id = promo_code_id
            promo_skip_reason: str | None = None
            if promo_code_id is not None:
                bonus_minor, promo_skip_reason = await self._reserve_promo_redemption(
                    connection,
                    promo_code_id=promo_code_id,
                    user_id=int(invoice["user_id"]),
                    base_minor=int(invoice["base_minor"]),
                    now=now,
                )
                if promo_skip_reason is not None:
                    bonus_minor = 0
                    promo_code_id = None

            principal_minor = int(transfer.amount_minor) + bonus_minor

            cursor = await connection.execute(
                """
                INSERT INTO deposits(
                    user_id, invoice_id, principal_minor, payout_address,
                    next_payout_at, opened_at, bonus_minor, promo_code_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice["user_id"],
                    invoice["id"],
                    principal_minor,
                    invoice["payout_address"],
                    now + 86_400,
                    now,
                    bonus_minor,
                    promo_code_id,
                ),
            )
            deposit_id = int(cursor.lastrowid)

            if promo_code_id is not None:
                try:
                    await connection.execute(
                        """
                        INSERT INTO promo_redemptions(
                            promo_code_id, user_id, deposit_id, invoice_id,
                            bonus_minor, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            promo_code_id,
                            int(invoice["user_id"]),
                            deposit_id,
                            int(invoice["id"]),
                            bonus_minor,
                            now,
                        ),
                    )
                except aiosqlite.IntegrityError:
                    # Give the reserved slot back and strip the bonus instead of
                    # rolling back the credited transfer.
                    await connection.execute(
                        "UPDATE promo_codes SET redemption_count = redemption_count - 1 "
                        "WHERE id = ? AND redemption_count > 0",
                        (promo_code_id,),
                    )
                    await connection.execute(
                        "UPDATE deposits SET principal_minor = ?, bonus_minor = 0, "
                        "promo_code_id = NULL WHERE id = ?",
                        (int(transfer.amount_minor), deposit_id),
                    )
                    principal_minor = int(transfer.amount_minor)
                    bonus_minor = 0
                    promo_code_id = None
                    promo_skip_reason = "promo_redemption_conflict"

            if promo_skip_reason is not None:
                await connection.execute(
                    "INSERT INTO audit_events(event_type, details, created_at) "
                    "VALUES ('promo_redeem_skipped', ?, ?)",
                    (
                        f"deposit={deposit_id};invoice={int(invoice['id'])};"
                        f"promo={skipped_promo_code_id};reason={promo_skip_reason}",
                        now,
                    ),
                )

            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) "
                "VALUES ('deposit_opened', ?, ?)",
                (f"deposit={deposit_id};tx={transfer.tx_hash}", now),
            )
            amount_text = minor_to_text(int(transfer.amount_minor))
            principal_text = minor_to_text(principal_minor)
            if bonus_minor > 0:
                bonus_text = minor_to_text(bonus_minor)
                body = (
                    f"Зачислено {amount_text} USDT + бонус {bonus_text} USDT = "
                    f"{principal_text} USDT. Депозит #{deposit_id} активирован."
                )
                telegram_html = (
                    "✅ <b>Пополнение подтверждено</b>\n\n"
                    f"💰 Зачислено: <b>{amount_text} USDT</b>\n"
                    f"🎁 Бонус: <b>+{bonus_text} USDT</b>\n"
                    f"📦 Депозит: <b>#{deposit_id}</b> на сумму <b>{principal_text} USDT</b>\n"
                    "⏱ Первая выплата — через 24 часа."
                )
            else:
                body = f"Зачислено {principal_text} USDT. Депозит #{deposit_id} активирован."
                telegram_html = (
                    "✅ <b>Пополнение подтверждено</b>\n\n"
                    f"💰 Зачислено: <b>{principal_text} USDT</b>\n"
                    f"📦 Депозит: <b>#{deposit_id}</b>\n"
                    "⏱ Первая выплата — через 24 часа."
                )
            await self._queue_notification(
                connection,
                user_id=int(invoice["user_id"]),
                category="deposit",
                event_type="deposit_confirmed",
                title="Пополнение подтверждено",
                body=body,
                telegram_html=telegram_html,
                dedupe_key=f"deposit-confirmed:{deposit_id}",
                data={
                    "target_view": "assets",
                    "deposit_id": deposit_id,
                    "amount_minor": int(transfer.amount_minor),
                    "bonus_minor": bonus_minor,
                    "principal_minor": principal_minor,
                    "tx_hash": str(transfer.tx_hash),
                },
                created_at=now,
            )
            if promo_skip_reason is not None:
                await self._queue_notification(
                    connection,
                    user_id=int(invoice["user_id"]),
                    category="deposit",
                    event_type="promo_skipped",
                    title="Промокод не применён",
                    body=(
                        "Промокод к этому пополнению не применён — бонус, показанный "
                        "в счёте, не зачислен. Депозит открыт на фактическую сумму "
                        "перевода."
                    ),
                    telegram_html=(
                        "⚠️ <b>Промокод не применён</b>\n\n"
                        "Бонус, показанный в счёте, не зачислен — депозит открыт "
                        "на фактическую сумму перевода."
                    ),
                    dedupe_key=f"deposit-promo-skipped:{deposit_id}",
                    data={
                        "target_view": "assets",
                        "deposit_id": deposit_id,
                        "promo_skip_reason": promo_skip_reason,
                    },
                    created_at=now,
                )
            return {
                "duplicate": False,
                "matched": True,
                "user_id": int(invoice["user_id"]),
                "deposit_id": deposit_id,
                "amount_minor": transfer.amount_minor,
                "principal_minor": principal_minor,
                "bonus_minor": bonus_minor,
                "promo_code_id": promo_code_id,
                "promo_skipped_reason": promo_skip_reason,
            }

    async def get_sync_height(self, key: str) -> int | None:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute("SELECT value FROM sync_state WHERE key = ?", (key,))
            row = await cursor.fetchone()
        return int(row["value"]) if row else None

    async def set_sync_height(self, key: str, value: int) -> None:
        now = int(time.time())
        async with self.transaction() as connection:
            await connection.execute(
                """
                INSERT INTO sync_state(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, str(value), now),
            )

    async def _qualification(
        self,
        connection: aiosqlite.Connection,
        user_id: int,
        level_index: int,
    ) -> bool:
        cursor = await connection.execute(
            "SELECT unlocked_level FROM referral_level_overrides WHERE user_id = ?",
            (user_id,),
        )
        manual = await cursor.fetchone()
        if manual and int(manual["unlocked_level"]) >= level_index + 1:
            return True
        cursor = await connection.execute(
            "SELECT COALESCE(SUM(principal_minor), 0) AS value "
            "FROM deposits WHERE user_id = ? AND status = 'active'",
            (user_id,),
        )
        personal = int((await cursor.fetchone())["value"])
        cursor = await connection.execute(
            """
            SELECT COALESCE(SUM(deposits.principal_minor), 0) AS value
            FROM deposits
            JOIN users ON users.telegram_id = deposits.user_id
            WHERE users.referrer_id = ? AND deposits.status = 'active'
            """,
            (user_id,),
        )
        first_line = int((await cursor.fetchone())["value"])
        personal_required = self.business.referral_personal_thresholds_usdt[level_index] * MINOR_FACTOR
        line_required = self.business.referral_line_thresholds_usdt[level_index] * MINOR_FACTOR
        return personal >= personal_required and first_line >= line_required

    async def _referral_available_minor(
        self,
        connection: aiosqlite.Connection,
        user_id: int,
    ) -> int:
        cursor = await connection.execute(
            "SELECT COALESCE(SUM(amount_minor),0) AS value FROM referral_accruals "
            "WHERE referrer_id = ? AND withdrawal_payout_id IS NULL",
            (user_id,),
        )
        organic = int((await cursor.fetchone())["value"] or 0)
        cursor = await connection.execute(
            "SELECT COALESCE(SUM(delta_minor),0) AS value FROM referral_balance_adjustments "
            "WHERE user_id = ? AND withdrawal_payout_id IS NULL",
            (user_id,),
        )
        manual = int((await cursor.fetchone())["value"] or 0)
        return max(0, organic + manual)

    async def ensure_missing_principal_payouts(self) -> int:
        """Queue principal for active deposits whose final profit was already scheduled before V5."""
        now = int(time.time())
        inserted = 0
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM deposits
                WHERE status = 'active'
                  AND scheduled_days >= ?
                ORDER BY id
                """,
                (self.business.payout_days,),
            )
            for deposit in await cursor.fetchall():
                cursor = await connection.execute(
                    """
                    INSERT OR IGNORE INTO payouts(
                        idempotency_key, user_id, source_deposit_id, kind, subtype,
                        payout_day, amount_minor, address, created_at, updated_at
                    ) VALUES (?, ?, ?, 'daily', 'principal', ?, ?, ?, ?, ?)
                    """,
                    (
                        f"principal:{deposit['id']}",
                        deposit["user_id"],
                        deposit["id"],
                        self.business.payout_days,
                        int(deposit["principal_minor"]),
                        deposit["payout_address"],
                        now,
                        now,
                    ),
                )
                inserted += int(bool(cursor.rowcount))
        return inserted

    async def schedule_due_payouts(self, limit: int = 50) -> int:
        now = int(time.time())
        scheduled = 0
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM deposits
                WHERE status = 'active'
                  AND scheduled_days < ?
                  AND next_payout_at <= ?
                ORDER BY next_payout_at, id
                LIMIT ?
                """,
                (self.business.payout_days, now, limit),
            )
            deposits = await cursor.fetchall()
            for deposit in deposits:
                day = int(deposit["scheduled_days"]) + 1
                amount_minor = calculate_bps(
                    int(deposit["principal_minor"]),
                    self.business.daily_profit_bps,
                )
                cursor = await connection.execute(
                    """
                    INSERT OR IGNORE INTO payouts(
                        idempotency_key, user_id, source_deposit_id, kind,
                        payout_day, amount_minor, address, created_at, updated_at
                    ) VALUES (?, ?, ?, 'daily', ?, ?, ?, ?, ?)
                    """,
                    (
                        f"daily:{deposit['id']}:{day}",
                        deposit["user_id"],
                        deposit["id"],
                        day,
                        amount_minor,
                        deposit["payout_address"],
                        now,
                        now,
                    ),
                )
                if not cursor.rowcount:
                    continue
                scheduled += 1

                if day == self.business.payout_days:
                    cursor = await connection.execute(
                        """
                        INSERT OR IGNORE INTO payouts(
                            idempotency_key, user_id, source_deposit_id, kind, subtype,
                            payout_day, amount_minor, address, created_at, updated_at
                        ) VALUES (?, ?, ?, 'daily', 'principal', ?, ?, ?, ?, ?)
                        """,
                        (
                            f"principal:{deposit['id']}",
                            deposit["user_id"],
                            deposit["id"],
                            day,
                            int(deposit["principal_minor"]),
                            deposit["payout_address"],
                            now,
                            now,
                        ),
                    )
                    if cursor.rowcount:
                        scheduled += 1

                source_user_id = int(deposit["user_id"])
                cursor = await connection.execute(
                    "SELECT referrer_id FROM users WHERE telegram_id = ?",
                    (source_user_id,),
                )
                source_user = await cursor.fetchone()
                ancestor_id = int(source_user["referrer_id"]) if source_user and source_user["referrer_id"] else None
                for level_index, percent_bps in enumerate(self.business.referral_level_bps):
                    if ancestor_id is None:
                        break
                    cursor = await connection.execute(
                        "SELECT payout_address, referrer_id, blocked FROM users WHERE telegram_id = ?",
                        (ancestor_id,),
                    )
                    ancestor = await cursor.fetchone()
                    if not ancestor:
                        break
                    reward_minor = calculate_bps(amount_minor, percent_bps)
                    if (
                        reward_minor > 0
                        and not ancestor["blocked"]
                        and await self._qualification(connection, ancestor_id, level_index)
                    ):
                        accrual_cursor = await connection.execute(
                            """
                            INSERT OR IGNORE INTO referral_accruals(
                                referrer_id, referred_id, source_deposit_id,
                                source_payout_day, level, percent_bps,
                                amount_minor, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                ancestor_id,
                                source_user_id,
                                deposit["id"],
                                day,
                                level_index + 1,
                                percent_bps,
                                reward_minor,
                                now,
                            ),
                        )
                        if accrual_cursor.rowcount:
                            source_cursor = await connection.execute(
                                "SELECT username, first_name FROM users WHERE telegram_id = ?",
                                (source_user_id,),
                            )
                            source_row = await source_cursor.fetchone()
                            source_label = (
                                f"@{source_row['username']}"
                                if source_row and source_row["username"]
                                else (str(source_row["first_name"] or "").strip() if source_row else "")
                            ) or f"ID {source_user_id}"
                            available_minor = await self._referral_available_minor(
                                connection, ancestor_id
                            )
                            reward_text = minor_to_text(int(reward_minor))
                            available_text = minor_to_text(available_minor)
                            await self._queue_notification(
                                connection,
                                user_id=ancestor_id,
                                category="partner",
                                event_type="referral_accrual",
                                title="Партнёрское начисление",
                                body=(
                                    f"+{reward_text} USDT · уровень {level_index + 1}. "
                                    f"Доступно к выводу {available_text} USDT."
                                ),
                                telegram_html=(
                                    "💎 <b>Партнёрское начисление</b>\n\n"
                                    f"➕ <b>+{reward_text} USDT</b>\n"
                                    f"📊 Уровень: <b>{level_index + 1}</b>\n"
                                    f"👤 Партнёр: <b>{html.escape(source_label)}</b>\n"
                                    f"💼 Доступно к выводу: <b>{available_text} USDT</b>"
                                ),
                                dedupe_key=(
                                    f"referral-accrual:{deposit['id']}:{day}:{level_index + 1}"
                                ),
                                data={
                                    "target_view": "team",
                                    "level": level_index + 1,
                                    "amount_minor": int(reward_minor),
                                    "available_minor": available_minor,
                                    "referred_id": source_user_id,
                                },
                                created_at=now,
                            )
                    ancestor_id = int(ancestor["referrer_id"]) if ancestor["referrer_id"] else None

                await connection.execute(
                    """
                    UPDATE deposits
                    SET scheduled_days = ?, next_payout_at = next_payout_at + 86400
                    WHERE id = ? AND scheduled_days = ?
                    """,
                    (day, deposit["id"], day - 1),
                )
        return scheduled

    async def get_next_payout(self) -> dict[str, object] | None:
        rows = await self.list_open_payouts(limit=1)
        return rows[0] if rows else None

    async def list_open_payouts(self, *, limit: int = 50) -> list[dict[str, object]]:
        """Return in-flight payouts: broadcast/signed first, then queued."""
        connection = self._connection()
        capped = max(1, min(int(limit), 200))
        async with self._lock:
            cursor = await connection.execute(
                """
                SELECT * FROM payouts
                WHERE status IN ('broadcast', 'signed', 'queued')
                ORDER BY CASE status
                    WHEN 'broadcast' THEN 0
                    WHEN 'signed' THEN 1
                    ELSE 2
                END, id
                LIMIT ?
                """,
                (capped,),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def mark_payout_signed(
        self,
        payout_id: int,
        tx_hash: str,
        raw_transaction: str,
        nonce: int,
    ) -> None:
        async with self.transaction() as connection:
            await connection.execute(
                """
                UPDATE payouts
                SET status = 'signed', tx_hash = ?, raw_transaction = ?, nonce = ?,
                    attempts = attempts + 1, last_error = NULL, updated_at = ?,
                    status_changed_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (tx_hash, raw_transaction, nonce, int(time.time()), int(time.time()), payout_id),
            )

    async def mark_payout_broadcast(self, payout_id: int) -> None:
        async with self.transaction() as connection:
            now = int(time.time())
            await connection.execute(
                "UPDATE payouts SET status = 'broadcast', updated_at = ?, "
                "status_changed_at = CASE WHEN status = 'signed' THEN ? ELSE COALESCE(status_changed_at, ?) END "
                "WHERE id = ? AND status IN ('signed', 'broadcast')",
                (now, now, now, payout_id),
            )

    async def record_payout_error(self, payout_id: int, error: str) -> None:
        async with self.transaction() as connection:
            await connection.execute(
                "UPDATE payouts SET last_error = ?, updated_at = ? "
                "WHERE id = ? AND status IN ('signed', 'broadcast')",
                (error[:1000], int(time.time()), payout_id),
            )

    async def mark_payout_failed(self, payout_id: int, error: str) -> None:
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute("SELECT * FROM payouts WHERE id = ?", (payout_id,))
            payout = await cursor.fetchone()
            if not payout:
                return
            was_failed = str(payout["status"]) == "failed"
            await connection.execute(
                "UPDATE payouts SET status = 'failed', last_error = ?, updated_at = ?, status_changed_at = ? WHERE id = ?",
                (error[:1000], now, now, payout_id),
            )
            if not was_failed and int(payout["admin_test"] or 0) == 0:
                amount_text = minor_to_text(int(payout["amount_minor"]))
                await self._queue_notification(
                    connection,
                    user_id=int(payout["user_id"]),
                    category="payout",
                    event_type="payout_failed",
                    title="Выплата требует внимания",
                    body=f"Выплата {amount_text} USDT не отправлена из-за технической ошибки. Заявка сохранена.",
                    telegram_html=(
                        "⚠️ <b>Выплата требует внимания</b>\n\n"
                        f"Сумма: <b>{amount_text} USDT</b>\n"
                        "Транзакция не была завершена из-за технической ошибки. "
                        "Заявка сохранена в NOVERA и не потеряна."
                    ),
                    dedupe_key=f"payout-failed:{payout_id}:{int(payout['attempts'] or 0)}",
                    data={"target_view": "history", "payout_id": int(payout_id)},
                    created_at=now,
                )

    async def mark_payout_confirmed(self, payout_id: int, tx_hash: str) -> dict[str, object] | None:
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute("SELECT * FROM payouts WHERE id = ?", (payout_id,))
            payout = await cursor.fetchone()
            if not payout:
                return None
            if payout["status"] == "confirmed":
                return dict(payout)
            await connection.execute(
                """
                UPDATE payouts
                SET status = 'confirmed', tx_hash = ?, raw_transaction = NULL,
                    last_error = NULL, confirmed_at = ?, updated_at = ?,
                    status_changed_at = ?
                WHERE id = ?
                """,
                (tx_hash, now, now, now, payout_id),
            )
            if int(payout["admin_test"] or 0) == 1:
                await connection.execute(
                    "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                    (
                        "admin_test_payout_confirmed",
                        f"admin={payout['user_id']};payout={payout_id};amount_minor={payout['amount_minor']};address={payout['address']};tx={tx_hash}",
                        now,
                    ),
                )

            if payout["kind"] == "daily" and payout["source_deposit_id"]:
                deposit_id = int(payout["source_deposit_id"])
                if str(payout["subtype"] or "") != "principal":
                    await connection.execute(
                        """
                        UPDATE deposits
                        SET paid_days = paid_days + 1
                        WHERE id = ? AND status = 'active'
                        """,
                        (deposit_id,),
                    )
                await connection.execute(
                    """
                    UPDATE deposits
                    SET status = 'completed', completed_at = ?
                    WHERE id = ?
                      AND status = 'active'
                      AND paid_days >= ?
                      AND EXISTS (
                          SELECT 1 FROM payouts
                          WHERE source_deposit_id = ?
                            AND subtype = 'principal'
                            AND status = 'confirmed'
                      )
                    """,
                    (now, deposit_id, self.business.payout_days, deposit_id),
                )
            if int(payout["admin_test"] or 0) == 0:
                amount_text = minor_to_text(int(payout["amount_minor"]))
                kind = str(payout["kind"] or "")
                subtype = str(payout["subtype"] or "")
                if kind == "referral":
                    title = "Партнёрский вывод подтверждён"
                    body = f"{amount_text} USDT отправлено на ваш кошелёк."
                    telegram_html = (
                        "🤝 <b>Партнёрский вывод подтверждён</b>\n\n"
                        f"💰 Сумма: <b>{amount_text} USDT</b>\n"
                        "✅ Транзакция подтверждена сетью BNB Smart Chain."
                    )
                    target_view = "team"
                    event_type = "referral_withdrawal_confirmed"
                elif subtype == "principal":
                    title = "Депозит возвращён"
                    body = f"{amount_text} USDT тела депозита возвращено на ваш кошелёк."
                    telegram_html = (
                        "✅ <b>Тело депозита возвращено</b>\n\n"
                        f"💰 Сумма: <b>{amount_text} USDT</b>\n"
                        "Цикл депозита завершён."
                    )
                    target_view = "assets"
                    event_type = "principal_return_confirmed"
                else:
                    payout_day = int(payout["payout_day"] or 0)
                    title = "Ежедневная выплата подтверждена"
                    body = f"+{amount_text} USDT отправлено на ваш кошелёк. День {payout_day}."
                    telegram_html = (
                        "💸 <b>Ежедневная выплата подтверждена</b>\n\n"
                        f"➕ <b>+{amount_text} USDT</b>\n"
                        f"📅 День: <b>{payout_day}</b>\n"
                        "✅ Транзакция подтверждена сетью BNB Smart Chain."
                    )
                    target_view = "history"
                    event_type = "daily_payout_confirmed"
                await self._queue_notification(
                    connection,
                    user_id=int(payout["user_id"]),
                    category="payout",
                    event_type=event_type,
                    title=title,
                    body=body,
                    telegram_html=telegram_html,
                    dedupe_key=f"payout-confirmed:{payout_id}",
                    data={
                        "target_view": target_view,
                        "payout_id": int(payout_id),
                        "amount_minor": int(payout["amount_minor"]),
                        "tx_hash": str(tx_hash),
                    },
                    created_at=now,
                )
            cursor = await connection.execute("SELECT * FROM payouts WHERE id = ?", (payout_id,))
            return dict(await cursor.fetchone())

    async def retry_payout(self, payout_id: int) -> bool:
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                UPDATE payouts
                SET status = 'queued', tx_hash = NULL, raw_transaction = NULL,
                    nonce = NULL, last_error = NULL, updated_at = ?, status_changed_at = ?
                WHERE id = ? AND status = 'failed'
                """,
                (int(time.time()), int(time.time()), payout_id),
            )
            return bool(cursor.rowcount)

    async def bootstrap(self, user_id: int) -> dict[str, object]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
            user = await cursor.fetchone()
            if not user:
                raise RepositoryError("User not found")
            cursor = await connection.execute(
                """
                SELECT ref.telegram_id, ref.username, ref.first_name
                FROM users AS current
                LEFT JOIN users AS ref ON ref.telegram_id = current.referrer_id
                WHERE current.telegram_id = ?
                """,
                (user_id,),
            )
            referrer_row = await cursor.fetchone()
            referrer = (
                dict(referrer_row)
                if referrer_row and referrer_row["telegram_id"] is not None
                else None
            )
            cursor = await connection.execute(
                "SELECT * FROM deposits WHERE user_id = ? ORDER BY opened_at DESC LIMIT 50",
                (user_id,),
            )
            deposits = [dict(row) for row in await cursor.fetchall()]
            cursor = await connection.execute(
                "SELECT * FROM payouts WHERE user_id = ? AND admin_test = 0 ORDER BY created_at DESC LIMIT 50",
                (user_id,),
            )
            payouts = [dict(row) for row in await cursor.fetchall()]
            cursor = await connection.execute(
                """
                WITH RECURSIVE tree(telegram_id, level) AS (
                    SELECT telegram_id, 1 FROM users WHERE referrer_id = ?
                    UNION ALL
                    SELECT users.telegram_id, tree.level + 1
                    FROM users JOIN tree ON users.referrer_id = tree.telegram_id
                    WHERE tree.level < 5
                )
                SELECT COUNT(*) AS count FROM tree
                """,
                (user_id,),
            )
            team_count = int((await cursor.fetchone())["count"] or 0)
            cursor = await connection.execute(
                """
                SELECT COALESCE(SUM(deposits.principal_minor), 0) AS value
                FROM deposits JOIN users ON users.telegram_id = deposits.user_id
                WHERE users.referrer_id = ? AND deposits.status = 'active'
                """,
                (user_id,),
            )
            first_line_minor = int((await cursor.fetchone())["value"] or 0)
            cursor = await connection.execute(
                """
                SELECT
                  (SELECT COALESCE(SUM(amount_minor),0) FROM referral_rewards WHERE referrer_id = ?) +
                  (SELECT COALESCE(SUM(amount_minor),0) FROM referral_accruals WHERE referrer_id = ?) AS value
                """,
                (user_id, user_id),
            )
            referral_earned_minor = int((await cursor.fetchone())["value"] or 0)
            referral_available_minor = await self._referral_available_minor(connection, user_id)
            cursor = await connection.execute(
                "SELECT COALESCE(SUM(amount_minor),0) AS value FROM payouts "
                "WHERE user_id = ? AND kind = 'referral' AND admin_test = 0 "
                "AND status IN ('queued','signed','broadcast')",
                (user_id,),
            )
            referral_pending_minor = int((await cursor.fetchone())["value"] or 0)
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM user_notifications WHERE user_id = ? AND read_at IS NULL",
                (user_id,),
            )
            notification_unread_count = int((await cursor.fetchone())["value"] or 0)
        return {
            "user": dict(user),
            "deposits": deposits,
            "payouts": payouts,
            "referrer": referrer,
            "notification_unread_count": notification_unread_count,
            "team": {
                "count": team_count,
                "first_line_minor": first_line_minor,
                "referral_earned_minor": referral_earned_minor,
                "referral_available_minor": referral_available_minor,
                "referral_pending_minor": referral_pending_minor,
            },
        }

    async def request_referral_withdrawal(
        self,
        user_id: int,
        idempotency_key: str,
        minimum_minor: int = MINOR_FACTOR,
    ) -> dict[str, object]:
        now = int(time.time())
        storage_key = f"referral-withdraw:{user_id}:{idempotency_key}"
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT * FROM payouts WHERE idempotency_key = ?",
                (storage_key,),
            )
            existing = await cursor.fetchone()
            if existing:
                payload = dict(existing)
                payload["reused"] = True
                return payload

            cursor = await connection.execute(
                "SELECT payout_address, blocked FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            user = await cursor.fetchone()
            if not user:
                raise RepositoryError("User not found")
            if user["blocked"]:
                raise RepositoryError("Account is blocked")
            address = str(user["payout_address"] or "").strip()
            if not address:
                raise RepositoryError("Set a payout wallet before withdrawing referral rewards")

            available_minor = await self._referral_available_minor(connection, user_id)
            if available_minor < int(minimum_minor):
                raise RepositoryError("Referral balance below minimum withdrawal")

            cursor = await connection.execute(
                """
                INSERT INTO payouts(
                    idempotency_key, user_id, kind, amount_minor, address,
                    created_at, updated_at
                ) VALUES (?, ?, 'referral', ?, ?, ?, ?)
                """,
                (storage_key, user_id, available_minor, address, now, now),
            )
            payout_id = int(cursor.lastrowid)
            await connection.execute(
                "UPDATE referral_accruals SET withdrawal_payout_id = ? "
                "WHERE referrer_id = ? AND withdrawal_payout_id IS NULL",
                (payout_id, user_id),
            )
            await connection.execute(
                "UPDATE referral_balance_adjustments SET withdrawal_payout_id = ? "
                "WHERE user_id = ? AND withdrawal_payout_id IS NULL",
                (payout_id, user_id),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "referral_withdrawal_requested",
                    f"user={user_id};payout={payout_id};amount_minor={available_minor}",
                    now,
                ),
            )
            amount_text = minor_to_text(available_minor)
            await self._queue_notification(
                connection,
                user_id=user_id,
                category="payout",
                event_type="referral_withdrawal_requested",
                title="Партнёрская выплата создана",
                body=f"{amount_text} USDT поставлено в очередь на вывод.",
                telegram_html=(
                    "⏳ <b>Партнёрская выплата создана</b>\n\n"
                    f"💰 Сумма: <b>{amount_text} USDT</b>\n"
                    f"👛 Адрес: <code>{html.escape(address)}</code>\n"
                    "Заявка передана автоматическому модулю выплат."
                ),
                dedupe_key=f"referral-withdrawal-requested:{payout_id}",
                data={
                    "target_view": "team",
                    "payout_id": payout_id,
                    "amount_minor": available_minor,
                },
                created_at=now,
            )
            cursor = await connection.execute("SELECT * FROM payouts WHERE id = ?", (payout_id,))
            payload = dict(await cursor.fetchone())
            payload["reused"] = False
            return payload

    async def request_admin_test_payout(
        self,
        admin_id: int,
        address: str,
        amount_minor: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        if int(amount_minor) < MINOR_FACTOR:
            raise RepositoryError("Minimum admin test payout is 1 USDT")
        now = int(time.time())
        storage_key = f"admin-test-payout:{admin_id}:{idempotency_key}"
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT * FROM payouts WHERE idempotency_key = ?",
                (storage_key,),
            )
            existing = await cursor.fetchone()
            if existing:
                payload = dict(existing)
                payload["reused"] = True
                return payload

            cursor = await connection.execute(
                "SELECT 1 FROM users WHERE telegram_id = ?",
                (admin_id,),
            )
            if await cursor.fetchone() is None:
                raise RepositoryError("User not found")

            cursor = await connection.execute(
                """
                INSERT INTO payouts(
                    idempotency_key, user_id, kind, admin_test, amount_minor,
                    address, created_at, updated_at
                ) VALUES (?, ?, 'referral', 1, ?, ?, ?, ?)
                """,
                (storage_key, admin_id, int(amount_minor), address, now, now),
            )
            payout_id = int(cursor.lastrowid)
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "admin_test_payout_requested",
                    f"admin={admin_id};payout={payout_id};amount_minor={int(amount_minor)};address={address}",
                    now,
                ),
            )
            cursor = await connection.execute("SELECT * FROM payouts WHERE id = ?", (payout_id,))
            payload = dict(await cursor.fetchone())
            payload["reused"] = False
            return payload

    async def admin_test_payouts(self, limit: int = 30) -> list[dict[str, object]]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                """
                SELECT payouts.*, users.username, users.first_name
                FROM payouts
                JOIN users ON users.telegram_id = payouts.user_id
                WHERE payouts.admin_test = 1
                ORDER BY payouts.created_at DESC, payouts.id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 100)),),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def team(self, user_id: int, today_start: int | None = None) -> dict[str, object]:
        connection = self._connection()
        now = int(time.time())
        day_start = max(0, min(int(today_start or (now - now % 86400)), now))
        async with self._lock:
            cursor = await connection.execute(
                """
                SELECT ref.telegram_id, ref.username, ref.first_name
                FROM users AS current
                LEFT JOIN users AS ref ON ref.telegram_id = current.referrer_id
                WHERE current.telegram_id = ?
                """,
                (user_id,),
            )
            referrer_row = await cursor.fetchone()
            referrer = (
                dict(referrer_row)
                if referrer_row and referrer_row["telegram_id"] is not None
                else None
            )

            cursor = await connection.execute(
                """
                WITH RECURSIVE tree(telegram_id, level) AS (
                    SELECT telegram_id, 1
                    FROM users
                    WHERE referrer_id = ?
                    UNION ALL
                    SELECT users.telegram_id, tree.level + 1
                    FROM users
                    JOIN tree ON users.referrer_id = tree.telegram_id
                    WHERE tree.level < 5
                )
                SELECT tree.level, users.telegram_id, users.username, users.first_name,
                       users.created_at, users.blocked,
                       COALESCE(SUM(deposits.principal_minor), 0) AS deposited_minor,
                       COALESCE(SUM(CASE WHEN deposits.status = 'active' THEN deposits.principal_minor ELSE 0 END), 0) AS active_minor,
                       COUNT(deposits.id) AS deposit_count
                FROM tree
                JOIN users ON users.telegram_id = tree.telegram_id
                LEFT JOIN deposits ON deposits.user_id = users.telegram_id
                GROUP BY tree.level, users.telegram_id
                ORDER BY tree.level, users.created_at DESC
                LIMIT 500
                """,
                (user_id,),
            )
            members = [dict(row) for row in await cursor.fetchall()]

            cursor = await connection.execute(
                """
                WITH RECURSIVE tree(telegram_id, level) AS (
                    SELECT telegram_id, 1 FROM users WHERE referrer_id = ?
                    UNION ALL
                    SELECT users.telegram_id, tree.level + 1
                    FROM users JOIN tree ON users.referrer_id = tree.telegram_id
                    WHERE tree.level < 5
                )
                SELECT tree.level,
                       COUNT(DISTINCT tree.telegram_id) AS member_count,
                       COALESCE(SUM(deposits.principal_minor), 0) AS deposited_minor,
                       COALESCE(SUM(CASE WHEN deposits.status = 'active' THEN deposits.principal_minor ELSE 0 END), 0) AS active_minor
                FROM tree
                LEFT JOIN deposits ON deposits.user_id = tree.telegram_id
                GROUP BY tree.level
                ORDER BY tree.level
                """,
                (user_id,),
            )
            level_rows = {int(row['level']): dict(row) for row in await cursor.fetchall()}

            cursor = await connection.execute(
                """
                SELECT level, COALESCE(SUM(amount_minor),0) AS earned_minor
                FROM (
                    SELECT level, amount_minor FROM referral_rewards WHERE referrer_id = ?
                    UNION ALL
                    SELECT level, amount_minor FROM referral_accruals WHERE referrer_id = ?
                )
                GROUP BY level
                """,
                (user_id, user_id),
            )
            rewards = {int(row['level']): dict(row) for row in await cursor.fetchall()}

            cursor = await connection.execute(
                "SELECT COALESCE(SUM(principal_minor),0) AS value FROM deposits "
                "WHERE user_id = ? AND status = 'active'",
                (user_id,),
            )
            personal_minor = int((await cursor.fetchone())["value"] or 0)
            cursor = await connection.execute(
                """
                SELECT COALESCE(SUM(deposits.principal_minor),0) AS value
                FROM deposits JOIN users ON users.telegram_id = deposits.user_id
                WHERE users.referrer_id = ? AND deposits.status = 'active'
                """,
                (user_id,),
            )
            line_minor = int((await cursor.fetchone())["value"] or 0)
            cursor = await connection.execute(
                """
                WITH RECURSIVE tree(telegram_id, level) AS (
                    SELECT telegram_id, 1 FROM users WHERE referrer_id = ?
                    UNION ALL
                    SELECT users.telegram_id, tree.level + 1
                    FROM users JOIN tree ON users.referrer_id = tree.telegram_id
                    WHERE tree.level < 5
                ) SELECT COUNT(*) AS count FROM tree
                """,
                (user_id,),
            )
            total_team_count = int((await cursor.fetchone())["count"] or 0)
            cursor = await connection.execute(
                """
                SELECT
                  (SELECT COALESCE(SUM(amount_minor),0) FROM referral_rewards WHERE referrer_id = ?) +
                  (SELECT COALESCE(SUM(amount_minor),0) FROM referral_accruals WHERE referrer_id = ?) AS value
                """,
                (user_id, user_id),
            )
            earned_minor = int((await cursor.fetchone())["value"] or 0)
            cursor = await connection.execute(
                """
                SELECT
                  (SELECT COALESCE(SUM(amount_minor),0) FROM referral_rewards WHERE referrer_id = ? AND created_at >= ?) +
                  (SELECT COALESCE(SUM(amount_minor),0) FROM referral_accruals WHERE referrer_id = ? AND created_at >= ?) AS value
                """,
                (user_id, day_start, user_id, day_start),
            )
            today_minor = int((await cursor.fetchone())["value"] or 0)
            available_minor = await self._referral_available_minor(connection, user_id)
            cursor = await connection.execute(
                "SELECT COALESCE(SUM(amount_minor),0) AS value FROM payouts "
                "WHERE user_id = ? AND kind = 'referral' AND admin_test = 0 "
                "AND status IN ('queued','signed','broadcast')",
                (user_id,),
            )
            pending_minor = int((await cursor.fetchone())["value"] or 0)
            cursor = await connection.execute(
                "SELECT COALESCE(SUM(amount_minor),0) AS value FROM payouts "
                "WHERE user_id = ? AND kind = 'referral' AND admin_test = 0 AND status = 'failed'",
                (user_id,),
            )
            failed_minor = int((await cursor.fetchone())["value"] or 0)
            cursor = await connection.execute(
                "SELECT COALESCE(SUM(amount_minor),0) AS value FROM payouts "
                "WHERE user_id = ? AND kind = 'referral' AND admin_test = 0 AND status = 'confirmed'",
                (user_id,),
            )
            withdrawn_minor = int((await cursor.fetchone())["value"] or 0)
            cursor = await connection.execute(
                "SELECT payout_address FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            user_row = await cursor.fetchone()
            payout_address = str(user_row["payout_address"] or "") if user_row else ""
            cursor = await connection.execute(
                "SELECT unlocked_level FROM referral_level_overrides WHERE user_id = ?",
                (user_id,),
            )
            manual_level_row = await cursor.fetchone()
            manual_level = int(manual_level_row["unlocked_level"]) if manual_level_row else 0

        levels = []
        for level in range(1, 6):
            row = level_rows.get(level, {})
            reward = rewards.get(level, {})
            levels.append({
                'level': level,
                'member_count': int(row.get('member_count') or 0),
                'deposited_minor': int(row.get('deposited_minor') or 0),
                'active_minor': int(row.get('active_minor') or 0),
                'earned_minor': int(reward.get('earned_minor') or 0),
                'pending_minor': 0,
            })

        qualified_levels = []
        for index in range(5):
            personal_required = int(self.business.referral_personal_thresholds_usdt[index]) * MINOR_FACTOR
            line_required = int(self.business.referral_line_thresholds_usdt[index]) * MINOR_FACTOR
            if personal_minor >= personal_required and line_minor >= line_required:
                qualified_levels.append(index + 1)
        organic_level = max(qualified_levels, default=0)
        current_level = max(organic_level, manual_level)
        next_goal = None
        for index in range(current_level, 5):
            personal_required = int(self.business.referral_personal_thresholds_usdt[index]) * MINOR_FACTOR
            line_required = int(self.business.referral_line_thresholds_usdt[index]) * MINOR_FACTOR
            if personal_minor < personal_required or line_minor < line_required:
                next_goal = {
                    'level': index + 1,
                    'rate_bps': int(self.business.referral_level_bps[index]),
                    'personal_required_minor': personal_required,
                    'line_required_minor': line_required,
                    'remaining_personal_minor': max(0, personal_required - personal_minor),
                    'remaining_line_minor': max(0, line_required - line_minor),
                }
                break

        return {
            'levels': levels,
            'members': members,
            'referrer': referrer,
            'stats': {
                'earned_minor': earned_minor,
                'today_minor': today_minor,
                'personal_minor': personal_minor,
                'line_minor': line_minor,
                'team_count': total_team_count,
                'current_level': current_level,
                'organic_level': organic_level,
                'manual_level': manual_level,
                'levels_total': 5,
                'available_minor': available_minor,
                'pending_minor': pending_minor,
                'failed_minor': failed_minor,
                'withdrawn_minor': withdrawn_minor,
                'minimum_withdrawal_minor': MINOR_FACTOR,
                'payout_address': payout_address,
                'next_goal': next_goal,
            },
        }

    async def is_granted_admin(self, telegram_id: int) -> bool:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT 1 FROM admin_grants WHERE telegram_id = ?",
                (telegram_id,),
            )
            return await cursor.fetchone() is not None

    async def admin_admins(self, bootstrap_ids: set[int] | frozenset[int]) -> list[dict[str, object]]:
        connection = self._connection()
        bootstrap = set(int(item) for item in bootstrap_ids)
        async with self._lock:
            cursor = await connection.execute(
                """
                SELECT users.telegram_id, users.username, users.first_name, users.created_at,
                       admin_grants.granted_by, admin_grants.created_at AS granted_at
                FROM admin_grants
                JOIN users ON users.telegram_id = admin_grants.telegram_id
                ORDER BY admin_grants.created_at DESC, users.telegram_id
                """
            )
            rows = [dict(row) for row in await cursor.fetchall()]
            seen = {int(row["telegram_id"]) for row in rows}
            result = [
                {**row, "source": "dynamic", "protected": False}
                for row in rows
            ]
            for telegram_id in sorted(bootstrap):
                cursor = await connection.execute(
                    "SELECT telegram_id, username, first_name, created_at FROM users WHERE telegram_id = ?",
                    (telegram_id,),
                )
                row = await cursor.fetchone()
                payload = dict(row) if row else {
                    "telegram_id": telegram_id,
                    "username": None,
                    "first_name": "",
                    "created_at": None,
                }
                payload.update({
                    "granted_by": None,
                    "granted_at": None,
                    "source": "bootstrap",
                    "protected": True,
                })
                if telegram_id in seen:
                    result = [item for item in result if int(item["telegram_id"]) != telegram_id]
                result.append(payload)
            result.sort(key=lambda item: (0 if item["source"] == "bootstrap" else 1, -(int(item.get("granted_at") or 0))))
            return result

    async def grant_admin(self, identifier: str, granted_by: int) -> dict[str, object]:
        value = identifier.strip().lstrip("@")
        if not value or len(value) > 64:
            raise RepositoryError("Invalid administrator identifier")
        async with self.transaction() as connection:
            if value.isdigit():
                cursor = await connection.execute(
                    "SELECT telegram_id, username, first_name, created_at FROM users WHERE telegram_id = ?",
                    (int(value),),
                )
            else:
                cursor = await connection.execute(
                    "SELECT telegram_id, username, first_name, created_at FROM users WHERE lower(username) = lower(?)",
                    (value,),
                )
            row = await cursor.fetchone()
            if row is None:
                raise RepositoryError("User not found")
            telegram_id = int(row["telegram_id"])
            now = int(time.time())
            await connection.execute(
                "INSERT OR IGNORE INTO admin_grants(telegram_id, granted_by, created_at) VALUES (?, ?, ?)",
                (telegram_id, granted_by, now),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES ('admin_granted', ?, ?)",
                (f"user={telegram_id};by={granted_by}", now),
            )
            result = dict(row)
            result.update({
                "granted_by": granted_by,
                "granted_at": now,
                "source": "dynamic",
                "protected": False,
            })
            return result

    async def revoke_admin(self, telegram_id: int, revoked_by: int) -> bool:
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "DELETE FROM admin_grants WHERE telegram_id = ?",
                (telegram_id,),
            )
            if not cursor.rowcount:
                return False
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES ('admin_revoked', ?, ?)",
                (f"user={telegram_id};by={revoked_by}", int(time.time())),
            )
            return True

    async def admin_summary(self) -> dict[str, int]:
        connection = self._connection()
        async with self._lock:
            result: dict[str, int] = {}
            queries = {
                "users": "SELECT COUNT(*) AS value FROM users",
                "active_users_7d": "SELECT COUNT(*) AS value FROM users WHERE last_seen_at >= strftime('%s','now') - 604800",
                "new_users_24h": "SELECT COUNT(*) AS value FROM users WHERE created_at >= strftime('%s','now') - 86400",
                "investors": "SELECT COUNT(DISTINCT user_id) AS value FROM deposits",
                "partners": "SELECT COUNT(*) AS value FROM users WHERE EXISTS (SELECT 1 FROM users AS child WHERE child.referrer_id = users.telegram_id)",
                "active_deposits": "SELECT COUNT(*) AS value FROM deposits WHERE status = 'active'",
                "active_principal_minor": "SELECT COALESCE(SUM(principal_minor), 0) AS value FROM deposits WHERE status = 'active'",
                "deposited_minor": "SELECT COALESCE(SUM(principal_minor), 0) AS value FROM deposits",
                "deposits_24h_minor": "SELECT COALESCE(SUM(principal_minor), 0) AS value FROM deposits WHERE opened_at >= strftime('%s','now') - 86400",
                "paid_minor": "SELECT COALESCE(SUM(amount_minor), 0) AS value FROM payouts WHERE admin_test = 0 AND status = 'confirmed'",
                "payouts_24h_minor": "SELECT COALESCE(SUM(amount_minor), 0) AS value FROM payouts WHERE admin_test = 0 AND status = 'confirmed' AND confirmed_at >= strftime('%s','now') - 86400",
                "queued_minor": "SELECT COALESCE(SUM(amount_minor), 0) AS value FROM payouts WHERE admin_test = 0 AND status IN ('queued','signed','broadcast')",
                "failed_payouts": "SELECT COUNT(*) AS value FROM payouts WHERE admin_test = 0 AND status = 'failed'",
                "referral_paid_minor": "SELECT COALESCE(SUM(amount_minor), 0) AS value FROM payouts WHERE kind = 'referral' AND admin_test = 0 AND status = 'confirmed'",
                "referral_pending_minor": "SELECT COALESCE(SUM(amount_minor), 0) AS value FROM payouts WHERE kind = 'referral' AND admin_test = 0 AND status IN ('queued','signed','broadcast')",
            }
            for key, sql in queries.items():
                cursor = await connection.execute(sql)
                result[key] = int((await cursor.fetchone())["value"] or 0)
        return result

    async def admin_users(self, query: str = "", limit: int = 50) -> list[dict[str, object]]:
        connection = self._connection()
        pattern = f"%{query.strip().lstrip('@')}%"
        async with self._lock:
            cursor = await connection.execute(
                """
                SELECT users.*,
                    COALESCE(SUM(deposits.principal_minor), 0) AS deposited_minor,
                    COUNT(deposits.id) AS deposit_count
                FROM users
                LEFT JOIN deposits ON deposits.user_id = users.telegram_id
                WHERE ? = '%%'
                   OR CAST(users.telegram_id AS TEXT) LIKE ?
                   OR COALESCE(users.username, '') LIKE ?
                GROUP BY users.telegram_id
                ORDER BY users.created_at DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def admin_operations(self, limit: int = 100) -> list[dict[str, object]]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                """
                SELECT payouts.*, users.username, users.first_name
                FROM payouts
                JOIN users ON users.telegram_id = payouts.user_id
                ORDER BY payouts.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def admin_deposits(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                """
                SELECT deposits.*, users.username, users.first_name,
                       deposit_invoices.tx_hash,
                       CASE WHEN admin_open.deposit_id IS NULL THEN 'chain' ELSE 'admin' END AS source,
                       admin_open.reason AS admin_reason,
                       admin_open.opened_by AS opened_by_admin
                FROM deposits
                JOIN users ON users.telegram_id = deposits.user_id
                JOIN deposit_invoices ON deposit_invoices.id = deposits.invoice_id
                LEFT JOIN admin_investment_openings AS admin_open ON admin_open.deposit_id = deposits.id
                WHERE ? IS NULL OR deposits.status = ?
                ORDER BY deposits.opened_at DESC
                LIMIT ?
                """,
                (status, status, limit),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def admin_user_detail(self, user_id: int) -> dict[str, object] | None:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            user = await cursor.fetchone()
            if not user:
                return None
            cursor = await connection.execute(
                "SELECT deposits.*, CASE WHEN admin_open.deposit_id IS NULL THEN 'chain' ELSE 'admin' END AS source, "
                "admin_open.reason AS admin_reason, admin_open.opened_by AS opened_by_admin "
                "FROM deposits LEFT JOIN admin_investment_openings AS admin_open ON admin_open.deposit_id = deposits.id "
                "WHERE deposits.user_id = ? ORDER BY deposits.opened_at DESC LIMIT 100",
                (user_id,),
            )
            deposits = [dict(row) for row in await cursor.fetchall()]
            cursor = await connection.execute(
                "SELECT * FROM payouts WHERE user_id = ? AND admin_test = 0 ORDER BY created_at DESC LIMIT 100",
                (user_id,),
            )
            payouts = [dict(row) for row in await cursor.fetchall()]
            cursor = await connection.execute(
                """
                WITH RECURSIVE tree(root_id, telegram_id, depth) AS (
                    SELECT u.telegram_id AS root_id, u.telegram_id, 0
                    FROM users AS u
                    WHERE u.referrer_id = ?
                    UNION ALL
                    SELECT tree.root_id, child.telegram_id, tree.depth + 1
                    FROM users AS child
                    JOIN tree ON child.referrer_id = tree.telegram_id
                    WHERE tree.depth < 5
                ),
                personal AS (
                    SELECT user_id, COALESCE(SUM(principal_minor), 0) AS personal_turnover_minor,
                           COUNT(id) AS deposit_count
                    FROM deposits
                    WHERE user_id IN (SELECT telegram_id FROM tree)
                    GROUP BY user_id
                ),
                structure AS (
                    SELECT tree.root_id,
                           COALESCE(SUM(CASE WHEN tree.depth > 0 THEN deposits.principal_minor ELSE 0 END), 0)
                             AS structure_turnover_minor,
                           COUNT(DISTINCT CASE WHEN tree.depth > 0 THEN tree.telegram_id END)
                             AS structure_member_count
                    FROM tree
                    LEFT JOIN deposits ON deposits.user_id = tree.telegram_id
                    GROUP BY tree.root_id
                )
                SELECT u.telegram_id, u.username, u.first_name, u.created_at,
                       COALESCE(personal.personal_turnover_minor, 0) AS personal_turnover_minor,
                       COALESCE(personal.deposit_count, 0) AS deposit_count,
                       COALESCE(structure.structure_turnover_minor, 0) AS structure_turnover_minor,
                       COALESCE(structure.structure_member_count, 0) AS structure_member_count
                FROM users AS u
                LEFT JOIN personal ON personal.user_id = u.telegram_id
                LEFT JOIN structure ON structure.root_id = u.telegram_id
                WHERE u.referrer_id = ?
                ORDER BY structure_turnover_minor DESC, personal_turnover_minor DESC, u.created_at DESC
                LIMIT 100
                """,
                (user_id, user_id),
            )
            partners = [dict(row) for row in await cursor.fetchall()]
            referrer = None
            if user['referrer_id'] is not None:
                cursor = await connection.execute(
                    "SELECT telegram_id, username, first_name FROM users WHERE telegram_id = ?",
                    (user['referrer_id'],),
                )
                row = await cursor.fetchone()
                if row:
                    referrer = dict(row)
            cursor = await connection.execute(
                "SELECT COALESCE(SUM(principal_minor), 0) AS deposited_minor, "
                "COALESCE(SUM(CASE WHEN status='active' THEN principal_minor ELSE 0 END), 0) AS active_minor, "
                "COUNT(*) AS deposit_count FROM deposits WHERE user_id = ?",
                (user_id,),
            )
            dep_stats = dict(await cursor.fetchone())
            cursor = await connection.execute(
                "SELECT COALESCE(SUM(CASE WHEN status='confirmed' THEN amount_minor ELSE 0 END), 0) AS paid_minor, "
                "COALESCE(SUM(CASE WHEN kind='referral' AND status='confirmed' THEN amount_minor ELSE 0 END), 0) AS referral_paid_minor "
                "FROM payouts WHERE user_id = ? AND admin_test = 0",
                (user_id,),
            )
            payout_stats = dict(await cursor.fetchone())
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT * FROM balance_adjustments WHERE user_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 30",
                (user_id,),
            )
            balance_adjustments = [dict(row) for row in await cursor.fetchall()]
            cursor = await connection.execute(
                """
                SELECT ra.*, 
                       old_user.username AS old_referrer_username,
                       old_user.first_name AS old_referrer_first_name,
                       new_user.username AS new_referrer_username,
                       new_user.first_name AS new_referrer_first_name
                FROM referrer_adjustments AS ra
                LEFT JOIN users AS old_user ON old_user.telegram_id = ra.old_referrer_id
                LEFT JOIN users AS new_user ON new_user.telegram_id = ra.new_referrer_id
                WHERE ra.user_id = ?
                ORDER BY ra.created_at DESC, ra.id DESC
                LIMIT 20
                """,
                (user_id,),
            )
            referrer_adjustments = [dict(row) for row in await cursor.fetchall()]
            referral_balance_minor = await self._referral_available_minor(connection, user_id)
            cursor = await connection.execute(
                "SELECT * FROM referral_balance_adjustments WHERE user_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 30",
                (user_id,),
            )
            referral_balance_adjustments = [dict(row) for row in await cursor.fetchall()]
            cursor = await connection.execute(
                "SELECT * FROM referral_level_overrides WHERE user_id = ?",
                (user_id,),
            )
            level_override_row = await cursor.fetchone()
            cursor = await connection.execute(
                "SELECT * FROM referral_level_adjustments WHERE user_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 30",
                (user_id,),
            )
            referral_level_adjustments = [dict(row) for row in await cursor.fetchall()]

        team_payload = await self.team(user_id)
        team_stats = dict(team_payload.get("stats") or {})
        partner_stats = {
            "earned_minor": int(team_stats.get("earned_minor") or 0),
            "today_minor": int(team_stats.get("today_minor") or 0),
            "available_minor": int(team_stats.get("available_minor") or 0),
            "personal_minor": int(team_stats.get("personal_minor") or 0),
            "line_minor": int(team_stats.get("line_minor") or 0),
            "team_count": int(team_stats.get("team_count") or 0),
            "current_level": int(team_stats.get("current_level") or 0),
            "levels_total": int(team_stats.get("levels_total") or 5),
        }

        return {
            "user": dict(user),
            "deposits": deposits,
            "payouts": payouts,
            "partners": partners,
            "partner_stats": partner_stats,
            "referrer": referrer,
            "stats": {**dep_stats, **payout_stats},
            "balance_adjustments": balance_adjustments,
            "referrer_adjustments": referrer_adjustments,
            "referral_balance_minor": referral_balance_minor,
            "referral_balance_adjustments": referral_balance_adjustments,
            "referral_level_override": dict(level_override_row) if level_override_row else None,
            "referral_level_adjustments": referral_level_adjustments,
        }

    @staticmethod
    def _admin_control_operation_key(
        kind: str, actor_id: int, user_id: int, idempotency_key: str
    ) -> str:
        clean = str(idempotency_key or "").strip()
        if not clean or len(clean) > 128:
            raise RepositoryError("Invalid Idempotency-Key")
        return f"admin-control:{kind}:{int(actor_id)}:{int(user_id)}:{clean}"

    async def _reuse_admin_control(
        self,
        connection: aiosqlite.Connection,
        *,
        operation_key: str,
        fingerprint: str,
    ) -> dict[str, object] | None:
        cursor = await connection.execute(
            "SELECT payload_fingerprint, result_json FROM admin_control_idempotency "
            "WHERE operation_key = ?",
            (operation_key,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        if str(row["payload_fingerprint"]) != fingerprint:
            raise RepositoryError("Idempotency key was already used")
        result = json.loads(str(row["result_json"]))
        if isinstance(result, dict):
            result["reused"] = True
            return result
        raise RepositoryError("Idempotency key was already used")

    async def _store_admin_control(
        self,
        connection: aiosqlite.Connection,
        *,
        operation_key: str,
        kind: str,
        actor_id: int,
        user_id: int,
        fingerprint: str,
        result: dict[str, object],
        created_at: int,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO admin_control_idempotency(
                operation_key, kind, actor_id, user_id, payload_fingerprint,
                result_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_key,
                kind,
                int(actor_id),
                int(user_id),
                fingerprint,
                json.dumps(result, separators=(",", ":"), sort_keys=True),
                int(created_at),
            ),
        )

    async def admin_set_referral_balance(
        self,
        user_id: int,
        new_balance_minor: int,
        changed_by: int,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        if new_balance_minor < 0:
            raise RepositoryError("Referral balance cannot be negative")
        clean_reason = reason.strip()[:500]
        if not clean_reason:
            raise RepositoryError("Referral balance adjustment reason is required")
        operation_key = self._admin_control_operation_key(
            "referral-balance", changed_by, user_id, idempotency_key
        )
        fingerprint = f"{int(new_balance_minor)}|{clean_reason}"
        now = int(time.time())
        async with self.transaction() as connection:
            reused = await self._reuse_admin_control(
                connection, operation_key=operation_key, fingerprint=fingerprint
            )
            if reused is not None:
                return reused
            cursor = await connection.execute(
                "SELECT 1 FROM users WHERE telegram_id = ?", (user_id,)
            )
            if await cursor.fetchone() is None:
                raise RepositoryError("User not found")
            old_balance = await self._referral_available_minor(connection, user_id)
            delta_minor = int(new_balance_minor) - old_balance
            await connection.execute(
                """
                INSERT INTO referral_balance_adjustments(
                    user_id, old_balance_minor, new_balance_minor, delta_minor,
                    reason, changed_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, old_balance, int(new_balance_minor), delta_minor,
                    clean_reason, changed_by, now,
                ),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "referral_balance_changed",
                    f"admin={changed_by};user={user_id};old={old_balance};new={int(new_balance_minor)};reason={clean_reason}",
                    now,
                ),
            )
            await self._queue_notification(
                connection,
                user_id=user_id,
                category="partner",
                event_type="referral_balance_adjusted",
                title="Партнёрский баланс изменён",
                body=f"Доступный баланс: {minor_to_text(int(new_balance_minor))} USDT.",
                telegram_html=(
                    "🤝 <b>Партнёрский баланс изменён</b>\n\n"
                    f"Доступно к выводу: <b>{minor_to_text(int(new_balance_minor))} USDT</b>"
                ),
                dedupe_key=f"referral-balance-adjusted:{user_id}:{now}:{secrets.token_hex(4)}",
                data={"target_view": "team", "balance_minor": int(new_balance_minor)},
                created_at=now,
            )
            result = {
                "old_balance_minor": old_balance,
                "new_balance_minor": int(new_balance_minor),
                "reused": False,
            }
            await self._store_admin_control(
                connection,
                operation_key=operation_key,
                kind="referral-balance",
                actor_id=changed_by,
                user_id=user_id,
                fingerprint=fingerprint,
                result=result,
                created_at=now,
            )
            return result

    async def admin_set_referral_level(
        self,
        user_id: int,
        unlocked_level: int,
        changed_by: int,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        if unlocked_level < 0 or unlocked_level > 5:
            raise RepositoryError("Referral level must be between 0 and 5")
        clean_reason = reason.strip()[:500]
        if not clean_reason:
            raise RepositoryError("Referral level adjustment reason is required")
        operation_key = self._admin_control_operation_key(
            "referral-level", changed_by, user_id, idempotency_key
        )
        fingerprint = f"{int(unlocked_level)}|{clean_reason}"
        now = int(time.time())
        async with self.transaction() as connection:
            reused = await self._reuse_admin_control(
                connection, operation_key=operation_key, fingerprint=fingerprint
            )
            if reused is not None:
                return reused
            cursor = await connection.execute(
                "SELECT 1 FROM users WHERE telegram_id = ?", (user_id,)
            )
            if await cursor.fetchone() is None:
                raise RepositoryError("User not found")
            cursor = await connection.execute(
                "SELECT unlocked_level FROM referral_level_overrides WHERE user_id = ?",
                (user_id,),
            )
            old_row = await cursor.fetchone()
            old_level = int(old_row["unlocked_level"]) if old_row else 0
            if unlocked_level == 0:
                await connection.execute(
                    "DELETE FROM referral_level_overrides WHERE user_id = ?", (user_id,)
                )
            else:
                await connection.execute(
                    """
                    INSERT INTO referral_level_overrides(
                        user_id, unlocked_level, reason, changed_by, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        unlocked_level=excluded.unlocked_level,
                        reason=excluded.reason,
                        changed_by=excluded.changed_by,
                        updated_at=excluded.updated_at
                    """,
                    (user_id, int(unlocked_level), clean_reason, changed_by, now),
                )
            await connection.execute(
                "INSERT INTO referral_level_adjustments(user_id,old_level,new_level,reason,changed_by,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (user_id, old_level, int(unlocked_level), clean_reason, changed_by, now),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "referral_level_override_changed",
                    f"admin={changed_by};user={user_id};old={old_level};new={int(unlocked_level)};reason={clean_reason}",
                    now,
                ),
            )
            if unlocked_level:
                title = "Открыт уровень партнёрской программы"
                body = f"Вам открыт доступ до {unlocked_level}-го уровня включительно."
                telegram_html = (
                    "🔓 <b>Открыт доступ к партнёрской программе</b>\n\n"
                    f"Доступны уровни: <b>1–{unlocked_level}</b>.\n"
                    "Настройка действует для будущих партнёрских начислений."
                )
            else:
                title = "Ручной доступ к уровням отключён"
                body = "Уровни снова определяются автоматически по условиям программы."
                telegram_html = (
                    "ℹ️ <b>Ручной доступ к уровням отключён</b>\n\n"
                    "Теперь уровни определяются автоматически по условиям партнёрской программы."
                )
            await self._queue_notification(
                connection,
                user_id=user_id,
                category="partner",
                event_type="referral_level_adjusted",
                title=title,
                body=body,
                telegram_html=telegram_html,
                dedupe_key=f"referral-level-adjusted:{user_id}:{now}:{secrets.token_hex(4)}",
                data={"target_view": "team", "manual_level": int(unlocked_level)},
                created_at=now,
            )
            result = {
                "old_level": old_level,
                "unlocked_level": int(unlocked_level),
                "reused": False,
            }
            await self._store_admin_control(
                connection,
                operation_key=operation_key,
                kind="referral-level",
                actor_id=changed_by,
                user_id=user_id,
                fingerprint=fingerprint,
                result=result,
                created_at=now,
            )
            return result

    async def admin_open_investment(
        self,
        user_id: int,
        principal_minor: int,
        changed_by: int,
        reason: str,
        operation_id: str,
    ) -> dict[str, object]:
        if principal_minor <= 0:
            raise RepositoryError("Investment amount must be positive")
        clean_reason = reason.strip()[:500]
        if not clean_reason:
            raise RepositoryError("Investment opening reason is required")
        clean_operation = operation_id.strip()
        if not clean_operation or len(clean_operation) > 80:
            raise RepositoryError("Invalid investment operation ID")
        operation_key = f"admin-investment:{changed_by}:{user_id}:{clean_operation}"
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT deposits.*, admin_open.operation_key
                FROM admin_investment_openings AS admin_open
                JOIN deposits ON deposits.id = admin_open.deposit_id
                WHERE admin_open.operation_key = ?
                """,
                (operation_key,),
            )
            existing = await cursor.fetchone()
            if existing:
                result = dict(existing)
                result["reused"] = True
                return result
            cursor = await connection.execute(
                "SELECT payout_address, blocked FROM users WHERE telegram_id = ?", (user_id,)
            )
            user = await cursor.fetchone()
            if user is None:
                raise RepositoryError("User not found")
            if bool(user["blocked"]):
                raise RepositoryError("Account is blocked")
            address = str(user["payout_address"] or "").strip()
            if not address:
                raise RepositoryError("User payout wallet is not configured")
            cursor = await connection.execute(
                """
                INSERT INTO deposit_invoices(
                    user_id, idempotency_key, base_minor, exact_minor,
                    status, expires_at, created_at, paid_at
                ) VALUES (?, ?, ?, ?, 'paid', ?, ?, ?)
                """,
                (user_id, operation_key, int(principal_minor), int(principal_minor), now, now, now),
            )
            invoice_id = int(cursor.lastrowid)
            cursor = await connection.execute(
                """
                INSERT INTO deposits(
                    user_id, invoice_id, principal_minor, payout_address,
                    next_payout_at, opened_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, invoice_id, int(principal_minor), address, now + 86_400, now),
            )
            deposit_id = int(cursor.lastrowid)
            await connection.execute(
                "INSERT INTO admin_investment_openings(deposit_id,user_id,operation_key,reason,opened_by,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (deposit_id, user_id, operation_key, clean_reason, changed_by, now),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "admin_investment_opened",
                    f"admin={changed_by};user={user_id};deposit={deposit_id};amount={int(principal_minor)};reason={clean_reason}",
                    now,
                ),
            )
            amount_text = minor_to_text(int(principal_minor))
            await self._queue_notification(
                connection,
                user_id=user_id,
                category="deposit",
                event_type="admin_investment_opened",
                title="Инвестиция открыта",
                body=f"Администратор открыл инвестицию #{deposit_id} на {amount_text} USDT.",
                telegram_html=(
                    "✅ <b>Инвестиция открыта</b>\n\n"
                    f"💰 Сумма: <b>{amount_text} USDT</b>\n"
                    f"📦 Инвестиция: <b>#{deposit_id}</b>\n"
                    "⏱ Первая выплата — через 24 часа."
                ),
                dedupe_key=f"admin-investment-opened:{deposit_id}",
                data={
                    "target_view": "assets",
                    "deposit_id": deposit_id,
                    "amount_minor": int(principal_minor),
                    "source": "admin",
                },
                created_at=now,
            )
            cursor = await connection.execute("SELECT * FROM deposits WHERE id = ?", (deposit_id,))
            result = dict(await cursor.fetchone())
            result["reused"] = False
            return result

    async def admin_close_investment(
        self,
        user_id: int,
        deposit_id: int,
        changed_by: int,
        reason: str,
        operation_id: str,
    ) -> dict[str, object]:
        clean_reason = reason.strip()[:500]
        if not clean_reason:
            raise RepositoryError("Investment close reason is required")
        clean_operation = operation_id.strip()
        if not clean_operation or len(clean_operation) > 80:
            raise RepositoryError("Invalid investment close operation ID")
        operation_key = f"admin-investment-close:{changed_by}:{user_id}:{deposit_id}:{clean_operation}"
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT deposits.*, closures.operation_key, closures.cancelled_payouts
                FROM admin_investment_closures AS closures
                JOIN deposits ON deposits.id = closures.deposit_id
                WHERE closures.operation_key = ?
                """,
                (operation_key,),
            )
            existing = await cursor.fetchone()
            if existing:
                result = dict(existing)
                result["reused"] = True
                result["cancelled_payouts"] = int(existing["cancelled_payouts"] or 0)
                return result

            cursor = await connection.execute(
                "SELECT * FROM deposits WHERE id = ? AND user_id = ?",
                (int(deposit_id), int(user_id)),
            )
            deposit = await cursor.fetchone()
            if deposit is None:
                raise RepositoryError("Deposit not found")
            if str(deposit["status"]) != "active":
                raise RepositoryError("Only active investments can be closed")

            cursor = await connection.execute(
                """
                SELECT COUNT(*) AS value FROM payouts
                WHERE source_deposit_id = ?
                  AND status IN ('signed', 'broadcast')
                """,
                (int(deposit_id),),
            )
            in_flight = int((await cursor.fetchone())["value"] or 0)
            if in_flight:
                raise RepositoryError(
                    "Investment has in-flight payouts; wait until they confirm or fail"
                )

            cursor = await connection.execute(
                """
                UPDATE payouts
                SET status = 'failed',
                    last_error = ?,
                    updated_at = ?,
                    status_changed_at = ?
                WHERE source_deposit_id = ?
                  AND status = 'queued'
                """,
                (
                    "Cancelled by administrator",
                    now,
                    now,
                    int(deposit_id),
                ),
            )
            cancelled = int(cursor.rowcount or 0)

            await connection.execute(
                """
                UPDATE deposits
                SET status = 'completed', completed_at = ?
                WHERE id = ? AND status = 'active'
                """,
                (now, int(deposit_id)),
            )
            await connection.execute(
                "INSERT INTO admin_investment_closures("
                "deposit_id,user_id,operation_key,reason,closed_by,cancelled_payouts,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    int(deposit_id),
                    int(user_id),
                    operation_key,
                    clean_reason,
                    int(changed_by),
                    cancelled,
                    now,
                ),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "admin_investment_closed",
                    (
                        f"admin={changed_by};user={user_id};deposit={deposit_id};"
                        f"cancelled_payouts={cancelled};reason={clean_reason}"
                    ),
                    now,
                ),
            )
            amount_text = minor_to_text(int(deposit["principal_minor"]))
            await self._queue_notification(
                connection,
                user_id=int(user_id),
                category="deposit",
                event_type="admin_investment_closed",
                title="Инвестиция закрыта",
                body=f"Администратор закрыл инвестицию #{deposit_id} на {amount_text} USDT.",
                telegram_html=(
                    "⏹ <b>Инвестиция закрыта</b>\n\n"
                    f"💰 Сумма: <b>{amount_text} USDT</b>\n"
                    f"📦 Инвестиция: <b>#{deposit_id}</b>\n"
                    "Дальнейшие начисления по этой инвестиции остановлены."
                ),
                dedupe_key=f"admin-investment-closed:{deposit_id}:{clean_operation}",
                data={
                    "target_view": "assets",
                    "deposit_id": int(deposit_id),
                    "amount_minor": int(deposit["principal_minor"]),
                    "source": "admin",
                },
                created_at=now,
            )
            cursor = await connection.execute(
                "SELECT * FROM deposits WHERE id = ?",
                (int(deposit_id),),
            )
            result = dict(await cursor.fetchone())
            result["reused"] = False
            result["cancelled_payouts"] = cancelled
            return result

    async def set_user_balance(
        self,
        user_id: int,
        new_balance_minor: int,
        changed_by: int,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        if new_balance_minor < 0:
            raise RepositoryError("Balance cannot be negative")
        clean_reason = reason.strip()[:500]
        if not clean_reason:
            raise RepositoryError("Balance adjustment reason is required")
        operation_key = self._admin_control_operation_key(
            "user-balance", changed_by, user_id, idempotency_key
        )
        fingerprint = f"{int(new_balance_minor)}|{clean_reason}"
        now = int(time.time())
        async with self.transaction() as connection:
            reused = await self._reuse_admin_control(
                connection, operation_key=operation_key, fingerprint=fingerprint
            )
            if reused is not None:
                return reused
            cursor = await connection.execute(
                "SELECT manual_balance_minor FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RepositoryError("User not found")
            old_balance = int(row["manual_balance_minor"] or 0)
            await connection.execute(
                "UPDATE users SET manual_balance_minor = ? WHERE telegram_id = ?",
                (new_balance_minor, user_id),
            )
            await connection.execute(
                """
                INSERT INTO balance_adjustments(
                    user_id, old_balance_minor, new_balance_minor, delta_minor,
                    reason, changed_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    old_balance,
                    new_balance_minor,
                    new_balance_minor - old_balance,
                    clean_reason,
                    changed_by,
                    now,
                ),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "user_balance_changed",
                    f"admin={changed_by};user={user_id};old={old_balance};new={new_balance_minor};reason={clean_reason}",
                    now,
                ),
            )
            result = {
                "old_balance_minor": old_balance,
                "new_balance_minor": int(new_balance_minor),
                "reused": False,
            }
            await self._store_admin_control(
                connection,
                operation_key=operation_key,
                kind="user-balance",
                actor_id=changed_by,
                user_id=user_id,
                fingerprint=fingerprint,
                result=result,
                created_at=now,
            )
            return result

    async def admin_set_user_wallet(
        self,
        user_id: int,
        address: str | None,
        changed_by: int,
    ) -> bool:
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "UPDATE users SET payout_address = ? WHERE telegram_id = ?",
                (address, user_id),
            )
            if not cursor.rowcount:
                return False
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "user_wallet_changed",
                    f"admin={changed_by};user={user_id};address={address or ''}",
                    now,
                ),
            )
            return True

    async def admin_set_user_referrer(
        self,
        user_id: int,
        identifier: str | None,
        changed_by: int,
        *,
        require_null_referrer: bool = False,
        reason: str | None = None,
    ) -> dict[str, object]:
        """Change a user's direct inviter without rewriting historical rewards.

        The current subtree stays attached to the user, so moving the user moves that
        subtree beneath the new inviter. Already-created referral accruals/payouts are
        historical ledger entries and are intentionally never reassigned.
        """
        clean = (identifier or "").strip().lstrip("@")
        if len(clean) > 64:
            raise RepositoryError("Invalid referrer identifier")
        clean_reason = reason.strip()[:500] if reason is not None else ""
        audit_reason = f";reason={clean_reason}" if clean_reason else ""
        now = int(time.time())

        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT telegram_id, referrer_id FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            target = await cursor.fetchone()
            if target is None:
                raise RepositoryError("User not found")
            old_referrer_id = (
                int(target["referrer_id"]) if target["referrer_id"] is not None else None
            )
            if require_null_referrer and old_referrer_id is not None:
                cursor = await connection.execute(
                    "SELECT telegram_id, username, first_name FROM users WHERE telegram_id = ?",
                    (old_referrer_id,),
                )
                row = await cursor.fetchone()
                old_referrer = dict(row) if row else None
                return {
                    "changed": False,
                    "old_referrer": old_referrer,
                    "new_referrer": old_referrer,
                    "reason": "already_bound",
                }

            new_referrer_id: int | None = None
            new_referrer: dict[str, object] | None = None
            if clean:
                if clean.isdigit():
                    cursor = await connection.execute(
                        "SELECT telegram_id, username, first_name FROM users WHERE telegram_id = ?",
                        (int(clean),),
                    )
                    rows = await cursor.fetchall()
                else:
                    cursor = await connection.execute(
                        "SELECT telegram_id, username, first_name FROM users "
                        "WHERE lower(username) = lower(?) ORDER BY last_seen_at DESC LIMIT 2",
                        (clean,),
                    )
                    rows = await cursor.fetchall()
                if not rows:
                    raise RepositoryError("Referrer not found")
                if len(rows) > 1:
                    raise RepositoryError("Referrer username is ambiguous; use Telegram ID")
                row = rows[0]
                new_referrer_id = int(row["telegram_id"])
                new_referrer = dict(row)
                if new_referrer_id == user_id:
                    raise RepositoryError("User cannot be their own referrer")

                # Walk upward from the proposed inviter. If the edited user appears in
                # that chain, the proposed inviter is inside this user's subtree and
                # accepting it would create a cycle.
                seen: set[int] = set()
                ancestor_id: int | None = new_referrer_id
                for _ in range(1000):
                    if ancestor_id is None:
                        break
                    if ancestor_id == user_id:
                        raise RepositoryError("Referrer would create a referral cycle")
                    if ancestor_id in seen:
                        raise RepositoryError("Existing referral cycle detected")
                    seen.add(ancestor_id)
                    cursor = await connection.execute(
                        "SELECT referrer_id FROM users WHERE telegram_id = ?",
                        (ancestor_id,),
                    )
                    ancestor = await cursor.fetchone()
                    if ancestor is None or ancestor["referrer_id"] is None:
                        ancestor_id = None
                    else:
                        ancestor_id = int(ancestor["referrer_id"])
                else:
                    raise RepositoryError("Referral hierarchy is too deep")

            if old_referrer_id == new_referrer_id:
                old_referrer = None
                if old_referrer_id is not None:
                    cursor = await connection.execute(
                        "SELECT telegram_id, username, first_name FROM users WHERE telegram_id = ?",
                        (old_referrer_id,),
                    )
                    row = await cursor.fetchone()
                    old_referrer = dict(row) if row else None
                return {
                    "changed": False,
                    "old_referrer": old_referrer,
                    "new_referrer": new_referrer or old_referrer,
                }

            old_referrer = None
            if old_referrer_id is not None:
                cursor = await connection.execute(
                    "SELECT telegram_id, username, first_name FROM users WHERE telegram_id = ?",
                    (old_referrer_id,),
                )
                row = await cursor.fetchone()
                old_referrer = dict(row) if row else None

            await connection.execute(
                "UPDATE users SET referrer_id = ? WHERE telegram_id = ?",
                (new_referrer_id, user_id),
            )
            await connection.execute(
                """
                INSERT INTO referrer_adjustments(
                    user_id, old_referrer_id, new_referrer_id, changed_by, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, old_referrer_id, new_referrer_id, changed_by, now),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "user_referrer_changed",
                    (
                        f"admin={changed_by};user={user_id};old={old_referrer_id or ''};"
                        f"new={new_referrer_id or ''}{audit_reason}"
                    ),
                    now,
                ),
            )
            return {
                "changed": True,
                "old_referrer": old_referrer,
                "new_referrer": new_referrer,
            }

    async def set_user_blocked(self, user_id: int, blocked: bool) -> bool:
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "UPDATE users SET blocked = ? WHERE telegram_id = ?",
                (1 if blocked else 0, user_id),
            )
            if not cursor.rowcount:
                return False
            if blocked:
                await connection.execute(
                    "UPDATE deposit_invoices SET status = 'expired' "
                    "WHERE user_id = ? AND status = 'pending'",
                    (user_id,),
                )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) "
                "VALUES ('user_block_state', ?, ?)",
                (f"user={user_id};blocked={int(blocked)}", int(time.time())),
            )
            return True

    async def create_broadcast(
        self,
        created_by: int,
        message: str,
        audience: str,
        *,
        parse_mode: str = "HTML",
        media_path: str | None = None,
        buttons: list[dict[str, str]] | None = None,
    ) -> dict[str, int | str]:
        if audience not in BROADCAST_AUDIENCE_FILTERS:
            raise RepositoryError("Unsupported broadcast audience")
        now = int(time.time())
        filters = BROADCAST_AUDIENCE_FILTERS
        async with self.transaction() as connection:
            buttons_json = json.dumps(buttons or [], ensure_ascii=False, separators=(",", ":"))
            cursor = await connection.execute(
                """
                INSERT INTO broadcasts(
                    created_by, audience, message, parse_mode, media_path, buttons_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (created_by, audience, message, parse_mode, media_path, buttons_json, now),
            )
            broadcast_id = int(cursor.lastrowid)
            await connection.execute(
                f"""
                INSERT INTO broadcast_deliveries(broadcast_id, user_id)
                SELECT ?, users.telegram_id
                FROM users
                WHERE users.blocked = 0 AND {filters[audience]}
                """,
                (broadcast_id,),
            )
            cursor = await connection.execute(
                "SELECT COUNT(*) AS value FROM broadcast_deliveries WHERE broadcast_id = ?",
                (broadcast_id,),
            )
            total = int((await cursor.fetchone())["value"])
            await connection.execute(
                "UPDATE broadcasts SET total_count = ?, status = ? WHERE id = ?",
                (total, "queued" if total else "completed", broadcast_id),
            )
        return {
            "id": broadcast_id,
            "audience": audience,
            "status": "queued" if total else "completed",
            "total_count": total,
        }

    async def claim_next_broadcast_delivery(self) -> dict[str, object] | None:
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT delivery.id, delivery.broadcast_id, delivery.user_id,
                       broadcasts.message, broadcasts.parse_mode, broadcasts.media_path,
                       broadcasts.media_file_id, broadcasts.buttons_json
                FROM broadcast_deliveries AS delivery
                JOIN broadcasts ON broadcasts.id = delivery.broadcast_id
                WHERE delivery.status = 'queued'
                  AND broadcasts.status IN ('queued', 'sending')
                ORDER BY delivery.id
                LIMIT 1
                """
            )
            row = await cursor.fetchone()
            if not row:
                return None
            await connection.execute(
                "UPDATE broadcast_deliveries "
                "SET status = 'sending', attempts = attempts + 1 WHERE id = ?",
                (row["id"],),
            )
            await connection.execute(
                "UPDATE broadcasts SET status = 'sending', "
                "started_at = COALESCE(started_at, ?) WHERE id = ?",
                (now, row["broadcast_id"]),
            )
            return dict(row)

    async def set_broadcast_media_file_id(
        self,
        broadcast_id: int,
        file_id: str,
    ) -> None:
        async with self.transaction() as connection:
            await connection.execute(
                "UPDATE broadcasts SET media_file_id = ? WHERE id = ? AND media_file_id IS NULL",
                (file_id[:512], broadcast_id),
            )

    async def finish_broadcast_delivery(
        self,
        delivery_id: int,
        *,
        delivered: bool,
        error: str | None = None,
    ) -> None:
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT broadcast_id FROM broadcast_deliveries WHERE id = ?",
                (delivery_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return
            broadcast_id = int(row["broadcast_id"])
            await connection.execute(
                "UPDATE broadcast_deliveries SET status = ?, last_error = ?, sent_at = ? "
                "WHERE id = ? AND status = 'sending'",
                (
                    "delivered" if delivered else "failed",
                    None if delivered else (error or "delivery failed")[:500],
                    now,
                    delivery_id,
                ),
            )
            cursor = await connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) AS delivered,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN status IN ('queued', 'sending') THEN 1 ELSE 0 END) AS pending
                FROM broadcast_deliveries
                WHERE broadcast_id = ?
                """,
                (broadcast_id,),
            )
            counts = await cursor.fetchone()
            pending = int(counts["pending"] or 0)
            await connection.execute(
                """
                UPDATE broadcasts
                SET delivered_count = ?, failed_count = ?,
                    status = CASE WHEN ? = 0 THEN 'completed' ELSE 'sending' END,
                    completed_at = CASE WHEN ? = 0 THEN ? ELSE completed_at END
                WHERE id = ?
                """,
                (
                    int(counts["delivered"] or 0),
                    int(counts["failed"] or 0),
                    pending,
                    pending,
                    now,
                    broadcast_id,
                ),
            )

    async def requeue_broadcast_delivery(self, delivery_id: int, error: str) -> None:
        async with self.transaction() as connection:
            await connection.execute(
                "UPDATE broadcast_deliveries SET status = 'queued', last_error = ? "
                "WHERE id = ? AND status = 'sending'",
                (error[:500], delivery_id),
            )

    async def admin_audit(self, limit: int = 100) -> list[dict[str, object]]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC, id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def admin_broadcasts(self, limit: int = 20) -> list[dict[str, object]]:
        connection = self._connection()
        async with self._lock:
            cursor = await connection.execute(
                "SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            broadcasts = [dict(row) for row in await cursor.fetchall()]
            for broadcast in broadcasts:
                cursor = await connection.execute(
                    """
                    SELECT
                        SUM(CASE WHEN status IN ('queued', 'sending') THEN 1 ELSE 0 END) AS pending,
                        MAX(CASE WHEN status = 'failed' THEN last_error ELSE NULL END) AS last_error
                    FROM broadcast_deliveries
                    WHERE broadcast_id = ?
                    """,
                    (broadcast["id"],),
                )
                row = await cursor.fetchone()
                broadcast["pending_count"] = int((row["pending"] if row else 0) or 0)
                broadcast["last_error"] = str(row["last_error"] or "") if row else ""
            return broadcasts

    async def broadcast_audience_counts(self) -> dict[str, int]:
        """Recipient counts per audience, using the same filters as create_broadcast."""
        connection = self._connection()
        counts: dict[str, int] = {}
        async with self._lock:
            for audience, condition in BROADCAST_AUDIENCE_FILTERS.items():
                cursor = await connection.execute(
                    f"SELECT COUNT(*) AS value FROM users WHERE users.blocked = 0 AND {condition}"
                )
                counts[audience] = int((await cursor.fetchone())["value"] or 0)
        return counts

    async def retry_broadcast(self, broadcast_id: int) -> dict[str, int]:
        """Requeue deliveries that failed. Already delivered recipients are never resent."""
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT id FROM broadcasts WHERE id = ?",
                (broadcast_id,),
            )
            if await cursor.fetchone() is None:
                raise RepositoryError("Broadcast not found")
            cursor = await connection.execute(
                "UPDATE broadcast_deliveries SET status = 'queued', last_error = NULL, sent_at = NULL "
                "WHERE broadcast_id = ? AND status = 'failed'",
                (broadcast_id,),
            )
            requeued = int(cursor.rowcount or 0)
            cursor = await connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) AS delivered,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN status IN ('queued', 'sending') THEN 1 ELSE 0 END) AS pending
                FROM broadcast_deliveries
                WHERE broadcast_id = ?
                """,
                (broadcast_id,),
            )
            counts = await cursor.fetchone()
            pending = int(counts["pending"] or 0)
            await connection.execute(
                """
                UPDATE broadcasts
                SET delivered_count = ?, failed_count = ?,
                    status = CASE WHEN ? = 0 THEN status ELSE 'queued' END,
                    completed_at = CASE WHEN ? = 0 THEN completed_at ELSE NULL END
                WHERE id = ?
                """,
                (
                    int(counts["delivered"] or 0),
                    int(counts["failed"] or 0),
                    pending,
                    pending,
                    broadcast_id,
                ),
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "broadcast_retried",
                    f"broadcast={broadcast_id};requeued={requeued}",
                    now,
                ),
            )
        return {"requeued": requeued, "pending": pending}

    async def queue_broadcast_self_test(
        self,
        admin_id: int,
        *,
        telegram_html: str,
        preview: str,
    ) -> bool:
        """Send the composed message to the acting admin only, via the notification worker.

        Nothing is written to `broadcasts`, so a test can never reach real users.
        """
        now = int(time.time())
        async with self.transaction() as connection:
            cursor = await connection.execute(
                "SELECT telegram_id FROM users WHERE telegram_id = ?",
                (admin_id,),
            )
            if await cursor.fetchone() is None:
                raise RepositoryError("User not found")
            digest = hashlib.sha256(telegram_html.encode("utf-8")).hexdigest()[:16]
            queued = await self._queue_notification(
                connection,
                user_id=admin_id,
                category="system",
                event_type="admin_broadcast_test",
                title="Тест рассылки",
                body=preview,
                telegram_html=telegram_html,
                dedupe_key=f"broadcast-test:{admin_id}:{now}:{digest}",
                data={"target_view": "admin"},
                created_at=now,
            )
            await connection.execute(
                "INSERT INTO audit_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (
                    "broadcast_test_sent",
                    f"admin={admin_id};digest={digest}",
                    now,
                ),
            )
        return queued
