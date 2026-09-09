import asyncio
import base64
import hashlib
import hmac
import html
import ipaddress
import json
import logging
import os
import re
import signal
import socket
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr, field_validator
from eth_account import Account
from web3 import Web3

from .amounts import (
    MINOR_FACTOR,
    bps_to_percent_text,
    minor_to_atomic,
    minor_to_text,
    percent_to_bps,
    usdt_to_minor,
)
from .api_settings import MiniAppSettings
from .config import Settings
from .launcher import run_launcher
from .repository import DeltaRepository, RepositoryError
from .runtime_secrets import ChainSecretBundle, RuntimeSecretError, RuntimeSecretStore
from .services.blockchain import EvmTokenClient
from .services.broadcasts import BroadcastService
from .services.notifications import UserNotificationService
from .services.deposit_monitor import DepositMonitor
from .services.payouts import DailyPayoutService
from .services.safety import PayoutCircuitBreaker, SafetyMonitor, SafetyRuntime
from .telegram_auth import TelegramAuthError, TelegramUser, validate_init_data
# NOVERA admin inviter management
# NOVERA real admin treasury test payouts
# NOVERA Telegram bot + in-app notifications
# NOVERA production safety monitor + payout circuit breaker
# NOVERA audited admin financial and partner controls


logger = logging.getLogger(__name__)
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
BROADCAST_MEDIA_ID_RE = re.compile(r"^[a-f0-9]{32}\.(?:jpg|png)$")
BROADCAST_MEDIA_MAX_BYTES = 5 * 1024 * 1024


SESSION_COOKIE_NAME = "delta_session"
# NOVERA Telegram per-user storage authentication
SESSION_TOKEN_VERSION = 1
CLIENT_SESSION_TTL_SECONDS = 90 * 24 * 60 * 60

# NOVERA account-safe native authentication


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _web_session_key(bot_token: str) -> bytes:
    return hmac.new(
        b"DELTA-MiniApp-Session-v1",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def issue_web_session(
    user: TelegramUser,
    bot_token: str,
    ttl_seconds: int,
    *,
    now: int | None = None,
) -> str:
    current_time = int(time.time()) if now is None else now
    payload = {
        "v": SESSION_TOKEN_VERSION,
        "uid": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "language_code": user.language_code,
        "iat": current_time,
        "exp": current_time + ttl_seconds,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(_web_session_key(bot_token), raw, hashlib.sha256).digest()
    return f"{_b64url_encode(raw)}.{_b64url_encode(signature)}"


def validate_web_session(
    token: str,
    bot_token: str,
    *,
    now: int | None = None,
) -> TelegramUser:
    if not token or len(token) > 4096:
        raise TelegramAuthError("NOVERA session is missing")
    try:
        raw_part, signature_part = token.split(".", 1)
        raw = _b64url_decode(raw_part)
        received_signature = _b64url_decode(signature_part)
    except Exception as exc:
        raise TelegramAuthError("NOVERA session is malformed") from exc
    expected_signature = hmac.new(_web_session_key(bot_token), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(received_signature, expected_signature):
        raise TelegramAuthError("NOVERA session signature is invalid")
    try:
        payload = json.loads(raw.decode("utf-8"))
        version = int(payload["v"])
        user_id = int(payload["uid"])
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramAuthError("NOVERA session payload is invalid") from exc
    current_time = int(time.time()) if now is None else now
    if version != SESSION_TOKEN_VERSION or issued_at > current_time + 30 or expires_at <= current_time:
        raise TelegramAuthError("NOVERA session has expired")
    if expires_at - issued_at > 7_776_000:
        raise TelegramAuthError("NOVERA session lifetime is invalid")
    return TelegramUser(
        id=user_id,
        username=payload.get("username"),
        first_name=str(payload.get("first_name") or ""),
        language_code=payload.get("language_code"),
    )



class WalletRequest(BaseModel):
    address: str = Field(min_length=42, max_length=42)


class InvoiceRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    promo_code: str | None = Field(default=None, max_length=32)


class SessionExchangeRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class BlockRequest(BaseModel):
    blocked: bool


class AdminGrantRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)


class AdminUserBalanceRequest(BaseModel):
    balance_usdt: Decimal = Field(ge=0, le=Decimal("1000000000000"))
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_must_be_meaningful(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 2:
            raise ValueError("Reason is required")
        return clean


class AdminUserWalletRequest(BaseModel):
    address: str | None = Field(default=None, max_length=42)


class AdminUserReferrerRequest(BaseModel):
    identifier: str | None = Field(default=None, max_length=64)


class AdminReferralBalanceRequest(BaseModel):
    balance_usdt: Decimal = Field(ge=0, le=Decimal("1000000000000"))
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_must_be_meaningful(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 2:
            raise ValueError("Reason is required")
        return clean


class AdminReferralLevelRequest(BaseModel):
    unlocked_level: int = Field(ge=0, le=5)
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_must_be_meaningful(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 2:
            raise ValueError("Reason is required")
        return clean


class AdminOpenInvestmentRequest(BaseModel):
    amount_usdt: Decimal = Field(gt=0, le=Decimal("1000000000000"))
    reason: str = Field(min_length=2, max_length=500)
    operation_id: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    confirm: Literal["OPEN_INVESTMENT"]

    @field_validator("reason")
    @classmethod
    def reason_must_be_meaningful(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 2:
            raise ValueError("Reason is required")
        return clean


class AdminCloseInvestmentRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    operation_id: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    confirm: Literal["CLOSE_INVESTMENT"]

    @field_validator("reason")
    @classmethod
    def reason_must_be_meaningful(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 2:
            raise ValueError("Reason is required")
        return clean

    @field_validator("operation_id")
    @classmethod
    def operation_id_must_be_clean(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 16:
            raise ValueError("Invalid investment operation ID")
        return clean

class AdminTestPayoutRequest(BaseModel):
    address: str = Field(min_length=42, max_length=42)
    amount: Decimal = Field(ge=Decimal("1"), le=Decimal("1000000000000"))
    confirm: Literal["REAL_PAYOUT"]


class PromoCodeCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    bonus_type: Literal["percent", "fixed"]
    bonus_percent: Decimal | None = Field(default=None, ge=0, le=Decimal("100"))
    bonus_usdt: Decimal | None = Field(default=None, ge=0, le=Decimal("1000000000000"))
    max_redemptions: int = Field(ge=1, le=1_000_000)
    min_deposit_usdt: Decimal = Field(default=Decimal("0"), ge=0)
    valid_from: int | None = Field(default=None, ge=0)
    valid_until: int | None = Field(default=None, ge=0)
    enabled: bool = True


class PromoCodeUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    bonus_type: Literal["percent", "fixed"] | None = None
    bonus_percent: Decimal | None = Field(default=None, ge=0, le=Decimal("100"))
    bonus_usdt: Decimal | None = Field(default=None, ge=0, le=Decimal("1000000000000"))
    max_redemptions: int | None = Field(default=None, ge=1, le=1_000_000)
    min_deposit_usdt: Decimal | None = Field(default=None, ge=0)
    valid_from: int | None = Field(default=None, ge=0)
    valid_until: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class BroadcastButtonRequest(BaseModel):
    text: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=4, max_length=2048)


class BroadcastRequest(BaseModel):
    message: str = Field(default="", max_length=4096)
    audience: Literal["all", "investors", "partners"] = "all"
    media_id: str | None = Field(default=None, max_length=64)
    buttons: list[BroadcastButtonRequest] = Field(default_factory=list, max_length=8)


class BroadcastMediaUploadRequest(BaseModel):
    mime_type: Literal["image/jpeg", "image/png"]
    data_base64: str = Field(min_length=16)


class BroadcastTestRequest(BaseModel):
    """Text-only rehearsal delivered to the acting admin, never to an audience."""

    message: str = Field(min_length=1, max_length=4096)


class RuntimeSettingsRequest(BaseModel):
    daily_profit_bps: int = Field(ge=1, le=10000)
    payout_days: int = Field(ge=1, le=20)
    deposit_min_usdt: int = Field(ge=1, le=1000000000)
    deposit_max_usdt: int = Field(ge=1, le=1000000000)
    invoice_ttl_minutes: int = Field(ge=1, le=1440)
    referral_level_bps: list[int] = Field(min_length=5, max_length=5)
    referral_personal_thresholds_usdt: list[int] = Field(min_length=5, max_length=5)
    referral_line_thresholds_usdt: list[int] = Field(min_length=5, max_length=5)
    deposits_enabled: bool
    investments_enabled: bool | None = None
    payouts_enabled: bool
    referral_enabled: bool | None = None
    confirmation_blocks: int = Field(ge=0, le=100)
    deposit_scan_interval_seconds: int = Field(ge=1, le=3600)
    support_url: str = Field(min_length=4, max_length=512)
    chat_url: str = Field(min_length=4, max_length=512)


class ChainRuntimeConfigRequest(BaseModel):
    mode: Literal["production", "testnet"]
    token_contract: str = Field(min_length=42, max_length=42)
    scan_start_block: int = Field(ge=0, le=10_000_000_000)
    rpc_url: SecretStr
    wss_url: SecretStr
    seed_phrase: SecretStr
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("reason")
    @classmethod
    def chain_reason_must_be_meaningful(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 4:
            raise ValueError("Reason is required")
        return clean


class ChainActivationRequest(BaseModel):
    generation: str = Field(pattern=r"^[a-f0-9]{32}$")
    treasury_confirmation: str = Field(min_length=42, max_length=42)
    operation_id: str = Field(
        min_length=16,
        max_length=80,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    reason: str = Field(min_length=4, max_length=500)
    confirm: Literal["ACTIVATE_CHAIN"]

    @field_validator("reason")
    @classmethod
    def activation_reason_must_be_meaningful(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 4:
            raise ValueError("Reason is required")
        return clean


class AuthenticatedUser(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str
    is_admin: bool
    is_owner: bool = False


@dataclass(slots=True)
class RuntimeStatus:
    started_at: float = field(default_factory=time.time)
    last_payout_tick: float | None = None
    last_payout_error: str | None = None


@dataclass(slots=True)
class ChainSetupRuntime:
    status: Literal["bootstrap", "configured", "active", "degraded"] = "bootstrap"
    active_generation: str | None = None
    pending_generation: str | None = None
    public_fingerprint: str | None = None
    last_error_code: str | None = None
    financial_ready: bool = False

    def snapshot(self) -> dict[str, object]:
        return {
            "status": self.status,
            "active_generation": self.active_generation,
            "pending_generation": self.pending_generation,
            "public_fingerprint": self.public_fingerprint,
            "last_error_code": self.last_error_code,
            "financial_ready": self.financial_ready,
        }


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = time.monotonic()
        threshold = now - window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= threshold:
                events.popleft()
            if len(events) >= limit:
                return max(1, int(window_seconds - (now - events[0])) + 1)
            events.append(now)
            if len(self._events) > 10_000:
                empty = [name for name, values in self._events.items() if not values]
                for name in empty[:1000]:
                    self._events.pop(name, None)
        return None


class _TelegramHTMLSanitizer(HTMLParser):
    allowed_tags = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in self.allowed_tags:
            return
        if tag == "a":
            href = next((value for name, value in attrs if name.lower() == "href"), None)
            href = (href or "").strip()
            if not href.startswith(("https://", "http://", "tg://")):
                return
            self.parts.append(f'<a href="{html.escape(href, quote=True)}">')
            self.open_tags.append(tag)
            return
        self.parts.append(f"<{tag}>")
        self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self.open_tags or tag not in self.open_tags:
            return
        while self.open_tags:
            current = self.open_tags.pop()
            self.parts.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        self.parts.append(html.escape(data, quote=False))

    def close_open_tags(self) -> None:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")


def sanitize_telegram_html(value: str) -> str:
    parser = _TelegramHTMLSanitizer()
    try:
        parser.feed(value)
        parser.close()
        parser.close_open_tags()
    except Exception:
        return html.escape(value, quote=False)
    return "".join(parser.parts).strip()


def validate_broadcast_buttons(buttons: list[BroadcastButtonRequest]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for button in buttons:
        text = button.text.strip()
        url = button.url.strip()
        if not url.startswith(("https://", "http://", "tg://")):
            raise HTTPException(status_code=422, detail="Button URL must use https://, http:// or tg://")
        result.append({"text": text, "url": url})
    return result


def _usdt_to_minor_allow_zero(value: Decimal) -> int:
    if value == 0:
        return 0
    return usdt_to_minor(value)


def _promo_bonus_minor_fields(
    bonus_type: str,
    bonus_percent: Decimal | None,
    bonus_usdt: Decimal | None,
) -> tuple[int, int]:
    """Translate percent/usdt request fields into bps/minor storage units."""
    if bonus_type == "percent":
        if bonus_percent is None or bonus_percent <= 0:
            raise HTTPException(
                status_code=422, detail="bonus_percent is required for percent promo"
            )
        return percent_to_bps(bonus_percent), 0
    if bonus_usdt is None or bonus_usdt <= 0:
        raise HTTPException(
            status_code=422, detail="bonus_usdt is required for fixed promo"
        )
    return 0, usdt_to_minor(bonus_usdt)


def _promo_response(promo: dict[str, object]) -> dict[str, object]:
    bonus_bps = int(promo.get("bonus_bps") or 0)
    bonus_fixed_minor = int(promo.get("bonus_fixed_minor") or 0)
    return {
        **promo,
        "bonus_percent": bps_to_percent_text(bonus_bps) if bonus_bps else None,
        "bonus_usdt": minor_to_text(bonus_fixed_minor) if bonus_fixed_minor else None,
        "min_deposit_usdt": minor_to_text(int(promo.get("min_deposit_minor") or 0)),
    }


def runtime_settings_snapshot(business: MiniAppSettings, chain_settings: Settings) -> dict[str, object]:
    return {
        "daily_profit_bps": int(business.daily_profit_bps),
        "payout_days": int(business.payout_days),
        "deposit_min_usdt": int(business.deposit_min_usdt),
        "deposit_max_usdt": int(business.deposit_max_usdt),
        "invoice_ttl_minutes": int(business.invoice_ttl_minutes),
        "referral_level_bps": list(business.referral_level_bps),
        "referral_personal_thresholds_usdt": list(business.referral_personal_thresholds_usdt),
        "referral_line_thresholds_usdt": list(business.referral_line_thresholds_usdt),
        "deposits_enabled": bool(chain_settings.deposits_enabled),
        "investments_enabled": bool(chain_settings.investments_enabled),
        "payouts_enabled": bool(chain_settings.payouts_enabled),
        "referral_enabled": bool(chain_settings.referral_enabled),
        "confirmation_blocks": int(chain_settings.confirmation_blocks),
        "deposit_scan_interval_seconds": int(chain_settings.deposit_scan_interval_seconds),
        "support_url": str(chain_settings.support_url),
        "chat_url": str(chain_settings.chat_url),
    }


def apply_runtime_settings(
    business: MiniAppSettings,
    chain_settings: Settings,
    values: dict[str, object],
) -> None:
    business_fields = {
        "daily_profit_bps", "payout_days", "deposit_min_usdt", "deposit_max_usdt",
        "invoice_ttl_minutes", "referral_level_bps",
        "referral_personal_thresholds_usdt", "referral_line_thresholds_usdt",
    }
    chain_fields = {
        "deposits_enabled", "investments_enabled", "payouts_enabled",
        "referral_enabled", "confirmation_blocks",
        "deposit_scan_interval_seconds", "support_url", "chat_url", "environment",
        "chain_enabled", "simulate_payouts", "chain_id", "token_contract",
        "treasury_address", "scan_start_block",
    }
    for key, value in values.items():
        if key in business_fields:
            if key.startswith("referral_"):
                value = tuple(int(item) for item in value)
            setattr(business, key, value)
        elif key in chain_fields:
            setattr(chain_settings, key, value)


def validate_runtime_settings_payload(payload: RuntimeSettingsRequest) -> None:
    if payload.deposit_max_usdt < payload.deposit_min_usdt:
        raise HTTPException(status_code=422, detail="Maximum deposit must be greater than or equal to minimum")
    if any(item < 0 or item > 10000 for item in payload.referral_level_bps):
        raise HTTPException(status_code=422, detail="Referral rates must be between 0 and 10000 bps")
    if any(item < 0 for item in payload.referral_personal_thresholds_usdt + payload.referral_line_thresholds_usdt):
        raise HTTPException(status_code=422, detail="Referral thresholds cannot be negative")
    if not payload.support_url.startswith(("https://", "http://", "tg://")):
        raise HTTPException(status_code=422, detail="Support URL is invalid")
    if not payload.chat_url.startswith(("https://", "http://", "tg://")):
        raise HTTPException(status_code=422, detail="Chat URL is invalid")


def runtime_secret_store(chain_settings: Settings) -> RuntimeSecretStore | None:
    key_file = chain_settings.runtime_config_key_file
    if key_file is None:
        return None
    return RuntimeSecretStore(
        Path(chain_settings.database_path).parent / "runtime_secrets",
        key_file,
    )


def apply_chain_bundle(chain_settings: Settings, bundle: ChainSecretBundle) -> None:
    chain_settings.environment = bundle.mode
    chain_settings.chain_enabled = True
    chain_settings.simulate_payouts = False
    chain_settings.chain_id = bundle.chain_id
    chain_settings.bsc_rpc_url = bundle.rpc_url
    chain_settings.bsc_wss_url = bundle.wss_url
    chain_settings.token_contract = bundle.token_contract
    chain_settings.treasury_address = bundle.treasury_address
    chain_settings.scan_start_block = bundle.scan_start_block
    chain_settings.payout_seed_phrase = SecretStr(bundle.seed_phrase)
    chain_settings.payout_private_key = None
    chain_settings.payout_keystore_path = None
    chain_settings.payout_keystore_password = None


def disable_financial_runtime(chain_settings: Settings) -> None:
    chain_settings.chain_enabled = False
    chain_settings.deposits_enabled = False
    chain_settings.investments_enabled = False
    chain_settings.payouts_enabled = False
    chain_settings.referral_enabled = False
    chain_settings.simulate_payouts = False
    chain_settings.bsc_rpc_url = ""
    chain_settings.bsc_wss_url = ""
    chain_settings.treasury_address = ""
    chain_settings.payout_seed_phrase = None
    chain_settings.payout_private_key = None
    chain_settings.payout_keystore_path = None
    chain_settings.payout_keystore_password = None


async def validate_public_provider_url(
    value: str,
    *,
    schemes: frozenset[str],
    label: str,
) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{label} endpoint is invalid") from exc
    if parsed.scheme not in schemes or not parsed.hostname:
        raise HTTPException(status_code=422, detail=f"{label} endpoint has an invalid scheme")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail=f"{label} endpoint credentials must use the URL path")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise HTTPException(status_code=422, detail=f"{label} endpoint must be public")
    try:
        direct = ipaddress.ip_address(host)
        addresses = {direct}
    except ValueError:
        try:
            records = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: socket.getaddrinfo(
                    host,
                    port or (443 if parsed.scheme in {"https", "wss"} else 80),
                    type=socket.SOCK_STREAM,
                ),
            )
        except OSError as exc:
            raise HTTPException(status_code=422, detail=f"{label} endpoint DNS lookup failed") from exc
        addresses = {
            ipaddress.ip_address(str(record[4][0]).split("%", 1)[0])
            for record in records
        }
    if not addresses or any(not address.is_global for address in addresses):
        raise HTTPException(status_code=422, detail=f"{label} endpoint must resolve only to public addresses")


def validate_chain_runtime_candidate(candidate: Settings) -> None:
    if candidate.environment not in {"production", "testnet", "development"}:
        raise HTTPException(status_code=422, detail="Invalid chain environment")

    phrase = candidate.payout_seed_phrase.get_secret_value().strip() if candidate.payout_seed_phrase else ""
    has_private_key = bool(candidate.payout_private_key and candidate.payout_private_key.get_secret_value().strip())
    has_keystore = bool(candidate.payout_keystore_path and candidate.payout_keystore_password)
    if phrase:
        if len(phrase.split()) not in {12, 15, 18, 21, 24}:
            raise HTTPException(status_code=422, detail="Seed phrase must contain 12, 15, 18, 21 or 24 words")
        try:
            Account.enable_unaudited_hdwallet_features()
            account = Account.from_mnemonic(phrase, account_path=candidate.seed_account_path)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Seed phrase cannot derive an EVM wallet") from exc
        candidate.treasury_address = account.address

    if not candidate.chain_enabled:
        return
    if candidate.environment == "production" and candidate.chain_id != 56:
        raise HTTPException(status_code=422, detail="Production mode requires BSC Mainnet chain ID 56")
    if candidate.environment == "testnet" and candidate.chain_id != 97:
        raise HTTPException(status_code=422, detail="Testnet mode requires BSC Testnet chain ID 97")
    if candidate.simulate_payouts:
        raise HTTPException(status_code=422, detail="Live chain mode cannot simulate payouts")
    if not Web3.is_address(candidate.token_contract):
        raise HTTPException(status_code=422, detail="Invalid token contract address")
    if not Web3.is_address(candidate.treasury_address):
        raise HTTPException(status_code=422, detail="Invalid treasury wallet address")
    if candidate.environment == "production" and int(candidate.scan_start_block) <= 0:
        raise HTTPException(status_code=422, detail="Production mode requires a positive scan start block")
    if candidate.environment == "production":
        if not candidate.bsc_rpc_url.startswith("https://"):
            raise HTTPException(status_code=422, detail="Production RPC must use https://")
        if not candidate.bsc_wss_url.startswith("wss://"):
            raise HTTPException(status_code=422, detail="Production WSS must use wss://")
    else:
        if not candidate.bsc_rpc_url.startswith(("https://", "http://")):
            raise HTTPException(status_code=422, detail="RPC must use http:// or https://")
        if not candidate.bsc_wss_url.startswith(("wss://", "ws://")):
            raise HTTPException(status_code=422, detail="WSS must use ws:// or wss://")
    if not phrase and not has_private_key and not has_keystore:
        raise HTTPException(status_code=422, detail="A payout signing method is required")


def chain_runtime_snapshot(
    chain_settings: Settings,
    setup: ChainSetupRuntime,
    secret_store: RuntimeSecretStore | None = None,
) -> dict[str, object]:
    phrase = chain_settings.payout_seed_phrase.get_secret_value().strip() if chain_settings.payout_seed_phrase else ""
    mode = "off"
    if chain_settings.chain_enabled:
        mode = "production" if chain_settings.environment == "production" and chain_settings.chain_id == 56 else "testnet"
    pending: dict[str, object] | None = None
    if setup.pending_generation and secret_store is not None:
        try:
            bundle = secret_store.load_pending(str(setup.pending_generation))
            pending = {
                "validated": True,
                "generation": bundle.generation,
                "mode": bundle.mode,
                "chain_id": bundle.chain_id,
                "treasury_address": bundle.treasury_address,
                "public_fingerprint": bundle.public_fingerprint,
            }
        except RuntimeSecretError:
            pending = None
    return {
        "mode": mode,
        "chain_id": int(chain_settings.chain_id),
        "token_contract": chain_settings.token_contract,
        "treasury_address": chain_settings.treasury_address,
        "scan_start_block": int(chain_settings.scan_start_block),
        "rpc_configured": bool(chain_settings.bsc_rpc_url),
        "wss_configured": bool(chain_settings.bsc_wss_url),
        "seed_configured": bool(phrase),
        "setup": setup.snapshot(),
        "pending": pending,
    }


def schedule_process_restart() -> None:
    loop = asyncio.get_running_loop()
    loop.call_later(1.5, lambda: os.kill(os.getpid(), signal.SIGTERM))


def validate_deployment_settings(
    chain_settings: Settings,
    business: MiniAppSettings,
) -> None:
    business.validate_business_rules()
    if chain_settings.chain_enabled and business.demo_mode:
        raise ValueError("DEMO_MODE must be false when CHAIN_ENABLED is true")
    if chain_settings.environment == "production":
        if business.demo_mode:
            raise ValueError("DEMO_MODE is forbidden in production")
        if not business.miniapp_url.startswith("https://"):
            raise ValueError("MINIAPP_URL must use HTTPS in production")
        if not business.miniapp_origin.startswith("https://"):
            raise ValueError("MINIAPP_ORIGIN must use HTTPS in production")
        if "*" in business.trusted_host_list:
            raise ValueError("Wildcard TRUSTED_HOSTS is forbidden in production")


async def payout_loop(
    service: DailyPayoutService,
    stop_event: asyncio.Event,
    interval_seconds: int,
    runtime: RuntimeStatus,
) -> None:
    while not stop_event.is_set():
        try:
            await service.run_once()
            runtime.last_payout_tick = time.time()
            runtime.last_payout_error = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            runtime.last_payout_error = type(exc).__name__
            logger.exception("Payout worker failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(2, interval_seconds))
        except TimeoutError:
            pass


async def initialize_chain_runtime(
    chain_settings: Settings,
    business: MiniAppSettings,
    repository: DeltaRepository,
) -> tuple[EvmTokenClient | None, object | None, RuntimeSecretStore | None, ChainSetupRuntime]:
    store = runtime_secret_store(chain_settings)
    state = await repository.get_chain_config_state()
    setup = ChainSetupRuntime(
        status=str(state.get("status") or "bootstrap"),  # type: ignore[arg-type]
        active_generation=(
            str(state["active_generation"]) if state.get("active_generation") else None
        ),
        pending_generation=(
            str(state["pending_generation"]) if state.get("pending_generation") else None
        ),
        public_fingerprint=(
            str(state["public_fingerprint"]) if state.get("public_fingerprint") else None
        ),
        last_error_code=(
            str(state["last_error_code"]) if state.get("last_error_code") else None
        ),
    )

    # Legacy deployments without the runtime key retain their existing startup
    # path. The bootstrap installer always provisions the key explicitly.
    if store is None:
        if chain_settings.chain_enabled:
            validate_chain_runtime_candidate(chain_settings)
            chain = EvmTokenClient(chain_settings)
            health = await chain.healthcheck()
            setup.status = "active"
            setup.financial_ready = True
            return chain, health, None, setup
        if chain_settings.environment != "production":
            setup.status = "active"
            setup.financial_ready = True
            return None, None, None, setup
        disable_financial_runtime(chain_settings)
        setup.status = "bootstrap"
        await repository.mark_chain_config_runtime(
            "bootstrap",
            generation=None,
            public_fingerprint=None,
        )
        return None, None, None, setup

    try:
        bundle = store.load_active()
    except RuntimeSecretError:
        try:
            store.quarantine_active()
        except RuntimeSecretError:
            pass
        disable_financial_runtime(chain_settings)
        setup.status = "degraded"
        setup.active_generation = None
        setup.last_error_code = "active_bundle_unreadable"
        await repository.mark_chain_config_runtime(
            "degraded",
            generation=None,
            public_fingerprint=setup.public_fingerprint,
            error_code=setup.last_error_code,
        )
        return None, None, store, setup

    if bundle is None:
        disable_financial_runtime(chain_settings)
        setup.status = "configured" if setup.pending_generation else "bootstrap"
        setup.financial_ready = False
        await repository.mark_chain_config_runtime(
            setup.status,
            generation=None,
            public_fingerprint=setup.public_fingerprint,
        )
        return None, None, store, setup

    async def start_bundle(
        selected: ChainSecretBundle,
    ) -> tuple[EvmTokenClient, object]:
        apply_chain_bundle(chain_settings, selected)
        validate_deployment_settings(chain_settings, business)
        validate_chain_runtime_candidate(chain_settings)
        client = EvmTokenClient(chain_settings)
        try:
            health = await client.healthcheck()
            await client.websocket_healthcheck()
            return client, health
        except BaseException:
            await client.close()
            raise

    try:
        chain, health = await start_bundle(bundle)
    except Exception as exc:
        logger.error("Active chain configuration failed startup validation: %s", type(exc).__name__)
        try:
            rolled_back = store.rollback()
            previous = store.load_active() if rolled_back else None
            if previous is not None:
                chain, health = await start_bundle(previous)
                setup.status = "active"
                setup.active_generation = previous.generation
                setup.public_fingerprint = previous.public_fingerprint
                setup.last_error_code = "rolled_back_after_startup_failure"
                setup.financial_ready = True
                await repository.mark_chain_config_runtime(
                    "active",
                    generation=previous.generation,
                    public_fingerprint=previous.public_fingerprint,
                    error_code=setup.last_error_code,
                )
                return chain, health, store, setup
        except Exception as rollback_exc:
            logger.error("Previous chain configuration could not be restored: %s", type(rollback_exc).__name__)
        try:
            store.quarantine_active()
        except RuntimeSecretError:
            pass
        disable_financial_runtime(chain_settings)
        setup.status = "degraded"
        setup.active_generation = None
        setup.last_error_code = "chain_startup_validation_failed"
        setup.financial_ready = False
        await repository.mark_chain_config_runtime(
            "degraded",
            generation=None,
            public_fingerprint=bundle.public_fingerprint,
            error_code=setup.last_error_code,
        )
        return None, None, store, setup

    setup.status = "active"
    setup.active_generation = bundle.generation
    setup.public_fingerprint = bundle.public_fingerprint
    setup.last_error_code = None
    setup.financial_ready = True
    await repository.mark_chain_config_runtime(
        "active",
        generation=bundle.generation,
        public_fingerprint=bundle.public_fingerprint,
    )
    return chain, health, store, setup


@asynccontextmanager
async def lifespan(application: FastAPI):
    chain_settings = Settings()
    business = MiniAppSettings()
    validate_deployment_settings(chain_settings, business)

    repository = DeltaRepository(chain_settings.database_path, business)
    await repository.connect()
    runtime_overrides = await repository.get_runtime_settings()
    if runtime_overrides:
        apply_runtime_settings(business, chain_settings, runtime_overrides)
        business.validate_business_rules()
    # If V5 is installed while the legacy worker has already scheduled the
    # final profit day, add the missing principal payout without touching
    # deposits that were already completed before the upgrade.
    await repository.ensure_missing_principal_payouts()
    chain, chain_health, secret_store, chain_setup = await initialize_chain_runtime(
        chain_settings,
        business,
        repository,
    )

    runtime = RuntimeStatus()
    safety_runtime = SafetyRuntime()
    payout_circuit = PayoutCircuitBreaker(safety_runtime)
    if not chain_settings.safety_monitor_enabled:
        payout_circuit.set_reasons([])
        safety_runtime.status = "disabled"
    stop_event = asyncio.Event()
    payout_service = DailyPayoutService(repository, chain_settings, chain, payout_circuit)
    tasks: list[asyncio.Task[object]] = []
    # Keep the payout worker alive even when payouts are temporarily disabled.
    # DailyPayoutService checks the runtime flag on every tick, so an admin can
    # disable and later re-enable payouts without restarting the container.
    tasks.append(
        asyncio.create_task(
            payout_loop(
                payout_service,
                stop_event,
                chain_settings.payout_interval_seconds,
                runtime,
            ),
            name="daily-payout-worker",
        )
    )

    if chain is not None:
        monitor = DepositMonitor(repository, chain_settings, chain, telemetry=safety_runtime)
        tasks.extend(
            [
                asyncio.create_task(
                    monitor.run_polling(stop_event),
                    name="deposit-http-monitor",
                ),
                asyncio.create_task(
                    monitor.run_websocket(stop_event),
                    name="deposit-wss-monitor",
                ),
            ]
        )

    bot_token = chain_settings.bot_token.get_secret_value()
    if business.run_bot_launcher:
        tasks.append(
            asyncio.create_task(
                run_launcher(
                    bot_token,
                    business.miniapp_url,
                    repository=repository,
                    admin_ids=chain_settings.admin_id_set | chain_settings.owner_id_set,
                    chain_settings=chain_settings,
                ),
                name="telegram-miniapp-launcher",
            )
        )
    if business.run_broadcast_worker:
        broadcaster = BroadcastService(repository, bot_token)
        tasks.append(
            asyncio.create_task(
                broadcaster.run(stop_event),
                name="telegram-broadcast-worker",
            )
        )

    notifier = UserNotificationService(repository, bot_token, business.miniapp_url)
    tasks.append(
        asyncio.create_task(
            notifier.run(stop_event),
            name="telegram-user-notification-worker",
        )
    )

    if chain_settings.safety_monitor_enabled:
        safety_monitor = SafetyMonitor(
            repository,
            chain_settings,
            chain,
            bot_token,
            safety_runtime,
            payout_circuit,
        )
        tasks.append(
            asyncio.create_task(
                safety_monitor.run(stop_event),
                name="novera-safety-monitor",
            )
        )

    application.state.chain_settings = chain_settings
    application.state.business = business
    application.state.repository = repository
    application.state.chain = chain
    application.state.chain_health = chain_health
    application.state.secret_store = secret_store
    application.state.chain_setup = chain_setup
    application.state.runtime = runtime
    application.state.safety_runtime = safety_runtime
    application.state.payout_circuit = payout_circuit
    application.state.stop_event = stop_event
    application.state.tasks = tasks
    application.state.rate_limiter = SlidingWindowRateLimiter()
    try:
        yield
    finally:
        stop_event.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if chain is not None:
            await chain.close()
        await repository.close()


startup_settings = MiniAppSettings()
app = FastAPI(
    title="NOVERA Mini App API",
    version="10.6-owner-bootstrap",
    lifespan=lifespan,
    docs_url="/docs" if startup_settings.demo_mode else None,
    redoc_url=None,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=startup_settings.trusted_host_list,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[startup_settings.miniapp_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=[
        "Content-Type",
        "Idempotency-Key",
        "X-Telegram-Init-Data",
        "X-Demo-Telegram-Id",
        "X-Request-Id",
    ],
    expose_headers=["X-Request-Id", "Retry-After"],
)


@app.exception_handler(RequestValidationError)
async def sanitized_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    # FastAPI's default Pydantic response includes the rejected input. That is
    # unsafe for write-only RPC/WSS/seed fields.
    details: list[dict[str, object]] = []
    for error in exc.errors():
        details.append(
            {
                "type": str(error.get("type") or "value_error"),
                "loc": list(error.get("loc") or ()),
                "msg": str(error.get("msg") or "Invalid request"),
            }
        )
    return JSONResponse(status_code=422, content={"detail": details})


@app.middleware("http")
async def request_guard(request: Request, call_next):
    request_id_header = request.headers.get("x-request-id", "")
    request_id = (
        request_id_header
        if REQUEST_ID_RE.fullmatch(request_id_header)
        else uuid.uuid4().hex
    )
    request.state.request_id = request_id

    content_length = request.headers.get("content-length")
    if content_length:
        request_limit = (
            BROADCAST_MEDIA_MAX_BYTES * 2
            if request.url.path == "/api/admin/broadcast-media"
            else startup_settings.max_request_bytes
        )
        try:
            too_large = int(content_length) > request_limit
        except ValueError:
            too_large = True
        if too_large:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body is too large"},
                headers={"X-Request-Id": request_id},
            )

    # Uvicorn normalizes request.url.scheme only for proxy addresses allowed by
    # FORWARDED_ALLOW_IPS. Reading X-Forwarded-Proto directly would let an
    # untrusted client bypass FORCE_HTTPS by spoofing the header.
    request_scheme = request.url.scheme
    client_host = request.client.host if request.client else ""
    local_healthcheck = client_host in {"127.0.0.1", "::1"}
    if startup_settings.force_https and request_scheme != "https" and not local_healthcheck:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "HTTPS is required"},
            headers={"X-Request-Id": request_id},
        )

    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if request_scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _header_text(value: object) -> str:
    """Normalise an optional header value to a stripped string.

    When a route function is invoked directly (tests, internal callers) the
    unset ``Header(default=None)`` parameters arrive as FastAPI param objects
    rather than ``None``. Anything that is not a string is treated as absent.
    """
    return value.strip() if isinstance(value, str) else ""


_RETIRED_HEADER_BRAND = "g" + "fort"
_SESSION_HEADER_NAMES = (
    "x-novera-session",
    f"x-{_RETIRED_HEADER_BRAND}-session",
)
_TELEGRAM_CONTEXT_HEADER_NAMES = (
    "x-novera-telegram-context",
    f"x-{_RETIRED_HEADER_BRAND}-telegram-context",
)


def _is_native_context(init_data: str, context_header: object) -> bool:
    return bool(init_data) or _header_text(context_header).lower() in {
        "1", "true", "telegram", "native"
    }


def _client_session_token(request: Request, declared: object) -> str:
    """Read the NOVERA per-account session header."""
    direct = _header_text(declared)
    if direct:
        return direct
    headers = getattr(request, "headers", None)
    if headers is None:
        return ""
    for name in _SESSION_HEADER_NAMES:
        value = _header_text(headers.get(name))
        if value:
            return value
    return ""


def _native_telegram_context(
    request: Request,
    init_data: str,
    declared: object,
) -> bool:
    if _is_native_context(init_data, declared):
        return True
    headers = getattr(request, "headers", None)
    if headers is None:
        return False
    for name in _TELEGRAM_CONTEXT_HEADER_NAMES:
        if _header_text(headers.get(name)).lower() in {
            "1", "true", "telegram", "native"
        }:
            return True
    return False


def _referrer_id_from_start_param(start_param: str | None) -> int | None:
    if start_param and start_param.startswith("ref_"):
        raw_referrer = start_param.removeprefix("ref_")
        if raw_referrer.isdigit():
            return int(raw_referrer)
    return None


async def _ensure_telegram_user(
    repository: DeltaRepository,
    telegram_user: TelegramUser,
) -> None:
    blocked = await repository.ensure_user(
        telegram_user.id,
        telegram_user.username,
        telegram_user.first_name,
        telegram_user.language_code,
        _referrer_id_from_start_param(telegram_user.start_param),
    )
    if blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )


async def current_user(
    request: Request,
    response: Response,
    x_telegram_init_data: str | None = Header(default=None),
    x_novera_telegram_context: str | None = Header(
        default=None,
        alias="X-NOVERA-Telegram-Context",
    ),
    x_novera_session: str | None = Header(default=None, alias="X-NOVERA-Session"),
    x_demo_telegram_id: int | None = Header(default=None),
    delta_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> AuthenticatedUser:
    """Authenticate NOVERA without sharing identity between Telegram accounts.

    NOVERA uses a server-signed session token stored in Telegram's own
    per-user SecureStorage (CloudStorage is a compatibility fallback). That
    token is preferred inside Telegram because some Telegram clients reuse a
    WebView and its old initData while switching accounts. Browser cookies are
    never used in a native Telegram launch.
    """
    chain_settings: Settings = request.app.state.chain_settings
    business: MiniAppSettings = request.app.state.business
    repository: DeltaRepository = request.app.state.repository
    bot_token = chain_settings.bot_token.get_secret_value()
    telegram_user: TelegramUser | None = None
    init_data = _header_text(x_telegram_init_data)
    client_session = _client_session_token(request, x_novera_session)
    native_context = _native_telegram_context(
        request, init_data, x_novera_telegram_context
    )
    client_error: TelegramAuthError | None = None
    init_error: TelegramAuthError | None = None

    if business.demo_mode and x_demo_telegram_id is not None:
        telegram_user = TelegramUser(
            id=x_demo_telegram_id,
            username=f"demo_{x_demo_telegram_id}",
            first_name="Demo",
            language_code="ru",
        )
    else:
        # Telegram SecureStorage/CloudStorage is scoped to the currently logged
        # in Telegram user and this Mini App. A valid token read from there is
        # therefore the safest identity source when Telegram reuses WebViews.
        if client_session:
            try:
                telegram_user = validate_web_session(client_session, bot_token)
            except TelegramAuthError as exc:
                client_error = exc

        # Fresh signed initData remains the normal bootstrap path. Keep an age
        # limit here; after bootstrap the per-user Telegram session is used.
        if telegram_user is None and init_data:
            try:
                telegram_user = validate_init_data(
                    init_data,
                    bot_token,
                    max_age_seconds=business.telegram_init_data_ttl_seconds,
                )
            except TelegramAuthError as exc:
                init_error = exc

        if telegram_user is None and native_context:
            detail = str(init_error or client_error or "Telegram authorization is unavailable")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail,
            )

        if telegram_user is None and delta_session:
            try:
                telegram_user = validate_web_session(delta_session, bot_token)
            except TelegramAuthError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(exc),
                ) from exc

        if telegram_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Telegram authorization is unavailable",
            )

    await _ensure_telegram_user(repository, telegram_user)

    if native_context and not business.demo_mode:
        # Domain cookies are shared by some Telegram clients across accounts.
        # They are intentionally removed from native Telegram requests.
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            path="/",
            secure=business.force_https,
            httponly=True,
            samesite="lax",
        )

    dynamic_admin = await repository.is_granted_admin(telegram_user.id)
    return AuthenticatedUser(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        is_admin=(
            telegram_user.id in chain_settings.owner_id_set
            or telegram_user.id in chain_settings.admin_id_set
            or dynamic_admin
        ),
        is_owner=telegram_user.id in chain_settings.owner_id_set,
    )


async def admin_user(
    user: AuthenticatedUser = Depends(current_user),
) -> AuthenticatedUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def owner_user(
    user: AuthenticatedUser = Depends(current_user),
) -> AuthenticatedUser:
    if not user.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required",
        )
    return user


def current_chain_setup(request: Request) -> ChainSetupRuntime:
    setup: ChainSetupRuntime | None = getattr(request.app.state, "chain_setup", None)
    if setup is not None:
        return setup
    chain_settings: Settings = request.app.state.chain_settings
    active = chain_settings.environment != "production" or chain_settings.chain_enabled
    return ChainSetupRuntime(
        status="active" if active else "bootstrap",
        financial_ready=active,
    )


def require_financial_activation(
    request: Request,
    *,
    capability: Literal["deposits", "investments", "payouts", "referral"] | None = None,
) -> Settings:
    chain_settings: Settings = request.app.state.chain_settings
    setup: ChainSetupRuntime | None = getattr(request.app.state, "chain_setup", None)
    # Unit/local callers historically assemble app.state without lifespan.
    # Production always has an explicit setup state.
    if setup is None and chain_settings.environment != "production":
        return chain_settings
    if (
        setup is None
        or setup.status != "active"
        or not setup.financial_ready
        or not chain_settings.chain_enabled
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Financial services are locked until owner activation",
        )
    enabled = {
        "deposits": chain_settings.deposits_enabled,
        "investments": chain_settings.investments_enabled,
        "payouts": chain_settings.payouts_enabled,
        "referral": chain_settings.referral_enabled,
    }
    if capability and not enabled[capability]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{capability.capitalize()} are temporarily disabled",
        )
    return chain_settings


def require_recent_owner_init_data(
    request: Request,
    owner: AuthenticatedUser,
    init_data: str | None,
) -> None:
    value = _header_text(init_data)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Fresh Telegram authorization is required",
        )
    chain_settings: Settings = request.app.state.chain_settings
    try:
        recent = validate_init_data(
            value,
            chain_settings.bot_token.get_secret_value(),
            max_age_seconds=300,
        )
    except TelegramAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Fresh Telegram authorization is required",
        ) from exc
    if recent.id != owner.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram owner identity mismatch",
        )


async def enforce_mutation_limit(
    request: Request,
    user: AuthenticatedUser,
    action: str,
) -> None:
    settings: MiniAppSettings = request.app.state.business
    limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
    retry_after = await limiter.check(
        f"{user.telegram_id}:{action}",
        settings.mutation_rate_limit,
        settings.mutation_rate_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)},
        )


@app.get("/health")
async def health(request: Request) -> dict[str, object]:
    chain_settings: Settings = request.app.state.chain_settings
    setup = current_chain_setup(request)
    return {
        "status": "ok",
        "version": app.version,
        "environment": chain_settings.environment,
        "setup_status": setup.status,
    }


@app.get("/ready")
async def ready(request: Request):
    repository: DeltaRepository = request.app.state.repository
    tasks: list[asyncio.Task[object]] = request.app.state.tasks
    database_ok = await repository.ping()
    failed_tasks = [task.get_name() for task in tasks if task.done()]
    ready_now = database_ok and not failed_tasks
    safety_runtime: SafetyRuntime = request.app.state.safety_runtime
    setup = current_chain_setup(request)
    payload = {
        "status": "ready" if ready_now else "not_ready",
        "database": database_ok,
        "failed_tasks": failed_tasks,
        "setup": setup.snapshot(),
        "safety": {
            "status": safety_runtime.status,
            "circuit_open": safety_runtime.circuit_open,
            "active_alerts": list(safety_runtime.active_alerts),
        },
    }
    if ready_now:
        return payload
    return JSONResponse(status_code=503, content=payload)


@app.post("/api/session/exchange")
async def exchange_bot_login(
    payload: SessionExchangeRequest,
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
    x_novera_telegram_context: str | None = Header(
        default=None,
        alias="X-NOVERA-Telegram-Context",
    ),
    x_novera_session: str | None = Header(default=None, alias="X-NOVERA-Session"),
) -> JSONResponse:
    chain_settings: Settings = request.app.state.chain_settings
    business: MiniAppSettings = request.app.state.business
    repository: DeltaRepository = request.app.state.repository
    bot_token = chain_settings.bot_token.get_secret_value()
    init_data = _header_text(x_telegram_init_data)
    client_session = _client_session_token(request, x_novera_session)
    native_context = _native_telegram_context(
        request, init_data, x_novera_telegram_context
    )

    # /start tokens are one-time, random and live for only ten minutes. They
    # are the recovery path for Telegram clients whose cached WebView does not
    # expose usable initData on the first V10 launch.
    token_user = await repository.consume_web_login_token(payload.token)
    if token_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bot login link is invalid or expired",
        )

    stored_user: TelegramUser | None = None
    if client_session:
        try:
            stored_user = validate_web_session(client_session, bot_token)
        except TelegramAuthError:
            stored_user = None
        if stored_user is not None and stored_user.id != token_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bot login link belongs to another Telegram account",
            )

    signed_user: TelegramUser | None = None
    if init_data:
        try:
            signed_user = validate_init_data(
                init_data,
                bot_token,
                max_age_seconds=business.telegram_init_data_ttl_seconds,
            )
        except TelegramAuthError:
            # A valid one-time /start token is intentionally allowed to repair
            # cached/missing initData. Do not fail the recovery path here.
            signed_user = None
        if signed_user is not None and signed_user.id != token_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bot login link belongs to another Telegram account",
            )

    profile_user = signed_user or stored_user or token_user
    telegram_user = TelegramUser(
        id=token_user.id,
        username=profile_user.username or token_user.username,
        first_name=profile_user.first_name or token_user.first_name,
        language_code=profile_user.language_code or token_user.language_code,
        start_param=token_user.start_param,
    )
    await _ensure_telegram_user(repository, telegram_user)

    if native_context:
        response = JSONResponse(
            content={
                "status": "ok",
                "mode": "telegram",
                "session_token": issue_web_session(
                    telegram_user,
                    bot_token,
                    CLIENT_SESSION_TTL_SECONDS,
                ),
                "expires_in": CLIENT_SESSION_TTL_SECONDS,
            }
        )
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            path="/",
            secure=business.force_https,
            httponly=True,
            samesite="lax",
        )
        return response

    # External-browser one-time links keep a normal HttpOnly cookie.
    response = JSONResponse(
        content={
            "status": "ok",
            "mode": "external",
            "expires_in": business.telegram_session_ttl_seconds,
        }
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=issue_web_session(
            telegram_user,
            bot_token,
            business.telegram_session_ttl_seconds,
        ),
        max_age=business.telegram_session_ttl_seconds,
        expires=business.telegram_session_ttl_seconds,
        path="/",
        secure=business.force_https,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/api/bootstrap")
async def bootstrap(
    request: Request,
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    repository: DeltaRepository = request.app.state.repository
    business: MiniAppSettings = request.app.state.business
    chain_settings: Settings = request.app.state.chain_settings
    result = await repository.bootstrap(user.telegram_id)
    result["auth"] = user.model_dump()
    result["auth_session_token"] = issue_web_session(
        TelegramUser(
            id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            language_code=None,
        ),
        chain_settings.bot_token.get_secret_value(),
        CLIENT_SESSION_TTL_SECONDS,
    )
    result["auth_session_expires_in"] = CLIENT_SESSION_TTL_SECONDS
    result["server_time"] = int(time.time())
    result["mode"] = {
        "environment": chain_settings.environment,
        "demo": business.demo_mode,
        "mainnet": chain_settings.chain_enabled and chain_settings.chain_id == 56,
        "web_only": not chain_settings.chain_enabled,
        "setup": current_chain_setup(request).snapshot(),
    }
    result["terms"] = {
        "daily_profit_bps": business.daily_profit_bps,
        "payout_days": business.payout_days,
        "deposit_min_usdt": business.deposit_min_usdt,
        "deposit_max_usdt": business.deposit_max_usdt,
        "referral_level_bps": business.referral_level_bps,
        "referral_personal_thresholds_usdt": business.referral_personal_thresholds_usdt,
        "referral_line_thresholds_usdt": business.referral_line_thresholds_usdt,
    }
    result["chain"] = {
        "enabled": chain_settings.chain_enabled,
        "deposits_enabled": chain_settings.deposits_enabled,
        "payouts_enabled": chain_settings.payouts_enabled,
        "chain_id": chain_settings.chain_id,
        "token_symbol": chain_settings.token_symbol,
        "treasury_address": chain_settings.treasury_address,
        "simulate_payouts": chain_settings.simulate_payouts,
        "explorer_tx_url": chain_settings.block_explorer_tx_url,
        "confirmation_blocks": chain_settings.confirmation_blocks,
    }
    bot_username = business.bot_username.lstrip("@")
    result["referral_link"] = (
        f"https://t.me/{bot_username}?start=ref_{user.telegram_id}"
    )
    result["support_url"] = chain_settings.support_url
    result["chat_url"] = chain_settings.chat_url
    return result


@app.get("/api/notifications")
async def notifications(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    category: str | None = Query(default=None),
    after_id: int | None = Query(default=None, ge=1),
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.list_notifications(
        user.telegram_id,
        limit=limit,
        category=category,
        after_id=after_id,
    )


@app.post("/api/notifications/{notification_id}/read")
async def read_notification(
    notification_id: int,
    request: Request,
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "notification-read")
    repository: DeltaRepository = request.app.state.repository
    return {"read": await repository.mark_notification_read(user.telegram_id, notification_id)}


@app.post("/api/notifications/read-all")
async def read_all_notifications(
    request: Request,
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "notification-read-all")
    repository: DeltaRepository = request.app.state.repository
    return {"updated": await repository.mark_all_notifications_read(user.telegram_id)}


@app.get("/api/team")
async def team(
    request: Request,
    today_start: int | None = Query(default=None, ge=0),
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.team(user.telegram_id, today_start=today_start)


@app.post("/api/referrals/withdraw")
async def withdraw_referral_rewards(
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "referral-withdrawal")
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")
    chain_settings = require_financial_activation(request, capability="payouts")
    if not chain_settings.referral_enabled:
        raise HTTPException(status_code=503, detail="Payouts are temporarily disabled")
    repository: DeltaRepository = request.app.state.repository
    try:
        payout = await repository.request_referral_withdrawal(
            user.telegram_id,
            idempotency_key,
        )
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "payout_id": int(payout["id"]),
        "amount_minor": int(payout["amount_minor"]),
        "address": str(payout["address"]),
        "status": str(payout["status"]),
        "reused": bool(payout.get("reused", False)),
    }


@app.post("/api/wallet")
async def set_wallet(
    payload: WalletRequest,
    request: Request,
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, str]:
    await enforce_mutation_limit(request, user, "wallet")
    chain_settings: Settings = request.app.state.chain_settings
    if not chain_settings.chain_enabled:
        raise HTTPException(
            status_code=503,
            detail="Wallet configuration is disabled in web-only mode",
        )
    if not Web3.is_address(payload.address):
        raise HTTPException(status_code=422, detail="Invalid BNB Chain address")
    address = Web3.to_checksum_address(payload.address)
    repository: DeltaRepository = request.app.state.repository
    try:
        await repository.set_wallet(user.telegram_id, address)
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"address": address}


@app.post("/api/deposits/invoice")
async def create_invoice(
    payload: InvoiceRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "invoice")
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")
    repository: DeltaRepository = request.app.state.repository
    chain_settings = require_financial_activation(request, capability="deposits")
    if not (
        chain_settings.chain_enabled
        and chain_settings.deposits_enabled
        and chain_settings.payouts_enabled
    ):
        raise HTTPException(
            status_code=503,
            detail="Deposits are temporarily disabled",
        )
    if not chain_settings.treasury_address:
        raise HTTPException(status_code=503, detail="Treasury wallet is not configured")
    promo_code = payload.promo_code.strip() if payload.promo_code else None
    try:
        invoice = await repository.create_invoice(
            user.telegram_id,
            usdt_to_minor(payload.amount),
            idempotency_key,
            promo_code=promo_code or None,
        )
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    bonus_minor = int(invoice.get("bonus_minor") or 0)
    effective_principal_minor = int(
        invoice.get("effective_principal_preview_minor")
        or (int(invoice["exact_minor"]) + bonus_minor)
    )
    return {
        "invoice_id": invoice["invoice_id"],
        "exact_amount": minor_to_text(int(invoice["exact_minor"]), trim=False),
        "expires_at": invoice["expires_at"],
        "reused": bool(invoice.get("reused", False)),
        "treasury_address": chain_settings.treasury_address,
        "token_symbol": chain_settings.token_symbol,
        "chain_id": chain_settings.chain_id,
        "promo_code_id": invoice.get("promo_code_id"),
        "bonus_minor": bonus_minor,
        "bonus_usdt": minor_to_text(bonus_minor, trim=False),
        "effective_principal_usdt": minor_to_text(effective_principal_minor, trim=False),
    }


@app.get("/api/admin/summary")
async def admin_summary(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, int]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_summary()


@app.get("/api/admin/users")
async def admin_users(
    request: Request,
    query: str = Query(default="", max_length=64),
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_users(query)


@app.get("/api/admin/users/{telegram_id}")
async def admin_user_detail(
    telegram_id: int,
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    repository: DeltaRepository = request.app.state.repository
    result = await repository.admin_user_detail(telegram_id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result


@app.post("/api/admin/users/{telegram_id}/block")
async def admin_block_user(
    telegram_id: int,
    payload: BlockRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, bool]:
    await enforce_mutation_limit(request, user, "block-user")
    if telegram_id == user.telegram_id and payload.blocked:
        raise HTTPException(status_code=409, detail="Administrator cannot block itself")
    repository: DeltaRepository = request.app.state.repository
    changed = await repository.set_user_blocked(telegram_id, payload.blocked)
    if not changed:
        raise HTTPException(status_code=404, detail="User not found")
    return {"blocked": payload.blocked}


@app.post("/api/admin/users/{telegram_id}/balance")
async def admin_set_user_balance(
    telegram_id: int,
    payload: AdminUserBalanceRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "user-balance")
    require_financial_activation(request)
    if not idempotency_key or not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")
    repository: DeltaRepository = request.app.state.repository
    try:
        result = await repository.set_user_balance(
            telegram_id,
            usdt_to_minor(payload.balance_usdt),
            user.telegram_id,
            payload.reason,
            idempotency_key,
        )
    except RepositoryError as exc:
        detail = str(exc)
        if detail == "User not found":
            code = 404
        elif "Idempotency" in detail:
            code = 409
        else:
            code = 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return {
        **result,
        "balance_usdt": minor_to_text(int(result["new_balance_minor"]), trim=False),
    }


@app.post("/api/admin/users/{telegram_id}/wallet")
async def admin_set_user_wallet(
    telegram_id: int,
    payload: AdminUserWalletRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "user-wallet")
    raw = (payload.address or "").strip()
    address: str | None = None
    if raw:
        if not Web3.is_address(raw):
            raise HTTPException(status_code=422, detail="Invalid BNB Chain address")
        address = Web3.to_checksum_address(raw)
    repository: DeltaRepository = request.app.state.repository
    if not await repository.admin_set_user_wallet(telegram_id, address, user.telegram_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"address": address}


@app.post("/api/admin/users/{telegram_id}/referrer")
async def admin_set_user_referrer(
    telegram_id: int,
    payload: AdminUserReferrerRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "user-referrer")
    repository: DeltaRepository = request.app.state.repository
    try:
        result = await repository.admin_set_user_referrer(
            telegram_id,
            payload.identifier,
            user.telegram_id,
        )
    except RepositoryError as exc:
        detail = str(exc)
        if detail == "User not found":
            code = 404
        elif detail == "Referrer not found":
            code = 404
        elif "cycle" in detail.lower() or "own referrer" in detail.lower():
            code = 409
        else:
            code = 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return result


@app.post("/api/admin/users/{telegram_id}/referral-balance")
async def admin_set_referral_balance(
    telegram_id: int,
    payload: AdminReferralBalanceRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "referral-balance")
    require_financial_activation(request, capability="referral")
    if not idempotency_key or not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")
    repository: DeltaRepository = request.app.state.repository
    try:
        result = await repository.admin_set_referral_balance(
            telegram_id,
            usdt_to_minor(payload.balance_usdt),
            user.telegram_id,
            payload.reason,
            idempotency_key,
        )
    except RepositoryError as exc:
        detail = str(exc)
        if detail == "User not found":
            code = 404
        elif "Idempotency" in detail:
            code = 409
        else:
            code = 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return {
        **result,
        "balance_usdt": minor_to_text(int(result["new_balance_minor"]), trim=False),
    }


@app.post("/api/admin/users/{telegram_id}/referral-level")
async def admin_set_referral_level(
    telegram_id: int,
    payload: AdminReferralLevelRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "referral-level")
    require_financial_activation(request, capability="referral")
    if not idempotency_key or not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")
    repository: DeltaRepository = request.app.state.repository
    try:
        return await repository.admin_set_referral_level(
            telegram_id,
            payload.unlocked_level,
            user.telegram_id,
            payload.reason,
            idempotency_key,
        )
    except RepositoryError as exc:
        detail = str(exc)
        if detail == "User not found":
            code = 404
        elif "Idempotency" in detail:
            code = 409
        else:
            code = 422
        raise HTTPException(status_code=code, detail=detail) from exc


@app.post("/api/admin/users/{telegram_id}/investments")
async def admin_open_investment(
    telegram_id: int,
    payload: AdminOpenInvestmentRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "open-investment")
    require_financial_activation(request, capability="investments")
    repository: DeltaRepository = request.app.state.repository
    try:
        result = await repository.admin_open_investment(
            telegram_id,
            usdt_to_minor(payload.amount_usdt),
            user.telegram_id,
            payload.reason,
            payload.operation_id,
        )
    except RepositoryError as exc:
        detail = str(exc)
        if detail == "User not found":
            code = 404
        elif detail == "Account is blocked":
            code = 409
        else:
            code = 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return {
        **result,
        "amount_usdt": minor_to_text(int(result["principal_minor"]), trim=False),
    }


@app.post("/api/admin/users/{telegram_id}/investments/{deposit_id}/close")
async def admin_close_investment(
    telegram_id: int,
    deposit_id: int,
    payload: AdminCloseInvestmentRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "close-investment")
    require_financial_activation(request, capability="investments")
    repository: DeltaRepository = request.app.state.repository
    try:
        result = await repository.admin_close_investment(
            telegram_id,
            deposit_id,
            user.telegram_id,
            payload.reason,
            payload.operation_id,
        )
    except RepositoryError as exc:
        detail = str(exc)
        if detail == "Deposit not found":
            code = 404
        elif detail.startswith("Investment has in-flight payouts"):
            code = 409
        elif detail == "Only active investments can be closed":
            code = 409
        else:
            code = 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return {
        **result,
        "amount_usdt": minor_to_text(int(result["principal_minor"]), trim=False),
    }


@app.get("/api/admin/admins")
async def admin_admins(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    chain_settings: Settings = request.app.state.chain_settings
    return await repository.admin_admins(
        chain_settings.admin_id_set | chain_settings.owner_id_set
    )


@app.post("/api/admin/admins")
async def add_admin(
    payload: AdminGrantRequest,
    request: Request,
    user: AuthenticatedUser = Depends(owner_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "grant-admin")
    repository: DeltaRepository = request.app.state.repository
    chain_settings: Settings = request.app.state.chain_settings
    try:
        result = await repository.grant_admin(payload.identifier, user.telegram_id)
    except RepositoryError as exc:
        if str(exc) == "User not found":
            raise HTTPException(status_code=404, detail="User not found") from exc
        raise HTTPException(status_code=422, detail="Invalid administrator identifier") from exc
    if int(result["telegram_id"]) in (
        chain_settings.admin_id_set | chain_settings.owner_id_set
    ):
        result["source"] = "bootstrap"
        result["protected"] = True
    return result


@app.delete("/api/admin/admins/{telegram_id}")
async def remove_admin(
    telegram_id: int,
    request: Request,
    user: AuthenticatedUser = Depends(owner_user),
) -> dict[str, bool]:
    await enforce_mutation_limit(request, user, "revoke-admin")
    chain_settings: Settings = request.app.state.chain_settings
    if telegram_id in (chain_settings.admin_id_set | chain_settings.owner_id_set):
        raise HTTPException(status_code=409, detail="Bootstrap owner or administrator cannot be removed")
    if telegram_id == user.telegram_id:
        raise HTTPException(status_code=409, detail="Administrator cannot remove itself")
    repository: DeltaRepository = request.app.state.repository
    removed = await repository.revoke_admin(telegram_id, user.telegram_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Administrator grant not found")
    return {"removed": True}


@app.get("/api/admin/deposits")
async def admin_deposits(
    request: Request,
    deposit_status: Literal["active", "completed", "paused", "failed"] | None = Query(
        default=None,
        alias="status",
    ),
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_deposits(deposit_status)


@app.get("/api/admin/operations")
async def admin_operations(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_operations()


@app.post("/api/admin/payouts/{payout_id}/retry")
async def retry_payout(
    payout_id: int,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, bool]:
    await enforce_mutation_limit(request, user, "retry-payout")
    require_financial_activation(request, capability="payouts")
    repository: DeltaRepository = request.app.state.repository
    return {"retried": await repository.retry_payout(payout_id)}


@app.get("/api/admin/promo-codes")
async def admin_list_promo_codes(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    rows = await repository.admin_list_promo_codes()
    return [_promo_response(row) for row in rows]


@app.post("/api/admin/promo-codes")
async def admin_create_promo_code(
    payload: PromoCodeCreateRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "promo-code")
    bonus_bps, bonus_fixed_minor = _promo_bonus_minor_fields(
        payload.bonus_type, payload.bonus_percent, payload.bonus_usdt
    )
    repository: DeltaRepository = request.app.state.repository
    try:
        created = await repository.admin_create_promo_code(
            code=payload.code,
            bonus_type=payload.bonus_type,
            bonus_bps=bonus_bps,
            bonus_fixed_minor=bonus_fixed_minor,
            max_redemptions=payload.max_redemptions,
            min_deposit_minor=_usdt_to_minor_allow_zero(payload.min_deposit_usdt),
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            enabled=payload.enabled,
            created_by=user.telegram_id,
        )
    except RepositoryError as exc:
        detail = str(exc)
        code = 409 if "already exists" in detail else 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return _promo_response(created)


@app.patch("/api/admin/promo-codes/{promo_id}")
async def admin_update_promo_code(
    promo_id: int,
    payload: PromoCodeUpdateRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "promo-code-update")
    repository: DeltaRepository = request.app.state.repository
    fields = payload.model_dump(exclude_unset=True)
    bonus_percent = fields.pop("bonus_percent", None)
    bonus_usdt = fields.pop("bonus_usdt", None)
    if "bonus_type" in fields or bonus_percent is not None or bonus_usdt is not None:
        current = await repository.admin_list_promo_codes()
        existing = next((row for row in current if int(row["id"]) == promo_id), None)
        if existing is None:
            raise HTTPException(status_code=404, detail="Promo code not found")
        bonus_type = fields.get("bonus_type", existing["bonus_type"])
        bonus_bps, bonus_fixed_minor = _promo_bonus_minor_fields(
            bonus_type, bonus_percent, bonus_usdt
        )
        fields["bonus_type"] = bonus_type
        fields["bonus_bps"] = bonus_bps
        fields["bonus_fixed_minor"] = bonus_fixed_minor
    if "min_deposit_usdt" in fields:
        fields["min_deposit_minor"] = _usdt_to_minor_allow_zero(
            fields.pop("min_deposit_usdt")
        )
    try:
        updated = await repository.admin_update_promo_code(promo_id, **fields)
    except RepositoryError as exc:
        detail = str(exc)
        if detail == "Promo code not found":
            code = 404
        elif "already exists" in detail:
            code = 409
        else:
            code = 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return _promo_response(updated)


@app.get("/api/admin/broadcasts")
async def admin_broadcasts(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_broadcasts()


@app.get("/api/admin/broadcasts/audience")
async def admin_broadcast_audience(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, int]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.broadcast_audience_counts()


@app.post("/api/admin/broadcasts/test")
async def send_broadcast_test(
    payload: BroadcastTestRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "broadcast-test")
    message = sanitize_telegram_html(payload.message)
    if not message:
        raise HTTPException(status_code=422, detail="Broadcast message or image is required")
    repository: DeltaRepository = request.app.state.repository
    try:
        queued = await repository.queue_broadcast_self_test(
            user.telegram_id,
            telegram_html=message,
            preview=html.unescape(re.sub(r"<[^>]+>", "", message))[:400],
        )
    except RepositoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"queued": queued, "recipient_id": user.telegram_id}


@app.post("/api/admin/broadcasts/{broadcast_id}/retry")
async def retry_broadcast(
    broadcast_id: int,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, int]:
    await enforce_mutation_limit(request, user, "retry-broadcast")
    repository: DeltaRepository = request.app.state.repository
    try:
        return await repository.retry_broadcast(broadcast_id)
    except RepositoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/broadcast-media")
async def upload_broadcast_media(
    payload: BroadcastMediaUploadRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "broadcast-media")
    try:
        raw = base64.b64decode(payload.data_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid image encoding") from exc
    if not raw or len(raw) > BROADCAST_MEDIA_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")
    if payload.mime_type == "image/jpeg":
        if not raw.startswith(b"\xff\xd8\xff"):
            raise HTTPException(status_code=422, detail="Invalid JPEG image")
        extension = ".jpg"
    else:
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=422, detail="Invalid PNG image")
        extension = ".png"
    chain_settings: Settings = request.app.state.chain_settings
    media_dir = Path(chain_settings.database_path).parent / "broadcast_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    try:
        media_dir.chmod(0o700)
    except OSError:
        pass
    media_id = f"{uuid.uuid4().hex}{extension}"
    path = media_dir / media_id
    path.write_bytes(raw)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return {"media_id": media_id, "size": len(raw), "mime_type": payload.mime_type}


@app.post("/api/admin/broadcasts")
async def create_broadcast(
    payload: BroadcastRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, int | str]:
    await enforce_mutation_limit(request, user, "broadcast")
    message = sanitize_telegram_html(payload.message)
    buttons = validate_broadcast_buttons(payload.buttons)
    media_path: str | None = None
    if payload.media_id:
        if not BROADCAST_MEDIA_ID_RE.fullmatch(payload.media_id):
            raise HTTPException(status_code=422, detail="Invalid broadcast image id")
        chain_settings: Settings = request.app.state.chain_settings
        candidate = Path(chain_settings.database_path).parent / "broadcast_media" / payload.media_id
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="Broadcast image not found")
        media_path = str(candidate)
    if not message and not media_path:
        raise HTTPException(status_code=422, detail="Broadcast message or image is required")
    repository: DeltaRepository = request.app.state.repository
    return await repository.create_broadcast(
        user.telegram_id,
        message,
        payload.audience,
        parse_mode="HTML",
        media_path=media_path,
        buttons=buttons,
    )


@app.get("/api/admin/treasury")
async def admin_treasury(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    chain_settings: Settings = request.app.state.chain_settings
    chain: EvmTokenClient | None = request.app.state.chain
    if chain is None or not chain_settings.chain_enabled:
        return {
            "enabled": False,
            "chain_id": chain_settings.chain_id,
            "address": chain_settings.treasury_address,
            "token_symbol": chain_settings.token_symbol,
            "payouts_enabled": chain_settings.payouts_enabled,
            "simulate_payouts": chain_settings.simulate_payouts,
            "explorer_tx_url": chain_settings.block_explorer_tx_url,
        }
    token_atomic, native_wei = await asyncio.gather(
        chain.token_balance(chain_settings.treasury_address),
        chain.native_balance(chain_settings.treasury_address),
    )
    token_value = Decimal(token_atomic) / (Decimal(10) ** chain_settings.token_decimals)
    native_value = Decimal(native_wei) / (Decimal(10) ** 18)
    return {
        "enabled": True,
        "chain_id": chain_settings.chain_id,
        "address": chain_settings.treasury_address,
        "token_symbol": chain_settings.token_symbol,
        "token_balance": format(token_value, "f"),
        "native_balance": format(native_value, "f"),
        "payouts_enabled": chain_settings.payouts_enabled,
        "simulate_payouts": chain_settings.simulate_payouts,
        "explorer_tx_url": chain_settings.block_explorer_tx_url,
    }


@app.get("/api/admin/treasury/test-payouts")
async def admin_test_payouts(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_test_payouts()


@app.post("/api/admin/treasury/test-payout")
async def create_admin_test_payout(
    payload: AdminTestPayoutRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "admin-test-payout")
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")

    chain_settings = require_financial_activation(request, capability="payouts")
    chain: EvmTokenClient | None = request.app.state.chain
    if not chain_settings.payouts_enabled:
        raise HTTPException(status_code=503, detail="Payouts are temporarily disabled")
    if chain is None or not chain_settings.chain_enabled or chain_settings.simulate_payouts:
        raise HTTPException(status_code=503, detail="Real payouts are not enabled")
    if not Web3.is_address(payload.address):
        raise HTTPException(status_code=422, detail="Invalid BNB Chain address")
    address = Web3.to_checksum_address(payload.address)
    if address.lower() == chain_settings.treasury_address.lower():
        raise HTTPException(status_code=422, detail="Destination must differ from treasury")

    try:
        amount_minor = usdt_to_minor(payload.amount)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid payout amount") from exc
    if amount_minor < MINOR_FACTOR:
        raise HTTPException(status_code=422, detail="Minimum admin test payout is 1 USDT")

    native_wei, token_atomic = await chain.signer_balances()
    required_atomic = minor_to_atomic(amount_minor, chain_settings.token_decimals)
    if token_atomic < required_atomic:
        raise HTTPException(status_code=409, detail="Insufficient treasury USDT balance")
    if native_wei <= 0:
        raise HTTPException(status_code=409, detail="Treasury has no BNB for gas")

    repository: DeltaRepository = request.app.state.repository
    try:
        payout = await repository.request_admin_test_payout(
            user.telegram_id,
            address,
            amount_minor,
            idempotency_key,
        )
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "payout_id": int(payout["id"]),
        "amount_minor": int(payout["amount_minor"]),
        "address": str(payout["address"]),
        "status": str(payout["status"]),
        "reused": bool(payout.get("reused", False)),
        "real": True,
    }


@app.get("/api/admin/settings")
async def admin_runtime_settings(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    return runtime_settings_snapshot(request.app.state.business, request.app.state.chain_settings)


@app.post("/api/admin/settings")
async def update_admin_runtime_settings(
    payload: RuntimeSettingsRequest,
    request: Request,
    user: AuthenticatedUser = Depends(owner_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "runtime-settings")
    validate_runtime_settings_payload(payload)
    values = payload.model_dump(exclude_none=True)
    setup = current_chain_setup(request)
    requested_finance = any(
        bool(values.get(name))
        for name in (
            "deposits_enabled",
            "investments_enabled",
            "payouts_enabled",
            "referral_enabled",
        )
    )
    if requested_finance and (
        setup.status != "active" or not setup.financial_ready
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Financial services cannot be enabled before owner chain activation",
        )
    repository: DeltaRepository = request.app.state.repository
    try:
        await repository.set_runtime_settings(values, user.telegram_id)
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    business: MiniAppSettings = request.app.state.business
    chain_settings: Settings = request.app.state.chain_settings
    apply_runtime_settings(business, chain_settings, values)
    business.validate_business_rules()
    return runtime_settings_snapshot(business, chain_settings)


@app.get("/api/admin/terms")
async def admin_terms(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    business: MiniAppSettings = request.app.state.business
    chain_settings: Settings = request.app.state.chain_settings
    return {
        "daily_profit_bps": business.daily_profit_bps,
        "payout_days": business.payout_days,
        "deposit_min_usdt": business.deposit_min_usdt,
        "deposit_max_usdt": business.deposit_max_usdt,
        "referral_level_bps": business.referral_level_bps,
        "referral_personal_thresholds_usdt": business.referral_personal_thresholds_usdt,
        "referral_line_thresholds_usdt": business.referral_line_thresholds_usdt,
        "chain_id": chain_settings.chain_id,
        "token_symbol": chain_settings.token_symbol,
        "treasury_address": chain_settings.treasury_address,
        "confirmation_blocks": chain_settings.confirmation_blocks,
        "deposit_scan_interval_seconds": chain_settings.deposit_scan_interval_seconds,
    }


@app.get("/api/admin/audit")
async def admin_audit(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_audit(limit)


@app.get("/api/admin/chain-config")
async def admin_chain_config(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    return chain_runtime_snapshot(
        request.app.state.chain_settings,
        current_chain_setup(request),
        request.app.state.secret_store,
    )


@app.post("/api/admin/chain-config/validate")
@app.post("/api/admin/chain-config")
async def validate_admin_chain_config(
    payload: ChainRuntimeConfigRequest,
    request: Request,
    user: AuthenticatedUser = Depends(owner_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "chain-config-validate")
    store: RuntimeSecretStore | None = request.app.state.secret_store
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encrypted runtime configuration store is unavailable",
        )

    rpc = payload.rpc_url.get_secret_value().strip()
    wss = payload.wss_url.get_secret_value().strip()
    seed = " ".join(payload.seed_phrase.get_secret_value().split())
    await validate_public_provider_url(
        rpc,
        schemes=frozenset({"https"} if payload.mode == "production" else {"http", "https"}),
        label="RPC",
    )
    await validate_public_provider_url(
        wss,
        schemes=frozenset({"wss"} if payload.mode == "production" else {"ws", "wss"}),
        label="WSS",
    )

    current: Settings = request.app.state.chain_settings
    candidate = current.model_copy(deep=True)
    if payload.mode == "production":
        candidate.environment = "production"
        candidate.chain_enabled = True
        candidate.simulate_payouts = False
        candidate.chain_id = 56
    else:
        candidate.environment = "testnet"
        candidate.chain_enabled = True
        candidate.simulate_payouts = False
        candidate.chain_id = 97
    candidate.token_contract = (
        Web3.to_checksum_address(payload.token_contract)
        if Web3.is_address(payload.token_contract)
        else payload.token_contract
    )
    candidate.scan_start_block = int(payload.scan_start_block)
    candidate.bsc_rpc_url = rpc
    candidate.bsc_wss_url = wss
    candidate.payout_seed_phrase = SecretStr(seed)
    candidate.payout_private_key = None
    candidate.payout_keystore_path = None
    candidate.payout_keystore_password = None
    validate_chain_runtime_candidate(candidate)
    validate_deployment_settings(candidate, request.app.state.business)

    client = EvmTokenClient(candidate)
    try:
        http_result = await client.healthcheck()
        ws_result = await client.websocket_healthcheck()
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "New blockchain configuration failed health check: "
                f"{client.safe_error(exc)}"
            ),
        ) from exc
    finally:
        await client.close()

    bundle = ChainSecretBundle.create(
        mode=payload.mode,
        chain_id=candidate.chain_id,
        rpc_url=rpc,
        wss_url=wss,
        seed_phrase=seed,
        token_contract=candidate.token_contract,
        treasury_address=candidate.treasury_address,
        scan_start_block=candidate.scan_start_block,
    )
    try:
        store.stage(bundle)
        store.prune_pending()
    except RuntimeSecretError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    repository: DeltaRepository = request.app.state.repository
    await repository.record_chain_config_staged(
        bundle.generation,
        bundle.public_fingerprint,
        user.telegram_id,
        payload.reason,
    )
    setup = current_chain_setup(request)
    setup.pending_generation = bundle.generation
    setup.public_fingerprint = bundle.public_fingerprint
    if setup.status != "active":
        setup.status = "configured"

    return {
        "validated": True,
        "generation": bundle.generation,
        "mode": payload.mode,
        "chain_id": candidate.chain_id,
        "treasury_address": bundle.treasury_address,
        "public_fingerprint": bundle.public_fingerprint,
        "rpc_health": {
            "chain_id": http_result.chain_id,
            "block_number": http_result.block_number,
        },
        "wss_health": {
            "chain_id": ws_result.chain_id,
            "block_number": ws_result.block_number,
            "subscription_ok": ws_result.subscription_ok,
        },
    }


@app.post("/api/admin/chain-config/activate")
async def activate_admin_chain_config(
    payload: ChainActivationRequest,
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
    user: AuthenticatedUser = Depends(owner_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "chain-config-activate")
    require_recent_owner_init_data(request, user, x_telegram_init_data)
    repository: DeltaRepository = request.app.state.repository
    existing = await repository.get_chain_activation(payload.operation_id)
    if existing is not None:
        if (
            str(existing["generation"]) != payload.generation
            or int(existing["actor_id"]) != user.telegram_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key was already used",
            )
        return {
            "activated": str(existing["status"]) == "activated",
            "generation": payload.generation,
            "reused": True,
            "restart_scheduled": False,
        }

    store: RuntimeSecretStore | None = request.app.state.secret_store
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encrypted runtime configuration store is unavailable",
        )
    try:
        bundle = store.load_pending(payload.generation)
    except RuntimeSecretError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if (
        not Web3.is_address(payload.treasury_confirmation)
        or Web3.to_checksum_address(payload.treasury_confirmation)
        != Web3.to_checksum_address(bundle.treasury_address)
    ):
        raise HTTPException(
            status_code=422,
            detail="Treasury confirmation does not match the derived wallet",
        )

    await validate_public_provider_url(
        bundle.rpc_url,
        schemes=frozenset({"https"} if bundle.mode == "production" else {"http", "https"}),
        label="RPC",
    )
    await validate_public_provider_url(
        bundle.wss_url,
        schemes=frozenset({"wss"} if bundle.mode == "production" else {"ws", "wss"}),
        label="WSS",
    )
    candidate: Settings = request.app.state.chain_settings.model_copy(deep=True)
    apply_chain_bundle(candidate, bundle)
    validate_chain_runtime_candidate(candidate)
    validate_deployment_settings(candidate, request.app.state.business)
    client = EvmTokenClient(candidate)
    try:
        await client.healthcheck()
        await client.websocket_healthcheck()
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Blockchain activation health check failed: {client.safe_error(exc)}",
        ) from exc
    finally:
        await client.close()

    try:
        store.activate(bundle.generation)
        result = await repository.record_chain_config_activated(
            payload.operation_id,
            bundle.generation,
            bundle.public_fingerprint,
            user.telegram_id,
            payload.reason,
        )
    except RepositoryError as exc:
        store.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeSecretError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    disable_financial_runtime(request.app.state.chain_settings)
    setup = current_chain_setup(request)
    setup.status = "configured"
    setup.active_generation = bundle.generation
    setup.pending_generation = None
    setup.public_fingerprint = bundle.public_fingerprint
    setup.financial_ready = False
    schedule_process_restart()
    return {
        "activated": True,
        "generation": bundle.generation,
        "treasury_address": bundle.treasury_address,
        "reused": bool(result["reused"]),
        "restart_scheduled": True,
    }


@app.get("/api/admin/safety")
async def admin_safety(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    runtime: SafetyRuntime = request.app.state.safety_runtime
    repository: DeltaRepository = request.app.state.repository
    result = runtime.snapshot()
    result["queue"] = await repository.payout_safety_metrics()
    return result


@app.get("/api/admin/system")
async def admin_system(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    chain_settings: Settings = request.app.state.chain_settings
    runtime: RuntimeStatus = request.app.state.runtime
    tasks: list[asyncio.Task[object]] = request.app.state.tasks
    signing_configured = bool(
        chain_settings.payout_seed_phrase
        or chain_settings.payout_private_key
        or (
            chain_settings.payout_keystore_path
            and chain_settings.payout_keystore_password
        )
    )
    safety_runtime: SafetyRuntime = request.app.state.safety_runtime
    setup = current_chain_setup(request)
    return {
        "uptime_seconds": int(time.time() - runtime.started_at),
        "last_payout_tick": runtime.last_payout_tick,
        "last_payout_error": runtime.last_payout_error,
        "chain_enabled": chain_settings.chain_enabled,
        "chain_id": chain_settings.chain_id,
        "simulate_payouts": chain_settings.simulate_payouts,
        "setup": setup.snapshot(),
        "safety": safety_runtime.snapshot(),
        "tasks": {
            task.get_name(): "stopped" if task.done() else "running"
            for task in tasks
        },
        "blockchain_configuration": {
            "rpc_configured": bool(chain_settings.bsc_rpc_url),
            "wss_configured": bool(chain_settings.bsc_wss_url),
            "token_contract_configured": bool(chain_settings.token_contract),
            "treasury_address_configured": bool(chain_settings.treasury_address),
            "signing_configured": signing_configured,
            "activation_scope": "bsc_mainnet" if chain_settings.chain_id == 56 else "bsc_testnet",
            "restart_required": True,
        },
    }
